"""Tests for image-supply-chain scripts, using fake scanner and cosign programs on PATH."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "secure-build"
    / "skills"
    / "image-supply-chain"
    / "scripts"
)
SPEC = importlib.util.spec_from_file_location(
    "summarize_evidence", SCRIPTS / "summarize_evidence.py"
)
assert SPEC and SPEC.loader
summarize = importlib.util.module_from_spec(SPEC)
sys.modules["summarize_evidence"] = summarize
SPEC.loader.exec_module(summarize)

DIGEST_REF = "us-docker.pkg.dev/proj/repo/app@sha256:" + "c" * 64

TRIVY_REPORT = {
    "Results": [
        {
            "Target": "app (debian 13)",
            "Vulnerabilities": [
                {
                    "VulnerabilityID": "CVE-2000-0001",
                    "PkgName": "libfoo",
                    "InstalledVersion": "1.0",
                    "FixedVersion": "1.1",
                    "Severity": "CRITICAL",
                },
                {
                    "VulnerabilityID": "CVE-2000-0002",
                    "PkgName": "libbar",
                    "InstalledVersion": "2.0",
                    "Severity": "HIGH",
                },
                {
                    "VulnerabilityID": "CVE-2000-0003",
                    "PkgName": "libbaz",
                    "InstalledVersion": "3.0",
                    "Severity": "LOW",
                },
            ],
            "Secrets": [{"RuleID": "aws-access-key-id"}],
        },
        {"Target": "empty"},
    ]
}
GRYPE_REPORT = {
    "matches": [
        {
            "vulnerability": {
                "id": "CVE-2000-0009",
                "severity": "High",
                "fix": {"versions": ["2.1"]},
            },
            "artifact": {"name": "libqux", "version": "2.0"},
        }
    ]
}
CDX = {"bomFormat": "CycloneDX", "components": [{"name": "a"}, {"name": "b"}]}
SPDX = {"spdxVersion": "SPDX-2.3", "packages": [{"name": "a"}, {"name": "b"}, {"name": "c"}]}


def write_evidence(directory: Path, scanner: str = "trivy", sboms: bool = True) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    report = TRIVY_REPORT if scanner == "trivy" else GRYPE_REPORT
    (directory / f"{scanner}.json").write_text(json.dumps(report))
    if sboms:
        (directory / "sbom.cdx.json").write_text(json.dumps(CDX))
        (directory / "sbom.spdx.json").write_text(json.dumps(SPDX))


# ---------------------------------------------------------------- summarize_evidence.py


def test_summary_counts_severities_and_sboms(tmp_path: Path) -> None:
    write_evidence(tmp_path)
    text, code = summarize.summarize(tmp_path, None)
    assert code == 0
    assert "| CRITICAL | 1 | 1 |" in text
    assert "| HIGH | 1 | 0 |" in text
    assert "CycloneDX: 2 entries" in text
    assert "SPDX: 3 entries" in text
    assert "Secrets found in image layers: 1" in text
    assert "CVE-2000-0001 in libfoo 1.0 (1.1)" in text
    assert "no fix listed" in text


def test_gate_fails_at_or_above_threshold(tmp_path: Path) -> None:
    write_evidence(tmp_path)
    assert summarize.summarize(tmp_path, "CRITICAL")[1] == 1
    assert summarize.summarize(tmp_path, "HIGH")[1] == 1


def test_gate_passes_below_threshold(tmp_path: Path) -> None:
    write_evidence(tmp_path, scanner="grype")
    text, code = summarize.summarize(tmp_path, "CRITICAL")
    assert code == 0
    assert "Gate: 0 finding(s) at or above CRITICAL." in text
    assert "CVE-2000-0009 in libqux 2.0 (2.1)" in text


def test_missing_sbom_is_reported_and_exits_two(tmp_path: Path) -> None:
    write_evidence(tmp_path, sboms=False)
    text, code = summarize.summarize(tmp_path, None)
    assert code == 2
    assert "CycloneDX: missing" in text


def test_missing_scan_file_raises_with_the_fix(tmp_path: Path) -> None:
    with pytest.raises(summarize.EvidenceError, match="Run image_evidence.sh first"):
        summarize.summarize(tmp_path, None)


def test_not_a_directory_and_bad_json(tmp_path: Path) -> None:
    with pytest.raises(summarize.EvidenceError, match="not a directory"):
        summarize.summarize(tmp_path / "missing", None)
    (tmp_path / "trivy.json").write_text("{not json")
    with pytest.raises(summarize.EvidenceError, match="not valid JSON"):
        summarize.summarize(tmp_path, None)


def test_main_returns_two_on_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert summarize.main([str(tmp_path / "nope")]) == 2
    assert "error:" in capsys.readouterr().err


# ---------------------------------------------------------------- shell scripts


def make_tool(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run_script(
    name: str, args: list[str], bin_dir: Path, tmp_path: Path
) -> subprocess.CompletedProcess[str]:
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)}
    return subprocess.run(
        ["/bin/sh", str(SCRIPTS / name), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.fixture
def tools(tmp_path: Path) -> Path:
    """A PATH directory with fake trivy, syft and python3 passthrough."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    make_tool(
        bin_dir,
        "trivy",
        'while [ $# -gt 0 ]; do [ "$1" = --output ] && out=$2; shift; done\n'
        f"cat > \"$out\" <<'EOF'\n{json.dumps(TRIVY_REPORT)}\nEOF\n",
    )
    make_tool(
        bin_dir,
        "syft",
        'for a in "$@"; do case "$a" in\n'
        f"cyclonedx-json=*) cat > \"${{a#*=}}\" <<'EOF'\n{json.dumps(CDX)}\nEOF\n;;\n"
        f"spdx-json=*) cat > \"${{a#*=}}\" <<'EOF'\n{json.dumps(SPDX)}\nEOF\n;;\n"
        "esac; done\n",
    )
    make_tool(bin_dir, "python3", f'exec "{sys.executable}" "$@"\n')
    return bin_dir


