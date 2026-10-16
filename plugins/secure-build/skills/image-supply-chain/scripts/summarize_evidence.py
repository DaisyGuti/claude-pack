#!/usr/bin/env python3
"""Summarize scan and SBOM evidence in a directory and gate on vulnerability severity.

Usage:
    summarize_evidence.py [--fail-on LOW|MEDIUM|HIGH|CRITICAL] EVIDENCE_DIR

Reads, when present: trivy.json or grype.json, sbom.cdx.json (CycloneDX) and sbom.spdx.json
(SPDX). Prints a markdown summary. Exit codes: 0 fine, 1 a vulnerability at or above
--fail-on exists, 2 the evidence is missing or unreadable.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SEVERITIES = ("UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL")
# Longest list of top findings printed; a report longer than this stops being read.
MAX_LISTED = 25


class EvidenceError(Exception):
    """The evidence directory cannot be summarized; the message says what to do."""


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise EvidenceError(f"{path}: file not found. Run image_evidence.sh first.") from None
    except json.JSONDecodeError as error:
        raise EvidenceError(
            f"{path}: not valid JSON ({error}). Rerun the tool that wrote it."
        ) from None


def normalize(severity: str | None) -> str:
    value = (severity or "UNKNOWN").upper()
    return value if value in SEVERITIES else "UNKNOWN"


def trivy_vulns(report: dict[str, Any]) -> list[dict[str, str]]:
    vulns: list[dict[str, str]] = []
    for result in report.get("Results") or []:
        for item in result.get("Vulnerabilities") or []:
            vulns.append(
                {
                    "id": item.get("VulnerabilityID", "?"),
                    "package": item.get("PkgName", "?"),
                    "installed": item.get("InstalledVersion", "?"),
                    "fixed": item.get("FixedVersion", ""),
                    "severity": normalize(item.get("Severity")),
                }
            )
    return vulns


def grype_vulns(report: dict[str, Any]) -> list[dict[str, str]]:
    vulns: list[dict[str, str]] = []
    for match in report.get("matches") or []:
        vuln = match.get("vulnerability", {})
        artifact = match.get("artifact", {})
        fixed = ", ".join((vuln.get("fix") or {}).get("versions") or [])
        vulns.append(
            {
                "id": vuln.get("id", "?"),
                "package": artifact.get("name", "?"),
                "installed": artifact.get("version", "?"),
                "fixed": fixed,
                "severity": normalize(vuln.get("severity")),
            }
        )
    return vulns


def trivy_secrets(report: dict[str, Any]) -> int:
    return sum(len(r.get("Secrets") or []) for r in report.get("Results") or [])


def count_cyclonedx(bom: dict[str, Any]) -> int:
    return len(bom.get("components") or [])


def count_spdx(doc: dict[str, Any]) -> int:
    # The SPDX document lists the image itself as a package; it is not a dependency.
    return len(doc.get("packages") or [])


def summarize(directory: Path, fail_on: str | None) -> tuple[str, int]:
    if not directory.is_dir():
        raise EvidenceError(
            f"{directory}: not a directory. Pass the OUT_DIR image_evidence.sh used."
        )
    lines = [f"# Image evidence summary ({directory})", ""]
    exit_code = 0
    secrets = 0

    if (directory / "trivy.json").exists():
        report = load_json(directory / "trivy.json")
        vulns, scanner = trivy_vulns(report), "trivy"
        secrets = trivy_secrets(report)
    elif (directory / "grype.json").exists():
        vulns, scanner = grype_vulns(load_json(directory / "grype.json")), "grype"
    else:
        raise EvidenceError(
            f"{directory}: neither trivy.json nor grype.json found. Run image_evidence.sh first."
        )

    counts = Counter(v["severity"] for v in vulns)
    lines += [
        f"## Vulnerabilities ({scanner})",
        "",
        "| Severity | Count | With a fix |",
        "|---|---|---|",
    ]
    for severity in reversed(SEVERITIES):
        fixable = sum(1 for v in vulns if v["severity"] == severity and v["fixed"])
        lines.append(f"| {severity} | {counts.get(severity, 0)} | {fixable} |")
    if secrets:
        lines += [
            "",
            f"Secrets found in image layers: {secrets}. Treat each as compromised and rotate it.",
        ]

    top = [v for v in vulns if v["severity"] in {"CRITICAL", "HIGH"}]
    if top:
        lines += ["", "Critical and high findings:", ""]
        for v in sorted(top, key=lambda x: (-SEVERITIES.index(x["severity"]), x["id"]))[
            :MAX_LISTED
        ]:
            fix = v["fixed"] or "no fix listed"
            lines.append(f"- {v['severity']} {v['id']} in {v['package']} {v['installed']} ({fix})")

    lines += ["", "## SBOM", ""]
    cdx, spdx = directory / "sbom.cdx.json", directory / "sbom.spdx.json"
    for label, path, counter in (("CycloneDX", cdx, count_cyclonedx), ("SPDX", spdx, count_spdx)):
        if path.exists():
            lines.append(f"- {label}: {counter(load_json(path))} entries ({path.name})")
        else:
            lines.append(f"- {label}: missing ({path.name} not found)")
            exit_code = max(exit_code, 2)

    if fail_on:
        threshold = SEVERITIES.index(fail_on)
        blocking = sum(1 for v in vulns if SEVERITIES.index(v["severity"]) >= threshold)
        lines += ["", f"Gate: {blocking} finding(s) at or above {fail_on}."]
        if blocking and exit_code == 0:
            exit_code = 1
    lines += [
        "",
        "This summary lists what the scanner found. It does not say the image is safe to deploy.",
    ]
    return "\n".join(lines), exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else "")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--fail-on", choices=SEVERITIES[1:])
    args = parser.parse_args(argv)
    try:
        text, code = summarize(args.directory, args.fail_on)
    except EvidenceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
