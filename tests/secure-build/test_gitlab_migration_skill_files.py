"""Structure and style checks for the gitlab-migration skill, its evals and its template."""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/secure-build"
SKILL = PLUGIN / "skills/gitlab-migration"
SKILL_MD = SKILL / "SKILL.md"
EVALS = PLUGIN / "evals"
THIS_TEST_DIR = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location(
    "gitlab_migration_inventory_for_files", SKILL / "scripts/inventory_github_repo.py"
)
assert _spec and _spec.loader
_inv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_inv)

ALLOWED_SKILL_FIELDS = {
    "name",
    "description",
    "when_to_use",
    "argument-hint",
    "arguments",
    "disable-model-invocation",
    "user-invocable",
    "allowed-tools",
    "disallowed-tools",
    "model",
    "effort",
    "context",
    "agent",
    "background",
    "hooks",
    "paths",
    "shell",
    "license",
    "compatibility",
    "metadata",
}
GRADER_TYPES = {"regex", "tool_used", "tool_order", "file_exists", "llm", "baseline"}
PROMPT_FIELDS = {
    "schema_version",
    "name",
    "description",
    "tags",
    "plugins",
    "runs",
    "expected_outcome",
    "model",
    "max_turns",
    "timeout_seconds",
    "allowed_tools",
    "append_system_prompt",
    "env",
}


def _split_frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    assert lines[0] == "---", f"{path}: the opening --- must be line 1"
    end = lines.index("---", 1)
    front = _inv.parse_yaml_subset("\n".join(lines[1:end])) or {}
    return front, "\n".join(lines[end + 1 :])


def _skill_text_files() -> list[Path]:
    files = [SKILL_MD, *sorted((SKILL / "references").glob("*.md"))]
    files += sorted((SKILL / "scripts").glob("*.py"))
    files += sorted(EVALS.glob("gitlab-migration-*/**/*.md"))
    return files


def _eval_cases() -> list[Path]:
    return sorted(p for p in EVALS.glob("gitlab-migration-*") if p.is_dir())


# --------------------------------------------------------------------------- SKILL.md


def test_frontmatter_fields_and_name():
    front, _ = _split_frontmatter(SKILL_MD)
    assert set(front) <= ALLOWED_SKILL_FIELDS, set(front) - ALLOWED_SKILL_FIELDS
    assert front["name"] == SKILL.name == "gitlab-migration"
    assert re.fullmatch(r"[a-z0-9-]{1,64}", front["name"])
    assert "claude" not in front["name"] and "anthropic" not in front["name"]


def test_side_effect_skill_is_user_invoked_only():
    front, _ = _split_frontmatter(SKILL_MD)
    assert front["disable-model-invocation"] == "true"


def test_allowed_tools_preapproves_only_the_bundled_scripts():
    front, _ = _split_frontmatter(SKILL_MD)
    assert front["allowed-tools"] == "Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*)"
    body = SKILL_MD.read_text()
    assert "only pre-approves" in body and "restricts nothing" in body


def test_description_rules():
    front, _ = _split_frontmatter(SKILL_MD)
    description = front["description"]
    assert len(description) + len(front.get("when_to_use", "")) < 1536
    assert ": " not in description and " #" not in description, "plain YAML scalar would break"
    assert re.match(r"^[A-Z][a-z]+s\b", description), "third person verb first"
    assert not re.match(r"^(I|You|We)\b", description)
    assert "even if they do not name" in description
    for term in ("GitHub", "GitLab", "GitHub Actions", "Dependabot", "Workload Identity"):
        assert term in description
    assert "Use when" in description


def test_skill_md_size_and_key_rules_first():
    lines = SKILL_MD.read_text().split("\n")
    assert len(lines) < 300
    head = "\n".join(lines[:60])
    assert "Writes wait for a go" in head
    assert "Secrets: names only" in head
    assert "PLAN" in head and "EXECUTE" in head


def test_skill_md_has_plan_and_execute_sections():
    body = SKILL_MD.read_text()
    assert "## PLAN mode" in body and "## EXECUTE mode" in body
    assert "Second confirmation" in body
    assert "disable-model-invocation" in body, "explains why evals have no Skill grader"


def test_skill_md_links_every_reference_and_each_exists():
    body = SKILL_MD.read_text()
    on_disk = {p.name for p in (SKILL / "references").glob("*.md")}
    linked = set(re.findall(r"references/([\w-]+\.md)", body))
    assert linked == on_disk, linked ^ on_disk
    assert "templates/renovate.json" in body
    for name in ("ci-harden", "image-supply-chain", "team-comms"):
        assert f"`{name}`" in body