def test_evidence_script_collects_and_summarizes(tools: Path, tmp_path: Path) -> None:
    out = tmp_path / "evidence"
    result = run_script("image_evidence.sh", [DIGEST_REF, str(out)], tools, tmp_path)
    assert result.returncode == 0, result.stderr
    assert {p.name for p in out.iterdir()} == {"trivy.json", "sbom.cdx.json", "sbom.spdx.json"}
    assert "SPDX: 3 entries" in result.stdout


def test_evidence_script_gate_exit_code(tools: Path, tmp_path: Path) -> None:
    out = tmp_path / "evidence"
    result = run_script(
        "image_evidence.sh", ["--fail-on", "HIGH", DIGEST_REF, str(out)], tools, tmp_path
    )
    assert result.returncode == 1


def test_evidence_script_refuses_a_tag(tools: Path, tmp_path: Path) -> None:
    result = run_script("image_evidence.sh", ["app:latest", str(tmp_path / "o")], tools, tmp_path)
    assert result.returncode == 2
    assert "not a digest reference" in result.stderr
    assert "docker buildx imagetools inspect" in result.stderr


def test_evidence_script_allows_a_tag_with_warning(tools: Path, tmp_path: Path) -> None:
    args = ["--allow-tag", "app:1.0", str(tmp_path / "o")]
    result = run_script("image_evidence.sh", args, tools, tmp_path)
    assert result.returncode == 0
    assert "scanning a tag" in result.stderr


def test_evidence_script_names_a_missing_tool(tools: Path, tmp_path: Path) -> None:
    (tools / "syft").unlink()
    result = run_script("image_evidence.sh", [DIGEST_REF, str(tmp_path / "o")], tools, tmp_path)
    assert result.returncode == 2
    assert "syft is not installed" in result.stderr


@pytest.mark.parametrize(
    "args",
    [[], [DIGEST_REF], ["--scanner", "nessus", DIGEST_REF, "out"], ["--bogus", DIGEST_REF, "out"]],
)
def test_evidence_script_rejects_bad_arguments(
    tools: Path, tmp_path: Path, args: list[str]
) -> None:
    result = run_script("image_evidence.sh", args, tools, tmp_path)
    assert result.returncode == 2
    assert result.stderr.startswith("image_evidence.sh:")


@pytest.fixture
def cosign(tmp_path: Path) -> Path:
    """A fake cosign that records its arguments and exits with $COSIGN_EXIT."""
    bin_dir = tmp_path / "cbin"
    bin_dir.mkdir()
    log = tmp_path / "cosign.log"
    make_tool(bin_dir, "cosign", f'echo "$*" >> "{log}"\nexit "${{COSIGN_EXIT:-0}}"\n')
    return bin_dir


