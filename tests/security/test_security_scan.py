"""Tests for security_scan.py on fixture outputs and stub scanners.

The files in fixtures/raw are real tool outputs from small synthetic projects (a fake API key,
requests 2.19.0, a Dockerfile and a Terraform bucket), trimmed and with paths replaced.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/security/skills/security-scan/scripts/security_scan.py"
RAW = Path(__file__).parent / "fixtures/raw"
FAKE_REPO = Path("/work/repo")


def _load():
    spec = importlib.util.spec_from_file_location("security_scan", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["security_scan"] = module
    spec.loader.exec_module(module)
    return module


ss = _load()


# --- severity ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        ("9.8", "critical"),
        ("9.0", "critical"),
        ("7.5", "high"),
        ("6.1", "medium"),
        ("3.9", "low"),
        ("0", "info"),
        ("", "unknown"),
        (None, "unknown"),
        ("n/a", "unknown"),
    ],
)
def test_cvss_bands(score, expected):
    assert ss.severity_from_cvss(score) == expected


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("CRITICAL", "critical"),
        ("High", "high"),
        ("ERROR", "high"),
        ("WARNING", "medium"),
        ("MODERATE", "medium"),
        ("Negligible", "info"),
        ("weird", "unknown"),
        (None, "unknown"),
    ],
)
def test_label_mapping(label, expected):
    assert ss.severity_from_label(label) == expected


# --- normalizers -------------------------------------------------------------


def test_gitleaks_reports_location_and_never_the_secret(tmp_path):
    raw = tmp_path / "gitleaks-dir.json"
    raw.write_text(
        json.dumps(
            [
                {
                    "RuleID": "generic-api-key",
                    "Description": "Detected a Generic API Key",
                    "StartLine": 7,
                    "File": "/work/repo/app/config.py",
                    "Secret": "FAKE-SECRET-VALUE-0000",
                    "Match": "api_key = 'FAKE-SECRET-VALUE-0000'",
                    "Commit": "abcdef1234567890",
                }
            ]
        )
    )
    (finding,) = ss.parse_gitleaks(raw, FAKE_REPO)
    assert (finding.kind, finding.severity) == ("secret", "high")
    assert (finding.file, finding.line, finding.rule) == ("app/config.py", 7, "generic-api-key")
    assert "abcdef123456" in finding.note
    assert "FAKE-SECRET-VALUE-0000" not in json.dumps(finding.as_dict())


def test_gitleaks_real_output_fixture():
    (finding,) = ss.parse_gitleaks(RAW / "gitleaks-dir.json", FAKE_REPO)
    assert finding.file == "app/config.py"
    assert finding.line == 1


def test_osv_groups_become_findings_with_fix_versions():
    findings = ss.parse_osv(RAW / "osv-scanner.json", FAKE_REPO)
    by_cve = {next(i for i in f.ids if i.startswith("CVE-")): f for f in findings}
    assert set(by_cve) == {"CVE-2018-18074", "CVE-2023-32681"}
    high = by_cve["CVE-2018-18074"]
    assert high.severity == "high"
    assert by_cve["CVE-2023-32681"].severity == "medium"
    assert high.file == "requirements.txt"
    assert (high.package, high.version) == ("requests", "2.19.0")
    assert "2.20.0" in high.fix
    assert {"PYSEC-2018-28", "GHSA-x84v-xcm2-53pg"} <= set(high.ids)


def test_osv_falls_back_to_database_severity_label(tmp_path):
    raw = tmp_path / "osv-scanner.json"
    raw.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "source": {"path": "go.mod"},
                        "packages": [
                            {
                                "package": {"name": "m", "version": "1"},
                                "groups": [{"ids": ["GHSA-aaaa"], "aliases": []}],
                                "vulnerabilities": [
                                    {
                                        "id": "GHSA-aaaa",
                                        "database_specific": {"severity": "CRITICAL"},
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        )
    )
    (finding,) = ss.parse_osv(raw, FAKE_REPO)
    assert finding.severity == "critical"
    assert finding.fix == ""


def test_grype_paths_are_scan_root_relative_and_cves_are_collected():
    findings = ss.parse_grype(RAW / "grype.json", FAKE_REPO)
    first = findings[0]
    assert first.file == "requirements.txt"
    assert "CVE-2018-18074" in first.ids
    assert first.title.endswith("CVE-2018-18074")
    assert first.fix == "Upgrade requests to 2.20.0."


def test_semgrep_maps_severity_and_cwe_and_drops_source_lines(tmp_path):
    (finding,) = ss.parse_semgrep(RAW / "semgrep.json", FAKE_REPO)
    assert (finding.kind, finding.severity) == ("code", "high")
    assert (finding.file, finding.line, finding.rule) == ("app.py", 3, "demo-shell-true")
    assert finding.ids == ["CWE-78"]
    raw = tmp_path / "semgrep.json"
    raw.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "check_id": "r",
                        "path": "a.py",
                        "start": {"line": 1},
                        "extra": {
                            "message": "m",
                            "severity": "INFO",
                            "lines": "token=FAKE-LINE-0001",
                        },
                    }
                ]
            }
        )
    )
    (info,) = ss.parse_semgrep(raw, FAKE_REPO)
    assert info.severity == "low"
    assert "FAKE-LINE-0001" not in json.dumps(info.as_dict())


def test_trivy_reports_dependencies_and_failed_misconfigurations_only(tmp_path):
    findings = ss.parse_trivy(RAW / "trivy.json", FAKE_REPO)
    kinds = {f.kind for f in findings}
    assert kinds == {"dependency", "iac"}
    dep = next(f for f in findings if f.kind == "dependency")
    assert dep.package == "requests" and "2.20.0" in dep.fix
    iac = next(f for f in findings if f.rule == "AWS-0086")
    assert (iac.file, iac.line, iac.severity) == ("main.tf", 1, "high")
    raw = tmp_path / "trivy.json"
    raw.write_text(
        json.dumps(
            {"Results": [{"Target": "x", "Misconfigurations": [{"ID": "X", "Status": "PASS"}]}]}
        )
    )
    assert ss.parse_trivy(raw, FAKE_REPO) == []


def test_checkov_list_output_assumes_severity_and_strips_root_slash():
    findings = ss.parse_checkov(RAW / "checkov.json", FAKE_REPO)
    assert findings
    assert {f.kind for f in findings} == {"iac"}
    assert all(f.severity == "medium" and "assumed" in f.note for f in findings)
    assert {f.file for f in findings} <= {"main.tf", "Dockerfile"}
    assert next(f for f in findings if f.file == "main.tf").line == 1


def test_checkov_accepts_a_single_object_and_a_real_severity(tmp_path):
    raw = tmp_path / "checkov.json"
    raw.write_text(
        json.dumps(
            {
                "check_type": "terraform",
                "results": {
                    "failed_checks": [
                        {
                            "check_id": "CKV_X",
                            "check_name": "n",
                            "file_path": "/a.tf",
                            "file_line_range": [3, 9],
                            "severity": "HIGH",
                        }
                    ]
                },
            }
        )
    )
    (finding,) = ss.parse_checkov(raw, FAKE_REPO)
    assert (finding.severity, finding.line, finding.note) == ("high", 3, "")


def test_unreadable_json_raises_a_clear_error(tmp_path):
    raw = tmp_path / "semgrep.json"
    raw.write_text("not json")
    with pytest.raises(ValueError, match="semgrep.json"):
        ss.parse_semgrep(raw, FAKE_REPO)


# --- de-duplication ----------------------------------------------------------


def _all_fixture_findings():
    return (
        ss.parse_gitleaks(RAW / "gitleaks-dir.json", FAKE_REPO)
        + ss.parse_osv(RAW / "osv-scanner.json", FAKE_REPO)
        + ss.parse_grype(RAW / "grype.json", FAKE_REPO)
        + ss.parse_semgrep(RAW / "semgrep.json", FAKE_REPO)
        + ss.parse_trivy(RAW / "trivy.json", FAKE_REPO)
        + ss.parse_checkov(RAW / "checkov.json", FAKE_REPO)
    )


def test_three_dependency_scanners_collapse_to_one_finding():
    merged = ss.dedupe(_all_fixture_findings())
    hits = [f for f in merged if "CVE-2018-18074" in f.ids and f.package == "requests"]
    assert len(hits) == 1
    assert hits[0].tools == ["grype", "osv-scanner", "trivy"]
    assert hits[0].fix.startswith("Upgrade requests")
    assert merged[0].severity == "high"


def test_dedupe_keeps_different_versions_apart_and_numbers_by_severity():
    a = ss.Finding("dependency", "low", "t", package="p", version="1", ids=["CVE-1"], tools=["a"])
    b = ss.Finding("dependency", "high", "t", package="p", version="2", ids=["CVE-1"], tools=["b"])
    merged = ss.dedupe([a, b])
    assert [f.version for f in merged] == ["2", "1"]
    assert [f.finding_id for f in merged] == ["SS-001", "SS-002"]


def test_dedupe_merges_the_same_secret_seen_by_two_gitleaks_passes():
    a = ss.Finding("secret", "high", "k", file="a.py", line=1, tools=["gitleaks"])
    b = ss.Finding("secret", "high", "k", file="a.py", line=1, tools=["gitleaks"], note="commit 1")
    (only,) = ss.dedupe([a, b])
    assert only.note == "commit 1"


def test_dedupe_takes_the_worse_severity_when_tools_disagree():
    a = ss.Finding(
        "dependency", "medium", "t", package="p", version="1", ids=["CVE-9"], tools=["a"]
    )
    b = ss.Finding(
        "dependency", "critical", "t", package="P", version="1", ids=["CVE-9"], tools=["b"]
    )
    (only,) = ss.dedupe([a, b])
    assert only.severity == "critical"


# --- merge command -----------------------------------------------------------


def test_merge_writes_report_and_json(tmp_path, capsys):
    out = tmp_path / "out"
    code = ss.main(["merge", "--raw", str(RAW), "--repo", str(FAKE_REPO), "--out", str(out)])
    assert code == 0
    report = (out / "SECURITY-SCAN.md").read_text()
    assert "## Coverage" in report and "SS-001" in report
    assert "app/config.py:1" in report
    data = json.loads((out / "findings.json").read_text())
    assert {t["name"]: t["status"] for t in data["tools"]}["gitleaks"] == "ran"
    assert data["findings"][0]["severity"] in {"high", "critical"}
    assert "FAKE" not in report


def test_merge_marks_tools_without_raw_output_as_not_run(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    shutil.copy(RAW / "semgrep.json", raw / "semgrep.json")
    out = tmp_path / "out"
    assert ss.main(["merge", "--raw", str(raw), "--repo", str(FAKE_REPO), "--out", str(out)]) == 0
    status = {
        t["name"]: t["status"] for t in json.loads((out / "findings.json").read_text())["tools"]
    }
    assert status["semgrep"] == "ran"
    assert status["osv-scanner"] == "not run"


def test_merge_with_a_corrupt_file_marks_that_tool_failed_and_keeps_the_rest(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    shutil.copy(RAW / "semgrep.json", raw / "semgrep.json")
    (raw / "trivy.json").write_text("{broken")
    out = tmp_path / "out"
    assert ss.main(["merge", "--raw", str(raw), "--repo", str(FAKE_REPO), "--out", str(out)]) == 0
    tools = {t["name"]: t for t in json.loads((out / "findings.json").read_text())["tools"]}
    assert tools["trivy"]["status"] == "failed"
    assert "trivy.json" in tools["trivy"]["detail"]
    assert tools["semgrep"]["count"] == 1


def test_fail_on_sets_exit_code_one_only_at_or_above_the_threshold(tmp_path):
    args = ["merge", "--raw", str(RAW), "--repo", str(FAKE_REPO)]
    assert ss.main([*args, "--out", str(tmp_path / "a"), "--fail-on", "high"]) == 1
    assert ss.main([*args, "--out", str(tmp_path / "b"), "--fail-on", "critical"]) == 0


def test_merge_without_a_raw_directory_is_a_usage_error(tmp_path, capsys):
    code = ss.main(["merge", "--raw", str(tmp_path / "missing"), "--repo", str(tmp_path)])
    assert code == 2
    assert "not a directory" in capsys.readouterr().err


def test_unknown_tool_name_is_rejected_with_the_valid_choices(tmp_path):
    with pytest.raises(SystemExit) as exc:
        ss.main(["run", "--repo", str(tmp_path), "--tools", "nessus"])
    assert "unknown tool" in str(exc.value) and "gitleaks" in str(exc.value)


# --- run command with stub scanners -------------------------------------------


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _stub_bin_dir(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # gitleaks: copy the fixture to the --report-path argument.
    _stub(
        bin_dir,
        "gitleaks",
        f'''[ "$1" = "version" ] && {{ echo "8.0-stub"; exit 0; }}
while [ $# -gt 0 ]; do [ "$1" = "--report-path" ] && dest="$2"; shift; done
/bin/cp "{RAW}/gitleaks-dir.json" "$dest"
''',
    )
    # semgrep: print the fixture to stdout.
    _stub(
        bin_dir,
        "semgrep",
        f'''[ "$1" = "--version" ] && {{ echo "1.0-stub"; exit 0; }}
/bin/cat "{RAW}/semgrep.json"
''',
    )
    # grype: crash.
    _stub(
        bin_dir, "grype", '[ "$1" = "version" ] && { echo stub; exit 0; }\necho boom >&2\nexit 3\n'
    )
    return bin_dir


def test_run_uses_installed_tools_and_reports_the_rest(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(ss.tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("PATH", str(_stub_bin_dir(tmp_path)))
    assert ss.main(["run", "--repo", str(repo), "--tools", "gitleaks,semgrep,grype,trivy"]) == 0
    captured = capsys.readouterr()
    assert "trivy: not installed" in captured.err
    assert "grype: failed" in captured.err and "boom" in captured.err
    (scan_dir,) = list(scratch.iterdir())  # the report lands outside the repository
    assert scan_dir.name.startswith("security-scan-repo-")
    assert list(repo.iterdir()) == []
    data = json.loads((scan_dir / "findings.json").read_text())
    status = {t["name"]: t["status"] for t in data["tools"]}
    assert status == {
        "gitleaks": "ran",
        "semgrep": "ran",
        "grype": "failed",
        "trivy": "not installed",
    }
    assert {f["kind"] for f in data["findings"]} == {"secret", "code"}
    assert "2 high" in captured.out  # the fake key and the shell=True finding


def test_an_out_directory_inside_the_repository_is_warned_about(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("PATH", str(_stub_bin_dir(tmp_path)))
    ss.main(["run", "--repo", str(repo), "--tools", "semgrep", "--out", str(repo / "reports")])
    assert "inside the repository" in capsys.readouterr().err


def test_a_failed_history_pass_keeps_the_working_tree_result(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(
        bin_dir,
        "gitleaks",
        f"""[ "$1" = "version" ] && {{ echo "8.0-stub"; exit 0; }}
