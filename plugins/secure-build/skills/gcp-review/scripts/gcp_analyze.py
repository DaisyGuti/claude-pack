#!/usr/bin/env python3
"""Turn a gcp_collect.py evidence file into findings, gaps and drafted fixes (offline).

Usage:
    gcp_analyze.py evidence.json [--format json|markdown|both] [--out-dir DIR]
                   [--key-max-age-days 90] [--benchmark-map PATH]
                   [--benchmark-edition EDITION] [--fail-on SEVERITY]

The analysis is deterministic: the same evidence file gives the same output. It never calls
gcloud and never runs a fix. The report has three sections: Findings, Not checked (gaps) and
Drafted fixes (not executed). It states configuration evidence only. It never says a project
is compliant, authorized or ready for an authorization decision.

Exit codes: 0 done, 1 --fail-on matched, 2 bad input.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def _load_rules() -> Any:
    """Load the sibling rules module by path, so this works from any working directory."""
    name = "gcp_rules"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parent / "gcp_rules.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}; reinstall the plugin")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rules = _load_rules()

EVIDENCE_SCHEMA = "gcp-review-evidence/1"
FINDINGS_SCHEMA = "gcp-review-findings/1"
SEVERITIES = rules.SEVERITIES
DEFAULT_KEY_MAX_AGE_DAYS = 90  # the common rotation period; override with --key-max-age-days
DEFAULT_BENCHMARK_MAP = Path(__file__).resolve().parent.parent / "references" / "cis-gcp-map.json"

DISCLAIMER = (
    "This report lists configuration evidence, findings and gaps from read-only calls. It does "
    "not state that any project or environment is compliant, authorized or ready for an "
    "authorization decision. A person with the authority makes that decision."
)

# Areas this skill never looks at. Every report prints them so a gap is never silent.
NOT_COVERED = [
    "BigQuery datasets, tables and CMEK (the bq tool is outside this skill)",
    "Cloud SQL database flags and backups, KMS key rotation, Cloud Functions and Dataproc",
    "Cloud Identity or Workspace settings: super admin use, multi-factor authentication, "
    "security keys",
    "Log sinks, log-based metrics and alerts, log bucket retention",
    "Application code, container image contents, runtime behavior and data classification",
    "Anything outside the projects, folders and organizations named in the evidence file",
]


class EvidenceError(ValueError):
    """The evidence file is missing, unreadable or not an evidence document."""


def load_evidence(path: Path) -> Any:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvidenceError(
            f"evidence file {path} does not exist. Run gcp_collect.py with --out {path} first."
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(
            f"evidence file {path} is not readable JSON ({exc}). Re-run gcp_collect.py."
        ) from exc
    found = doc.get("schema") if isinstance(doc, dict) else type(doc).__name__
    if found != EVIDENCE_SCHEMA:
        raise EvidenceError(
            f"{path} is not a {EVIDENCE_SCHEMA} document (found {found!r}). "
            "Create it with gcp_collect.py."
        )
    if not isinstance(doc.get("calls"), list):
        raise EvidenceError(f"{path} has no 'calls' list. Re-run gcp_collect.py.")
    return rules.Evidence(doc)


def attach_benchmark(findings: list[dict[str, Any]], path: Path | None, edition: str | None):
    """Add benchmark IDs from the map file. Returns a small description of what happened."""
    info: dict[str, Any] = {"standard": None, "edition": None, "notice": None}
    if path is None or not path.exists():
        info["notice"] = "No benchmark map was loaded, so findings carry no benchmark IDs."
        return info
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        info["notice"] = f"Benchmark map {path} is unreadable ({exc}); no IDs attached."
        return info
    info["standard"], info["edition"] = doc.get("standard"), doc.get("edition")
    if edition and edition != doc.get("edition"):
        info["notice"] = (
            f"The benchmark map is for edition {doc.get('edition')} and the edition in use is "
            f"{edition}. IDs are left off because numbering changes between editions."
        )
        return info
    info["notice"] = (
        f"Benchmark IDs follow edition {doc.get('edition')} as listed in "
        f"{doc.get('verified_against')}. Confirm each ID against the edition your team holds "
        "before citing it."
    )
    mapping = doc.get("rules") or {}
    for finding in findings:
        finding["benchmark"] = [
            {"standard": doc.get("standard"), "edition": doc.get("edition"), **entry}
            for entry in mapping.get(finding["rule"], [])
        ]
    return info


def build_document(
    evidence: Any, key_max_age_days: int, map_path: Path | None, edition: str | None
) -> dict[str, Any]:
    report = rules.Report(evidence, key_max_age_days)
    rules.run_checks(report)
    benchmark = attach_benchmark(report.findings, map_path, edition)
    counts = {s: sum(1 for f in report.findings if f["severity"] == s) for s in SEVERITIES}
    identity = next(iter(evidence.select("identity")), {})
    return {
        "schema": FINDINGS_SCHEMA,
        "disclaimer": DISCLAIMER,
        "collected_at": evidence.doc.get("collected_at"),
        "scopes": evidence.doc.get("scopes"),
        "identity": identity.get("text") or identity.get("data"),
        "settings": {"key_max_age_days": key_max_age_days},
        "benchmark": benchmark,
        "summary": {"by_severity": counts},
        "findings": report.findings,
        "gaps": report.gaps,
        "not_covered": NOT_COVERED,
    }


def render_markdown(doc: dict[str, Any]) -> str:
    scopes = doc.get("scopes") or {}
    scope_text = "; ".join(f"{k}: {', '.join(v) or 'none'}" for k, v in sorted(scopes.items()))
    lines = [
        "# GCP security review: evidence and gaps",
        "",
        doc["disclaimer"],
        "",
        f"- Collected at: {doc.get('collected_at')}",
        f"- Run as: {str(doc.get('identity') or 'unknown').strip()}",
        f"- Scope: {scope_text}",
        f"- Key age limit used: {doc['settings']['key_max_age_days']} days",
    ]
    if doc["benchmark"].get("notice"):
        lines.append(f"- Benchmark: {doc['benchmark']['notice']}")
    counts = doc["summary"]["by_severity"]
    summary = ", ".join(f"{s} {counts[s]}" for s in SEVERITIES)
    lines += ["", "## Findings", "", f"Summary: {summary}", ""]
    if not doc["findings"]:
        lines += ["No findings from the checks that could run. See the gaps below.", ""]
    for f in doc["findings"]:
        lines += [
            f"### {f['id']} [{f['severity']}] {f['title']} ({f['rule']})",
            "",
            f"- Resource: {f['resource']}",
            f"- Scope: {f['scope']}",
            f"- Evidence: `{f['evidence']}`",
        ]
        lines += [
            f"- Benchmark: {b['standard']} {b['edition']} {b['id']} ({b['title']})"
            for b in f["benchmark"]
        ]
        lines.append("")
    lines += ["## Not checked (gaps)", ""]
    if doc["gaps"]:
        lines += [
            f"- {g['what']}: {g['status']}" + (f" - {g['detail']}" if g["detail"] else "")
            for g in doc["gaps"]
        ]
    else:
        lines.append("- Every call in the battery returned data.")
    lines += ["", "Areas this skill does not look at:", ""]
    lines += [f"- {item}" for item in doc["not_covered"]]
    lines += [
        "",
        "## Drafted fixes (not executed)",
        "",
        "Nothing in this review ran any of these. Each one is a draft for a person to read, "
        "adapt and run through the team's change process.",
        "",
    ]
    drafted = [f for f in doc["findings"] if f["fix"]]
    if not drafted:
        lines.append("No drafted fixes.")
    for f in drafted:
        lines += [f"### {f['id']} {f['title']}", ""]
        if f["fix"]["note"]:
            lines += [f"Note: {f['fix']['note']}", ""]
        if f["fix"]["commands"]:
            lines += ["```sh", *f["fix"]["commands"], "```", ""]
        if f["fix"]["terraform"]:
            lines += ["```hcl", f["fix"]["terraform"], "```", ""]
    return "\n".join(lines).rstrip() + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze GCP review evidence offline.")
    parser.add_argument("evidence", help="evidence JSON written by gcp_collect.py")
    parser.add_argument(
        "--format",
        choices=["json", "markdown", "both"],
        help="default: both with --out-dir, markdown without",
    )
    parser.add_argument("--out-dir", help="write findings.json and report.md here")
    parser.add_argument("--key-max-age-days", type=int, default=DEFAULT_KEY_MAX_AGE_DAYS)
    parser.add_argument("--benchmark-map", default=str(DEFAULT_BENCHMARK_MAP))
    parser.add_argument("--benchmark-edition", help="edition in use; a different one drops IDs")
    parser.add_argument(
        "--fail-on", choices=SEVERITIES, help="exit 1 if a finding is this severe or worse"
    )
    return parser


def _write_outputs(doc: dict[str, Any], out: Path, fmt: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    if fmt in {"json", "both"}:
        (out / "findings.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    if fmt in {"markdown", "both"}:
        (out / "report.md").write_text(render_markdown(doc), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.key_max_age_days < 1:
        print("gcp_analyze: --key-max-age-days must be at least 1.", file=sys.stderr)
        return 2
    try:
        evidence = load_evidence(Path(args.evidence))
    except EvidenceError as exc:
        print(f"gcp_analyze: {exc}", file=sys.stderr)
        return 2
    doc = build_document(
        evidence, args.key_max_age_days, Path(args.benchmark_map), args.benchmark_edition
    )
    fmt = args.format or ("both" if args.out_dir else "markdown")
    if args.out_dir:
        try:
            _write_outputs(doc, Path(args.out_dir), fmt)
        except OSError as exc:
            message = f"cannot write to {args.out_dir}: {exc}. Choose a writable --out-dir."
            print(f"gcp_analyze: {message}", file=sys.stderr)
            return 2
        counts = f"{len(doc['findings'])} findings, {len(doc['gaps'])} gaps"
        print(f"gcp_analyze: wrote {args.out_dir} ({counts})")
    else:
        if fmt in {"json", "both"}:
            print(json.dumps(doc, indent=2))
        if fmt in {"markdown", "both"}:
            print(render_markdown(doc))
    if args.fail_on:
        limit = SEVERITIES.index(args.fail_on)
        if any(SEVERITIES.index(f["severity"]) <= limit for f in doc["findings"]):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