def test_reference_files_are_one_level_deep_and_have_toc():
    refs = sorted((SKILL / "references").glob("*.md"))
    assert refs
    for ref in refs:
        text = ref.read_text()
        assert ref.parent == SKILL / "references"
        if len(text.split("\n")) > 100:
            assert "## Contents" in text, f"{ref.name} needs a table of contents"
        for anchor in re.findall(r"\]\(#([\w-]+)\)", text):
            headings = {
                re.sub(r"[^\w\- ]", "", h.lstrip("# ").strip().lower()).replace(" ", "-")
                for h in text.split("\n")
                if h.startswith("#")
            }
            assert anchor in headings, f"{ref.name}: contents link #{anchor} has no heading"


def test_references_cite_a_fetch_date():
    for name in (
        "importer.md",
        "actions-to-gitlab-ci.md",
        "gcp-wif-trust.md",
        "repo-settings.md",
        "cutover-and-rollback.md",
        "sources.md",
    ):
        text = (SKILL / "references" / name).read_text()
        assert re.search(r"\b\d{4}-\d{2}-\d{2}\b", text), name
        assert "https://" in text, name


def test_sources_lists_verified_and_unverified():
    text = (SKILL / "references/sources.md").read_text()
    assert "## Verified against the pages" in text
    assert "## Not verified" in text


# --------------------------------------------------------------------- team-safe style


def test_no_personal_or_machine_specific_content():
    banned = [
        "/" + "Users" + "/",
        "~" + "/",
        "dais" + "y",
        "Dais" + "y",
        "guti" + "errez",
        "ECS" + "/",
    ]
    for path in _skill_text_files() + sorted(THIS_TEST_DIR.glob("test_gitlab_migration_*.py")):
        text = path.read_text()
        for item in banned:
            assert item not in text, f"{path.name} contains {item!r}"


def test_no_contrastive_constructions_or_growing_counts():
    contrastive = re.compile(
        r", not |\brather than\b|\bnot just\b|\bnot merely\b|\binstead of typing\b"
    )
    counts = re.compile(
        r"\b(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\s+(?:skills|rules|checks|"
        r"references|scripts|plugins|agents|hooks)\b",
        re.IGNORECASE,
    )
    for path in _skill_text_files():
        text = path.read_text()
        assert not contrastive.search(text), f"{path.name}: {contrastive.search(text).group(0)!r}"
        if path.suffix == ".md":
            assert not counts.search(text), f"{path.name}: {counts.search(text).group(0)!r}"


def test_no_secret_looking_values():
    secret_shapes = re.compile(
        r"(ghp_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}"
        r"|-----BEGIN [A-Z ]*PRIVATE KEY)"
    )
    for path in _skill_text_files() + sorted(THIS_TEST_DIR.glob("test_gitlab_migration_*.py")):
        assert not secret_shapes.search(path.read_text()), path.name


# ------------------------------------------------------------------------------ scripts


@pytest.mark.parametrize("script", sorted((SKILL / "scripts").glob("*.py")), ids=lambda p: p.name)
def test_scripts_are_stdlib_only_executable_with_shebang(script: Path):
    text = script.read_text()
    assert text.startswith("#!/usr/bin/env python3\n")
    assert script.stat().st_mode & 0o111
    tree = ast.parse(text)
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module.split(".")[0])
    assert modules <= set(sys.stdlib_module_names), modules - set(sys.stdlib_module_names)


# ------------------------------------------------------------------------------ template


def test_renovate_template_lives_in_ci_harden_only():
    shared = SKILL.parent / "ci-harden/templates/renovate.json"
    assert json.loads(shared.read_text())["extends"] == ["config:best-practices"]
    assert not (SKILL / "templates/renovate.json").exists()
    assert (SKILL / "../ci-harden/templates/renovate.json").resolve() == shared.resolve()


# --------------------------------------------------------------------------------- evals


def test_at_least_three_cases_with_graders_and_a_near_miss():
    cases = _eval_cases()
    assert len(cases) >= 3
    tags = []
    for case in cases:
        front, body = _split_frontmatter(case / "prompt.md")
        assert set(front) <= PROMPT_FIELDS, (case.name, set(front) - PROMPT_FIELDS)
        assert front["name"] == case.name
        assert front["runs"] == "1"
        assert 1 <= int(front["max_turns"]) <= 200
        assert 1 <= int(front["timeout_seconds"]) <= 3600
        assert front["description"].strip()
        tags += front["tags"]
        assert body.strip()
        graders = sorted((case / "graders").glob("*.md"))
        assert graders, case.name
    assert "near-miss" in tags


