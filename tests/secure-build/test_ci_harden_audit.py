"""Tests for ci-harden/scripts/ci_audit.py on synthetic workflow and pipeline files."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[2] / "plugins" / "secure-build" / "skills" / "ci-harden"
SPEC = importlib.util.spec_from_file_location("ci_audit", SKILL / "scripts" / "ci_audit.py")
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
sys.modules["ci_audit"] = audit
SPEC.loader.exec_module(audit)

SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64


def gh(text: str, tmp_path: Path) -> list:
    path = tmp_path / ".github" / "workflows" / "ci.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return audit.check_github(path, text)


def gl(text: str, tmp_path: Path) -> list:
    path = tmp_path / ".gitlab-ci.yml"
    path.write_text(text)
    return audit.check_gitlab(path, text)


def rules(findings: list) -> list[str]:
    return [f.rule for f in findings]


GOOD_GITHUB = f"""name: ci
on:
  pull_request:
permissions: {{}}
jobs:
  test:
    runs-on: ubuntu-24.04
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@{SHA} # v4
        with:
          persist-credentials: false
      - name: Run
        env:
          TITLE: ${{{{ github.event.pull_request.title }}}}
        run: echo "$TITLE"
"""

# ---------------------------------------------------------------- GitHub


def test_good_workflow_is_clean(tmp_path: Path) -> None:
    assert gh(GOOD_GITHUB, tmp_path) == []


@pytest.mark.parametrize(
    ("ref", "severity"),
    [
        ("thirdparty/tool@v1", "error"),
        ("actions/checkout@v4", "warning"),
        ("github/codeql-action/init@main", "warning"),
        ("org/repo/.github/workflows/x.yml@main", "error"),
    ],
)
def test_unpinned_uses(tmp_path: Path, ref: str, severity: str) -> None:
    text = f"permissions: {{}}\njobs:\n  a:\n    steps:\n      - uses: {ref}\n"
    found = [f for f in gh(text, tmp_path) if f.rule == "GHA001"]
    assert [f.severity for f in found] == [severity]


def test_pinned_local_and_digest_uses_pass(tmp_path: Path) -> None:
    text = (
        "permissions: {}\njobs:\n  a:\n    steps:\n"
        f"      - uses: org/tool@{SHA}\n"
        "      - uses: ./.github/actions/local\n"
        f"      - uses: docker://alpine@{DIGEST}\n"
    )
    assert "GHA001" not in rules(gh(text, tmp_path))


def test_docker_uses_without_digest_warns(tmp_path: Path) -> None:
    text = "permissions: {}\njobs:\n  a:\n    steps:\n      - uses: docker://alpine:3.20\n"
    assert [f.severity for f in gh(text, tmp_path) if f.rule == "GHA001"] == ["warning"]


def test_checkout_without_persist_credentials_is_info(tmp_path: Path) -> None:
    text = f"permissions: {{}}\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@{SHA}\n"
    assert "GHA008" in rules(gh(text, tmp_path))


def test_missing_permissions_blocks_flag_each_job(tmp_path: Path) -> None:
    text = (
        "jobs:\n  a:\n    runs-on: x\n    steps: []\n"
        "  b:\n    runs-on: x\n    permissions:\n      contents: read\n"
        "  c:\n    uses: ./.github/workflows/r.yml\n"
    )
    found = [f for f in gh(text, tmp_path) if f.rule == "GHA002"]
    assert [f.message.split("'")[1] for f in found] == ["a", "c"]


def test_workflow_level_permissions_cover_all_jobs(tmp_path: Path) -> None:
    text = "permissions:\n  contents: read\njobs:\n  a:\n    runs-on: x\n"
    assert "GHA002" not in rules(gh(text, tmp_path))


def test_write_all_is_error(tmp_path: Path) -> None:
    text = "permissions: write-all\njobs:\n  a:\n    runs-on: x\n"
    found = [f for f in gh(text, tmp_path) if f.rule == "GHA002"]
    assert [f.severity for f in found] == ["error"]


def test_pull_request_target_warns_and_head_checkout_errors(tmp_path: Path) -> None:
    safe = "on:\n  pull_request_target:\npermissions: {}\njobs:\n  a:\n    runs-on: x\n"
    assert [f.severity for f in gh(safe, tmp_path) if f.rule == "GHA003"] == ["warning"]
    unsafe = safe + (
        f"    steps:\n      - uses: actions/checkout@{SHA}\n        with:\n"
        "          ref: ${{ github.event.pull_request.head.sha }}\n"
    )
    assert sorted(f.severity for f in gh(unsafe, tmp_path) if f.rule == "GHA003") == [
        "error",
        "warning",
    ]


def test_head_checkout_without_pull_request_target_is_not_flagged(tmp_path: Path) -> None:
    text = (
        "on:\n  pull_request:\npermissions: {}\njobs:\n  a:\n    steps:\n"
        f"      - uses: actions/checkout@{SHA}\n        with:\n"
        "          ref: ${{ github.event.pull_request.head.sha }}\n"
    )
    assert "GHA003" not in rules(gh(text, tmp_path))


@pytest.mark.parametrize(
    "line",
    [
        "credentials_json: ${{ secrets.GCP_SA_KEY }}",
        "GOOGLE_APPLICATION_CREDENTIALS: /tmp/key.json",
        "AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET }}",
        "run: gcloud auth activate-service-account --key-file key.json",
    ],
)
def test_long_lived_credentials(tmp_path: Path, line: str) -> None:
    text = f"permissions: {{}}\njobs:\n  a:\n    steps:\n      - {line}\n"
    assert "GHA005" in rules(gh(text, tmp_path))


def test_workload_identity_auth_is_not_flagged(tmp_path: Path) -> None:
    text = (
        "permissions: {}\njobs:\n  a:\n    steps:\n"
        f"      - uses: google-github-actions/auth@{SHA}\n        with:\n"
        "          workload_identity_provider: ${{ vars.WIF }}\n"
    )
    assert "GHA005" not in rules(gh(text, tmp_path))


@pytest.mark.parametrize(
    ("body", "flagged"),
    [
        ('echo "${{ github.event.pull_request.title }}"', True),
        ('echo "${{ github.head_ref }}"', True),
        ('echo "${{ github.event.head_commit.message }}"', True),
        ('echo "${{ github.event.comment.body }}"', True),
        ('echo "${{ github.sha }}"', False),
        ('echo "${{ github.repository }}"', False),
        ('echo "$TITLE"', False),
    ],
)
def test_script_injection_inline_and_block(tmp_path: Path, body: str, flagged: bool) -> None:
    inline = f"permissions: {{}}\njobs:\n  a:\n    steps:\n      - run: {body}\n"
    block = (
        "permissions: {}\njobs:\n  a:\n    steps:\n      - run: |\n"
        f"          set -e\n          {body}\n"
    )
    assert ("GHA006" in rules(gh(inline, tmp_path))) is flagged
    assert ("GHA006" in rules(gh(block, tmp_path))) is flagged


def test_untrusted_value_in_env_is_not_flagged(tmp_path: Path) -> None:
    assert "GHA006" not in rules(gh(GOOD_GITHUB, tmp_path))


def test_secrets_inherit_and_unsafe_commands(tmp_path: Path) -> None:
    text = (
        "permissions: {}\njobs:\n  a:\n    uses: ./.github/workflows/r.yml\n    secrets: inherit\n"
        "env:\n  ACTIONS_ALLOW_UNSECURE_COMMANDS: true\n"
    )
    found = rules(gh(text, tmp_path))
    assert "GHA007" in found
    assert "GHA013" in found


def test_comments_are_ignored(tmp_path: Path) -> None:
    text = "# uses: thirdparty/tool@v1\npermissions: {}\njobs:\n  a:\n    runs-on: x\n"
    assert gh(text, tmp_path) == []


# ---------------------------------------------------------------- GitLab


GOOD_GITLAB = f"""variables:
  IMAGE: registry.example.com/app