[ "$1" = "git" ] && {{ echo "fatal: no commits" >&2; exit 1; }}
while [ $# -gt 0 ]; do [ "$1" = "--report-path" ] && dest="$2"; shift; done
/bin/cp "{RAW}/gitleaks-dir.json" "$dest"
""",
    )
    monkeypatch.setenv("PATH", str(bin_dir))
    out = tmp_path / "out"
    assert ss.main(["run", "--repo", str(repo), "--tools", "gitleaks", "--out", str(out)]) == 0
    tool = json.loads((out / "findings.json").read_text())["tools"][0]
    assert tool["status"] == "ran" and tool["count"] == 1
    assert "gitleaks-git.json pass lost" in tool["detail"] and "no commits" in tool["detail"]
    assert "pass lost" in (out / "SECURITY-SCAN.md").read_text()


def test_a_long_report_details_the_top_findings_and_tables_the_rest(tmp_path):
    findings = [
        ss.Finding("code", "low", f"issue {i}", file=f"f{i}.py", line=1, rule=f"r{i}")
        for i in range(ss.MAX_DETAILED_FINDINGS + 5)
    ]
    merged = ss.dedupe(findings)
    text = ss.render_markdown(Path("/work/repo"), [], merged, "now")
    assert text.count("### SS-") == ss.MAX_DETAILED_FINDINGS
    assert "Remaining 5 finding(s)" in text and "| SS-205 |" in text


def test_run_with_no_tools_installed_exits_two_with_install_hints(tmp_path, monkeypatch, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    code = ss.main(["run", "--repo", str(tmp_path), "--out", str(tmp_path / "out")])
    assert code == 2
    err = capsys.readouterr().err
    assert "brew install gitleaks" in err
    assert "no scanner produced a result" in err


def test_run_times_out_a_hung_tool_and_keeps_going(tmp_path, monkeypatch, capsys):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir, "semgrep", '[ "$1" = "--version" ] && { echo v; exit 0; }\n/bin/sleep 30\n')
    _stub(
        bin_dir,
        "checkov",
        '[ "$1" = "--version" ] && { echo v; exit 0; }\necho "[]"\n',
    )
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}/bin")
    repo = tmp_path / "repo"
    repo.mkdir()
    code = ss.main(
        [
            "run",
            "--repo",
            str(repo),
            "--out",
            str(tmp_path / "o"),
            "--tools",
            "semgrep,checkov",
            "--timeout",
            "1",
        ]
    )
    assert code == 0
    assert "timed out after 1 seconds" in capsys.readouterr().err


def test_detect_lists_every_tool_with_install_hints(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert ss.main(["detect", "--json"]) == 0
    tools = json.loads(capsys.readouterr().out)
    assert {t["name"] for t in tools} == set(ss.TOOLS)
    assert all(t["status"] == "not installed" and t["detail"] for t in tools)


def test_gitleaks_scans_history_only_when_the_repo_has_git(tmp_path):
    raw = tmp_path / "raw"
    plain = ss.TOOLS["gitleaks"].commands(tmp_path, raw, "")
    assert [name for name, _, _ in plain] == ["gitleaks-dir.json"]
    (tmp_path / ".git").mkdir()
    with_git = ss.TOOLS["gitleaks"].commands(tmp_path, raw, "")
    assert [name for name, _, _ in with_git] == ["gitleaks-dir.json", "gitleaks-git.json"]
    assert all("--redact" in argv for _, argv, _ in with_git)


def test_semgrep_never_sends_metrics_and_accepts_a_local_rule_directory(tmp_path):
    (_, argv, _) = ss.TOOLS["semgrep"].commands(tmp_path, tmp_path, "rules/")[0]
    assert argv[argv.index("--metrics") + 1] == "off"
    assert argv[argv.index("--config") + 1] == "rules/"
    (_, default_argv, _) = ss.TOOLS["semgrep"].commands(tmp_path, tmp_path, "")[0]
    assert default_argv[default_argv.index("--config") + 1] == ss.DEFAULT_SEMGREP_CONFIG


def test_a_secret_sorts_before_a_dependency_of_the_same_severity():
    dep = ss.Finding("dependency", "high", "d", file="a", package="p", version="1", ids=["CVE-1"])
    secret = ss.Finding("secret", "high", "s", file="z.py", line=1)
    assert [f.kind for f in ss.dedupe([dep, secret])] == ["secret", "dependency"]


def test_version_is_the_first_dotted_number_in_the_tool_output(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir, "grype", 'echo "Application:  grype"\necho "Version:  0.120.1"\n')
    monkeypatch.setenv("PATH", str(bin_dir))
    assert ss.tool_version(ss.TOOLS["grype"]) == "0.120.1"


# --- --changed-since ---------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


@pytest.fixture
def branch_repo(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.py").write_text("x = 1\n")
    (repo / "b.py").write_text("y = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "checkout", "-q", "-b", "feature")
    (repo / "a.py").write_text("x = 2\n")
    _git(repo, "commit", "-qam", "change a")
    (repo / "c.py").write_text("z = 1\n")  # untracked
    raw = tmp_path / "raw"
    raw.mkdir()
    results = [
        {
            "check_id": "r",
            "path": name,
            "start": {"line": 1},
            "extra": {"message": "m", "severity": "ERROR"},
        }
        for name in ("a.py", "b.py", "c.py")
    ]
    (raw / "semgrep.json").write_text(json.dumps({"results": results}))
    return repo, raw


def test_changed_since_keeps_committed_and_untracked_changes_only(branch_repo, tmp_path):
    repo, raw = branch_repo
    out = tmp_path / "out"
    code = ss.main(
        [
            "merge",
            "--raw",
            str(raw),
            "--repo",
            str(repo),
            "--out",
            str(out),
            "--changed-since",
            "main",
        ]
    )
    assert code == 0
    data = json.loads((out / "findings.json").read_text())
    assert [f["file"] for f in data["findings"]] == ["a.py", "c.py"]
    assert [f["id"] for f in data["findings"]] == ["SS-001", "SS-002"]
    assert "1 finding(s) elsewhere" in data["filter"]
    assert "- Filter:" in (out / "SECURITY-SCAN.md").read_text()


def test_changed_since_with_an_unknown_ref_refuses_instead_of_showing_everything(
    branch_repo, tmp_path, capsys
):
    repo, raw = branch_repo
    code = ss.main(
        [
            "merge",
            "--raw",
            str(raw),
            "--repo",
            str(repo),
            "--out",
            str(tmp_path / "o"),
            "--changed-since",
            "no-such-ref",
        ]
    )
    assert code == 2
    assert "--changed-since no-such-ref" in capsys.readouterr().err
    assert not (tmp_path / "o" / "findings.json").exists()


# --- suppression files ---------------------------------------------------------


def test_suppression_files_are_listed_so_a_reviewer_reads_them(tmp_path):
    repo = tmp_path / "repo"
    (repo / "svc").mkdir(parents=True)
    (repo / "node_modules" / "x").mkdir(parents=True)
    (repo / ".gitleaksignore").write_text("a:b:1\n")
    (repo / "svc" / ".semgrepignore").write_text("tests/\n")
    (repo / "node_modules" / "x" / ".trivyignore").write_text("CVE-1\n")
    assert ss.find_suppression_files(repo) == [".gitleaksignore", "svc/.semgrepignore"]
    out = tmp_path / "out"
    raw = tmp_path / "raw"
    raw.mkdir()
    shutil.copy(RAW / "semgrep.json", raw / "semgrep.json")
    assert ss.main(["merge", "--raw", str(raw), "--repo", str(repo), "--out", str(out)]) == 0
    assert "- `svc/.semgrepignore`" in (out / "SECURITY-SCAN.md").read_text()
    data = json.loads((out / "findings.json").read_text())
    assert data["suppression_files"] == [".gitleaksignore", "svc/.semgrepignore"]