def test_prompts_do_not_name_the_skill():
    for case in _eval_cases():
        _, body = _split_frontmatter(case / "prompt.md")
        for word in ("gitlab-migration", "secure-build", "/secure"):
            assert word not in body, (case.name, word)


def test_no_skill_trigger_grader_because_skill_is_user_invoked_only():
    for grader in EVALS.glob("gitlab-migration-*/graders/*.md"):
        front, _ = _split_frontmatter(grader)
        assert not (front.get("type") == "tool_used" and front.get("tool") == "Skill"), grader
    descriptions = " ".join(
        _split_frontmatter(c / "prompt.md")[0]["description"] for c in _eval_cases()
    )
    assert "disable-model-invocation" in descriptions


def test_every_grader_is_well_formed_and_regexes_compile():
    for grader in EVALS.glob("gitlab-migration-*/graders/*.md"):
        front, body = _split_frontmatter(grader)
        assert front["type"] in GRADER_TYPES, grader
        if front["type"] == "llm":
            assert "PASS if" in body and "FAIL if" in body, grader
        if front["type"] == "regex":
            assert front["match"] in {"contains", "not_contains"}
            flags = re.I | re.S if "i" in front.get("flags", "") else 0
            if "s" in front.get("flags", ""):
                flags |= re.S
            re.compile(front["pattern"], flags)
        if front["type"] == "tool_used":
            re.compile(front["input_match"])
            assert front["min"] == "0" and front["max"] == "0"


WRITE_SAMPLES_BLOCKED = [
    "glab repo create grp/proj",
    "glab project create x",
    "glab api --method POST projects/1/hooks",
    "glab api projects/1/protected_branches -X POST -f name=main",
    "glab api projects/1/hooks -f url=https://x.invalid",
    "glab api import/github -F repo_id=1",
    "glab variable set DEPLOY_KEY",
    "glab repo mirror g/p --direction=push",
    "gh repo archive acme/payments",
    "gcloud iam workload-identity-pools providers create-oidc gitlab",
    "gcloud iam service-accounts add-iam-policy-binding sa@x",
    "git push origin main",
]
WRITE_SAMPLES_ALLOWED = [
    "glab auth status",
    "glab api projects/1/import",
    "glab api version",
    "glab variable list",
    "gh repo view acme/payments",
    "gh api repos/acme/payments --jq .id",
    "gcloud iam workload-identity-pools providers list --location=global",
    "gcloud iam service-accounts get-iam-policy sa@x",
    "git status",
]


@pytest.mark.parametrize(
    "case_name", ["gitlab-migration-plan-only", "gitlab-migration-draft-then-confirm"]
)
def test_no_write_grader_blocks_writes_and_allows_reads(case_name: str):
    front, _ = _split_frontmatter(EVALS / case_name / "graders/no-write-calls.md")
    pattern = re.compile(front["input_match"])
    for command in WRITE_SAMPLES_BLOCKED:
        if command.startswith("gcloud") and case_name.endswith("draft-then-confirm"):
            continue  # that case never involves Google Cloud
        assert pattern.search(json.dumps({"command": command})), command
    for command in WRITE_SAMPLES_ALLOWED:
        assert not pattern.search(json.dumps({"command": command})), command


def test_plan_regex_accepts_a_plan_and_rejects_a_ci_answer():
    front, _ = _split_frontmatter(
        EVALS / "gitlab-migration-plan-only/graders/plan-covers-topics.md"
    )
    pattern = re.compile(front["pattern"], re.I | re.S)
    plan = (
        "Importer: carries issues. Workload Identity: add provider with id_tokens. "
        "CODEOWNERS moves. Renovate replaces Dependabot. Slack app. Cutover checklist. Rollback."
    )
    assert pattern.search(plan)
    assert not pattern.search("image: python:3\ntest:\n  script: pytest\n")


def test_near_miss_regexes_separate_ci_answer_from_plan():
    ci = (EVALS / "gitlab-migration-near-miss-gitlab-ci-job/graders").glob("*.md")
    graders = {g.stem: _split_frontmatter(g)[0] for g in ci}
    answer = (
        "test:\n  rules:\n    - if: $CI_PIPELINE_SOURCE == 'merge_request_event'\n"
        "  cache:\n    paths: [.cache/pip]\n  script:\n    - pytest\n"
    )
    ok = re.compile(graders["answers-the-question"]["pattern"], re.I | re.S)
    bad = re.compile(graders["no-migration-plan"]["pattern"], re.I)
    assert ok.search(answer) and not bad.search(answer)
    assert bad.search("Here is a cutover checklist and rollback plan")
