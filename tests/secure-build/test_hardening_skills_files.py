"""Structure tests for dockerfile-harden, image-supply-chain and ci-harden.

These catch drift a linter cannot: a reference file named in SKILL.md that does not exist, a
script that lost its executable bit, a pinned digest that is not a digest, or an eval case
without a grader.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "secure-build"
SKILLS = ("dockerfile-harden", "image-supply-chain", "ci-harden")
ALLOWED_FIELDS = {"name", "description", "when_to_use", "allowed-tools", "disable-model-invocation"}


def frontmatter(skill: str) -> tuple[dict[str, str], str]:
    text = (PLUGIN / "skills" / skill / "SKILL.md").read_text()
    assert text.startswith("---\n"), f"{skill}: the opening --- must be line 1"
    head, _, body = text[4:].partition("\n---\n")
    fields: dict[str, str] = {}
    key = ""
    for line in head.splitlines():
        match = re.match(r"^([a-z-]+):\s*(.*)$", line)
        if match:
            key = match.group(1)
            fields[key] = match.group(2)
        elif key:
            fields[key] += " " + line.strip()
    return fields, body


@pytest.mark.parametrize("skill", SKILLS)
def test_frontmatter_is_valid(skill: str) -> None:
    fields, _ = frontmatter(skill)
    assert set(fields) <= ALLOWED_FIELDS, f"unknown frontmatter field in {skill}"
    assert fields["name"] == skill
    assert re.fullmatch(r"[a-z0-9-]{1,64}", skill)
    assert "claude" not in skill and "anthropic" not in skill
    description = fields["description"].lstrip(">-").strip()
    assert 100 < len(description) <= 1536
    assert not description.startswith(("I ", "You "))


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_md_is_short_and_has_no_personal_paths(skill: str) -> None:
    text = (PLUGIN / "skills" / skill / "SKILL.md").read_text()
    assert text.count("\n") < 500
    assert "/Users/" not in text
    assert "~/" not in text


@pytest.mark.parametrize("skill", SKILLS)
def test_every_file_named_in_skill_md_exists(skill: str) -> None:
    text = (PLUGIN / "skills" / skill / "SKILL.md").read_text()
    named = set(re.findall(r"(?<![\w/-])(?:references|templates|scripts)/[\w./-]+\w", text))
    assert named, f"{skill} names no bundled files"
    for name in named:
        assert (PLUGIN / "skills" / skill / name).exists(), f"{skill}: {name} is named but missing"


@pytest.mark.parametrize("skill", SKILLS)
def test_long_references_have_a_contents_list(skill: str) -> None:
    for path in (PLUGIN / "skills" / skill / "references").glob("*.md"):
        lines = path.read_text().splitlines()
        if len(lines) > 100:
            assert any(line.startswith("Contents") for line in lines[:12]), (
                f"{path.name} passes 100 lines and needs a contents list"
            )


@pytest.mark.parametrize("skill", SKILLS)
def test_scripts_are_executable_with_a_shebang(skill: str) -> None:
    scripts = [p for p in (PLUGIN / "skills" / skill / "scripts").iterdir() if p.is_file()]
    assert scripts
    for script in scripts:
        assert os.access(script, os.X_OK), f"{script.name} must be executable"
        assert script.read_text().startswith("#!"), f"{script.name} needs a shebang"


def test_cross_skill_references_point_at_files_that_exist() -> None:
    # image-supply-chain and dockerfile-harden send readers into ci-harden and each other.
    pattern = re.compile(r"`((?:ci-harden|image-supply-chain|dockerfile-harden)/[\w./-]+\w)`")
    for skill in SKILLS:
        for path in (PLUGIN / "skills" / skill).rglob("*.md"):
            for target in pattern.findall(path.read_text()):
                assert (PLUGIN / "skills" / target).exists(), (
                    f"{path.name}: {target} does not exist"
                )


def test_pinned_digests_and_shas_in_templates_are_well_formed() -> None:
    for path in (PLUGIN / "skills").glob("*/templates/**/*"):
        if not path.is_file() or path.name in {"CODEOWNERS", "dockerignore"}:
            continue
        text = path.read_text()
        for match in re.findall(r"sha256:([0-9a-f]+)", text):
            assert len(match) == 64, f"{path.name}: malformed digest sha256:{match}"
        for match in re.findall(r"uses:\s*\S+@([0-9a-f]{7,})\b", text):
            assert len(match) == 40, f"{path.name}: action pinned to a short SHA {match}"


def test_github_template_pins_every_action_and_grants_nothing_by_default() -> None:
    text = (PLUGIN / "skills/ci-harden/templates/.github/workflows/secure-build.yml").read_text()
    uses = re.findall(r"^\s*(?:-\s+)?uses:\s*(\S+)", text, re.M)
    assert uses
    assert all(re.search(r"@[0-9a-f]{40}$", u) for u in uses)
    assert re.search(r"^permissions:\s*\{\}\s*$", text, re.M)
    assert "pull_request_target" not in text
    assert "credentials_json" not in text


def test_gitlab_template_uses_oidc_and_no_stored_key() -> None:
    text = (PLUGIN / "skills/ci-harden/templates/.gitlab-ci.yml").read_text()
    assert "id_tokens:" in text
    assert "SIGSTORE_ID_TOKEN" in text
    assert not re.search(r"GCP_SA_KEY|GOOGLE_APPLICATION_CREDENTIALS|--key-file", text)
    assert "dind" not in text.replace("Docker-in-Docker", "")


def test_eval_cases_have_graders_and_the_right_trigger_graders() -> None:
    cases = [d for skill in SKILLS for d in (PLUGIN / "evals").glob(f"{skill}-*") if d.is_dir()]
    for skill in SKILLS:
        mine = [d for d in cases if d.name.startswith(f"{skill}-")]
        assert len(mine) >= 3, f"{skill} needs at least three eval cases"
        graders = {d.name: list((d / "graders").glob("*.md")) for d in mine}
        assert all(graders.values()), "every eval case needs at least one grader"
        triggers = [
            g
            for gs in graders.values()
            for g in gs
            if f'(?:[\\w-]+:)?{skill}"' in g.read_text() and "min: 0" not in g.read_text()
        ]
        near_misses = [
            g
            for gs in graders.values()
            for g in gs
            if f'(?:[\\w-]+:)?{skill}"' in g.read_text() and "max: 0" in g.read_text()
        ]
        assert triggers, f"{skill} needs a should-trigger case"
        assert near_misses, f"{skill} needs a near-miss case"
        for g in near_misses:
            assert "arm: both" in g.read_text()
    for case in cases:
        prompt = (case / "prompt.md").read_text()
        assert prompt.startswith("---\n")
        for skill in SKILLS:
            assert f"/{skill}" not in prompt.split("---", 2)[2], "prompts must not name the skill"