GITHUB_ID = "https://github.com/acme/app/.github/workflows/secure-build.yml@refs/heads/main"
GITLAB_ID = "https://gitlab.com/acme/app//.gitlab-ci.yml@refs/heads/main"


def test_verify_github_pins_identity_and_issuer(cosign: Path, tmp_path: Path) -> None:
    result = run_script(
        "verify_image.sh",
        ["--host", "github", "--identity", GITHUB_ID, DIGEST_REF],
        cosign,
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    logged = (tmp_path / "cosign.log").read_text()
    assert f"verify --certificate-identity {GITHUB_ID}" in logged
    assert "--certificate-oidc-issuer https://token.actions.githubusercontent.com" in logged
    assert logged.strip().endswith(DIGEST_REF)


def test_verify_gitlab_and_attestation(cosign: Path, tmp_path: Path) -> None:
    args = ["--host", "gitlab", "--identity", GITLAB_ID, "--attestation", "cyclonedx", DIGEST_REF]
    result = run_script("verify_image.sh", args, cosign, tmp_path)
    assert result.returncode == 0, result.stderr
    lines = (tmp_path / "cosign.log").read_text().splitlines()
    assert lines[0].startswith("verify ")
    assert lines[1].startswith("verify-attestation --type cyclonedx ")
    assert "--certificate-oidc-issuer https://gitlab.com" in lines[1]


def test_verify_self_managed_gitlab_issuer(cosign: Path, tmp_path: Path) -> None:
    identity = "https://git.example.org/acme/app//.gitlab-ci.yml@refs/heads/main"
    args = [
        "--host",
        "gitlab",
        "--identity",
        identity,
        "--issuer",
        "https://git.example.org",
        DIGEST_REF,
    ]
    result = run_script("verify_image.sh", args, cosign, tmp_path)
    assert result.returncode == 0, result.stderr
    assert (
        "--certificate-oidc-issuer https://git.example.org" in (tmp_path / "cosign.log").read_text()
    )


def test_verify_with_key(cosign: Path, tmp_path: Path) -> None:
    key = "gcpkms://projects/p/locations/l/keyRings/r/cryptoKeys/k"
    result = run_script("verify_image.sh", ["--key", key, DIGEST_REF], cosign, tmp_path)
    assert result.returncode == 0, result.stderr
    assert f"verify --key {key}" in (tmp_path / "cosign.log").read_text()


def test_verify_propagates_cosign_failure(cosign: Path, tmp_path: Path) -> None:
    env_args = ["--host", "github", "--identity", GITHUB_ID, DIGEST_REF]
    env = {"PATH": f"{cosign}:/usr/bin:/bin", "COSIGN_EXIT": "1"}
    result = subprocess.run(
        ["/bin/sh", str(SCRIPTS / "verify_image.sh"), *env_args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 1


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--host", "github", "--identity", GITHUB_ID, "app:latest"], "not a digest reference"),
        (["--host", "github", DIGEST_REF], "needs --identity"),
        (["--host", "github", "--identity", "https://github.com/acme/*", DIGEST_REF], "wildcard"),
        (
            [
                "--host",
                "gitlab",
                "--identity",
                "https://gitlab.com/acme/app/.gitlab-ci.yml",
                DIGEST_REF,
            ],
            "double slash",
        ),
        (["--host", "bitbucket", "--identity", GITHUB_ID, DIGEST_REF], "--host must be"),
        (["--key", "k", "--host", "github", DIGEST_REF], "cannot be combined"),
        (["--identity"], "needs a value"),
    ],
)
def test_verify_fails_closed_before_calling_cosign(
    cosign: Path, tmp_path: Path, args: list[str], message: str
) -> None:
    result = run_script("verify_image.sh", args, cosign, tmp_path)
    assert result.returncode == 2
    assert message in result.stderr
    assert not (tmp_path / "cosign.log").exists()


def test_verify_names_missing_cosign(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = run_script(
        "verify_image.sh",
        ["--host", "github", "--identity", GITHUB_ID, DIGEST_REF],
        empty,
        tmp_path,
    )
    assert result.returncode == 2
    assert "cosign is not installed" in result.stderr


def test_scripts_are_executable() -> None:
    for name in ("image_evidence.sh", "verify_image.sh", "summarize_evidence.py"):
        assert os.access(SCRIPTS / name, os.X_OK), f"{name} must be executable"