build:
  image:
    name: moby/buildkit@{DIGEST}
    entrypoint: [""]
  id_tokens:
    GCP_ID_TOKEN:
      aud: wif
  script:
    - echo "$CI_COMMIT_SHA"
"""


def test_good_pipeline_is_clean(tmp_path: Path) -> None:
    assert gl(GOOD_GITLAB, tmp_path) == []


@pytest.mark.parametrize(
    ("snippet", "expected"),
    [
        ("image: node:20", 1),
        (f"image: node:20@{DIGEST}", 0),
        ("image:\n    name: node:20\n    entrypoint: ['']", 1),
        ("image: $BASE_IMAGE", 1),
        ("services:\n    - docker:dind", 1),
        (f"services:\n    - name: docker:29-dind@{DIGEST}\n      alias: docker", 0),
    ],
)
def test_image_pinning(tmp_path: Path, snippet: str, expected: int) -> None:
    text = f"job:\n  {snippet}\n  script:\n    - true\n"
    found = [f for f in gl(text, tmp_path) if f.rule == "GLC001"]
    assert len(found) == expected


def test_variable_image_is_info_not_warning(tmp_path: Path) -> None:
    found = [f for f in gl("job:\n  image: $BASE\n  script: [x]\n", tmp_path) if f.rule == "GLC001"]
    assert [f.severity for f in found] == ["info"]


def test_dind_service_gets_runner_note(tmp_path: Path) -> None:
    text = f"job:\n  services:\n    - docker:dind@{DIGEST}\n  script: [x]\n"
    assert "GLC010" in rules(gl(text, tmp_path))


def test_includes(tmp_path: Path) -> None:
    text = (
        "include:\n"
        "  - remote: https://example.com/ci.yml\n"
        "  - project: grp/shared\n    file: /a.yml\n"
        f"  - project: grp/pinned\n    file: /a.yml\n    ref: {SHA}\n"
        "  - template: Jobs/SAST.gitlab-ci.yml\n"
        "  - local: /ci/build.yml\n"
        "  - component: gitlab.example.com/grp/comp/build@~latest\n"
        "  - component: gitlab.example.com/grp/comp/test@1.2.0\n"
    )
    found = [f for f in gl(text, tmp_path) if f.rule == "GLC002"]
    messages = " ".join(f.message for f in found)
    assert len(found) == 3
    assert "example.com/ci.yml" in messages
    assert "grp/shared" in messages
    assert "build@~latest" in messages


def test_inline_remote_include(tmp_path: Path) -> None:
    found = gl("include: https://example.com/ci.yml\n", tmp_path)
    assert "GLC002" in rules(found)


@pytest.mark.parametrize(
    ("line", "flagged"),
    [
        ("DB_PASSWORD: hunter2", True),
        ("API_TOKEN: $API_TOKEN", False),
        ("APP_ENV: production", False),
    ],
)
def test_literal_secret_variables(tmp_path: Path, line: str, flagged: bool) -> None:
    text = f"variables:\n  {line}\njob:\n  script: [x]\n"
    assert ("GLC004" in rules(gl(text, tmp_path))) is flagged


def test_debug_trace_environment_dump_and_allow_failure(tmp_path: Path) -> None:
    text = (
        "variables:\n  CI_DEBUG_TRACE: 'true'\n"
        "trivy-scan:\n  allow_failure: true\n  script:\n    - env\n"
        "deploy:\n  allow_failure: true\n  script: [x]\n"
    )
    found = rules(gl(text, tmp_path))
    assert found.count("GLC006") == 1
    assert found.count("GLC007") == 1  # only the scan job, not deploy
    assert found.count("GLC009") == 1


def test_gitlab_long_lived_key_and_missing_id_tokens(tmp_path: Path) -> None:
    text = "job:\n  script:\n    - gcloud auth activate-service-account --key-file $GCP_SA_KEY\n"
    found = rules(gl(text, tmp_path))
    assert "GLC003" in found
    assert "GLC012" in found


def test_cloud_use_with_id_tokens_has_no_glc012(tmp_path: Path) -> None:
    text = "job:\n  id_tokens:\n    T:\n      aud: x\n  script:\n    - gcloud run deploy\n"
    assert "GLC012" not in rules(gl(text, tmp_path))


# ---------------------------------------------------------------- Shared rules


@pytest.mark.parametrize(
    ("line", "rule"),
    [
        ("curl -fsSL https://x.example/i.sh | sh", "CI001"),
        ("docker login -u user -p $PASS registry.example.com", "CI002"),
        ("echo $PASS | docker login -u user --password-stdin registry.example.com", None),
        ("-----BEGIN RSA PRIVATE KEY-----", "CI003"),
        ("key: AKIAABCDEFGHIJKLMNOP", "CI003"),
    ],
)
def test_shared_rules_on_both_platforms(tmp_path: Path, line: str, rule: str | None) -> None:
    github = f"permissions: {{}}\njobs:\n  a:\n    steps:\n      - run: {line}\n"
    gitlab = f"job:\n  script:\n    - {line}\n"
    for found in (gh(github, tmp_path), gl(gitlab, tmp_path)):
        shared = [r for r in rules(found) if r.startswith("CI")]
        assert shared == ([rule] if rule else [])


# ---------------------------------------------------------------- Templates and CLI


def test_shipped_reference_pipelines_pass_their_own_audit() -> None:
    found = audit.run([SKILL / "templates"])
    assert [f.text() for f in found] == []


def test_discover_finds_workflows_and_gitlab_files_only(tmp_path: Path) -> None:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "a.yml").write_text("jobs: {}\n")
    (tmp_path / ".github" / "workflows" / "b.yaml").write_text("jobs: {}\n")
    (tmp_path / ".github" / "dependabot.yml").write_text("version: 2\n")
    (tmp_path / ".gitlab-ci.yml").write_text("job:\n  script: [x]\n")
    (tmp_path / "ci").mkdir()
    (tmp_path / "ci" / "build.gitlab-ci.yml").write_text("job:\n  script: [x]\n")
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    names = sorted(p.name for p, _ in audit.discover([tmp_path], None))
    assert names == [".gitlab-ci.yml", "a.yml", "b.yaml", "build.gitlab-ci.yml"]


def test_unknown_file_needs_platform(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    stray = tmp_path / "pipeline.yml"
    stray.write_text("job:\n  script: [x]\n")
    assert audit.main([str(stray)]) == 2
    assert "--platform" in capsys.readouterr().err
    assert audit.main(["--platform", "gitlab", str(stray)]) == 0


def test_missing_path_exits_two_with_a_fix(capsys: pytest.CaptureFixture[str]) -> None:
    assert audit.main(["/nonexistent/.gitlab-ci.yml"]) == 2
    err = capsys.readouterr().err
    assert "/nonexistent/.gitlab-ci.yml" in err
    assert "Pass a workflow file" in err


def test_exit_codes_and_fail_on(tmp_path: Path) -> None:
    bad = tmp_path / ".gitlab-ci.yml"
    bad.write_text("job:\n  image: node:20\n  script: [x]\n")
    assert audit.main([str(bad)]) == 1
    assert audit.main(["--fail-on", "error", str(bad)]) == 0
    good = tmp_path / "good" / ".gitlab-ci.yml"
    good.parent.mkdir()
    good.write_text(GOOD_GITLAB)
    assert audit.main([str(good)]) == 0


def test_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / ".gitlab-ci.yml"
    bad.write_text("job:\n  image: node:20\n  script: [x]\n")
    audit.main(["--json", str(bad)])
    data = json.loads(capsys.readouterr().out)
    assert {"path", "line", "rule", "severity", "message", "fix"} <= set(data[0])
