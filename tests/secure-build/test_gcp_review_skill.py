"""Structure checks for the gcp-review skill: frontmatter, size, links, docs and evals."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins/secure-build"
SKILL = PLUGIN / "skills/gcp-review"
EVALS = sorted((PLUGIN / "evals").glob("gcp-review-*/"))


def load(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, SKILL / "scripts" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rules = load("gcp_rules.py", "gcp_review_rules_for_skill_test")
collect = load("gcp_collect.py", "gcp_review_collect_for_skill_test")
wrapper = sys.modules["gcloud_readonly"]


def split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Parse the small YAML subset these files use: scalars, folded blocks and lists."""
    assert text.startswith("---\n"), "the opening --- must be line 1"
    head, _, body = text[4:].partition("\n---\n")
    data: dict[str, object] = {}
    key: str | None = None
    for line in head.splitlines():
        if re.match(r"^[A-Za-z_-]+:", line):
            key, _, value = line.partition(":")
            value = value.strip()
            data[key] = [] if value == "" else ("" if value in {">-", ">", "|"} else value)
        elif key is not None and line.strip().startswith("- "):
            assert isinstance(data[key], list)
            data[key].append(line.strip()[2:])  # type: ignore[union-attr]
        elif key is not None and line.strip():
            current = data[key]
            data[key] = (
                (str(current) + " " + line.strip()).strip() if isinstance(current, str) else current
            )
    return data, body


SKILL_TEXT = (SKILL / "SKILL.md").read_text(encoding="utf-8")
META, BODY = split_frontmatter(SKILL_TEXT)


class TestFrontmatter:
    def test_name_matches_the_folder_and_the_rules(self) -> None:
        name = str(META["name"])
        assert name == SKILL.name == "gcp-review"
        assert re.fullmatch(r"[a-z0-9-]{1,64}", name)
        assert "claude" not in name and "anthropic" not in name

    def test_description_is_third_person_and_within_the_limit(self) -> None:
        description = str(META["description"])
        assert len(description) + len(str(META.get("when_to_use", ""))) <= 1536
        assert not re.match(r"(I|You|We)\b", description)
        assert description.startswith("Runs a read-only security review")

    def test_description_carries_trigger_terms_and_the_push(self) -> None:
        description = str(META["description"]).lower()
        for term in (
            "iam", "service account keys", "organization policies", "workload identity",
            "gitlab", "github", "vpc service controls", "cmek", "artifact registry",
            "binary authorization", "cloud run", "gke", "assured workloads", "fedramp",
        ):  # fmt: skip
            assert term in description, term
        assert "even if they do not name this skill" in description

    def test_allowed_tools_pre_approve_only_the_scripts_and_read(self) -> None:
        assert META["allowed-tools"] == ["Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*)", "Read"]

    def test_read_only_skill_does_not_disable_model_invocation(self) -> None:
        assert "disable-model-invocation" not in META

    def test_only_documented_fields_are_used(self) -> None:
        assert set(META) <= {"name", "description", "allowed-tools", "when_to_use"}


class TestBody:
    def test_size_is_well_under_the_limit(self) -> None:
        assert len(SKILL_TEXT.splitlines()) < 300

    def test_the_key_instructions_come_first(self) -> None:
        first = BODY[: BODY.index("## Before starting")]
        for needle in ("Read-only", "wrapper", "Evidence and gaps only", "PreToolUse hook"):
            assert needle in first, needle

    def test_allowed_tools_limitation_is_stated_honestly(self) -> None:
        assert "does not restrict" in BODY
        assert "guardrails" in BODY

    def test_all_three_report_sections_are_named(self) -> None:
        for heading in ("Findings", "Not checked (gaps)", "Drafted fixes (not executed)"):
            assert heading in BODY

    def test_every_script_is_called_through_the_skill_dir_variable(self) -> None:
        for match in re.finditer(r"python3 (\S+)", BODY):
            assert match.group(1).startswith("${CLAUDE_SKILL_DIR}/scripts/"), match.group(1)

    def test_every_linked_file_exists_one_level_deep(self) -> None:
        for target in re.findall(r"\]\((references/[^)#]+)", BODY):
            assert (SKILL / target).is_file(), target
            assert target.count("/") == 1

    def test_every_backticked_skill_file_exists(self) -> None:
        for path in re.findall(r"`((?:scripts|references)/[\w./-]+)`", BODY):
            assert (SKILL / path).exists(), path

    def test_external_fetch_sources_are_named(self) -> None:
        for url in (
            "cisecurity.org/benchmark/google_cloud_computing_platform",
            "org-policy-constraints",
            "assured-workloads/docs/overview",
            "workload-identity-federation-with-deployment-pipelines",
        ):
            assert url in BODY, url

    def test_terraform_security_command_center_and_asset_inventory_are_named(self) -> None:
        for term in (
            "terraform",
            "claude-plugins-official",
            "Security Command",
            "Cloud Asset Inventory",
        ):
            assert term in BODY, term


MARKDOWN = [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md"))]


class TestReferences:
    @pytest.mark.parametrize(
        "path", sorted((SKILL / "references").glob("*.md")), ids=lambda p: p.name
    )
    def test_sources_and_fetch_date(self, path: Path) -> None:
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:25])
        assert "https://" in head and re.search(r"fetched 20\d\d-\d\d-\d\d", head), path.name

    @pytest.mark.parametrize(
        "path", sorted((SKILL / "references").glob("*.md")), ids=lambda p: p.name
    )
    def test_long_references_have_a_table_of_contents(self, path: Path) -> None:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > 100:
            assert any(line.startswith("## Contents") for line in lines[:40]), path.name

    @pytest.mark.parametrize(
        "path", sorted((SKILL / "references").glob("*.md")), ids=lambda p: p.name
    )
    def test_references_do_not_link_to_other_references(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\]\((?:\./)?references/", text) and "](../" not in text

    def test_every_rule_is_documented(self) -> None:
        text = (SKILL / "references/checks.md").read_text(encoding="utf-8")
        for rule in rules.RULES:
            if re.fullmatch(r"GCP-ORG-\d+", rule):
                continue  # documented as a range plus the constraint table
            assert rule in text, rule

    def test_every_org_policy_check_and_constraint_name_is_documented(self) -> None:
        text = (SKILL / "references/checks.md").read_text(encoding="utf-8")
        for check, names in collect.ORG_POLICY_CONSTRAINTS.items():
            assert f"| {check} |" in text, check
            for name in names:
                assert f"`{name}`" in text, name
        for rule, _constraint in rules.ORG_CHECKS.values():
            assert rule in text, rule

    def test_every_wrapper_command_family_in_the_catalog_is_allowlisted(self) -> None:
        for call_args in (
            "projects get-iam-policy", "org-policies describe", "assured workloads list",
            "container binauthz policy export", "artifacts repositories get-iam-policy",
        ):  # fmt: skip
            words = tuple(call_args.split())
            assert words in wrapper.ALLOWED_COMMANDS

    def test_assured_workloads_reference_names_run_time_fetches(self) -> None:
        text = (SKILL / "references/assured-workloads.md").read_text(encoding="utf-8")
        assert "What to fetch at run time" in text
        assert "does not decide" in text or "decide" in text

    def test_a_verified_benchmark_edition_is_recorded_with_its_source(self) -> None:
        text = (SKILL / "references/checks.md").read_text(encoding="utf-8")
        flat = " ".join(text.split()).lower()
        assert "5.0.0" in text and "Prowler" in text and "confirm each id" in flat


class TestHouseStyle:
    @pytest.mark.parametrize("path", MARKDOWN, ids=lambda p: p.name)
    def test_no_personal_paths_or_names(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        assert "/Users/" not in text and "~/" not in text

    @pytest.mark.parametrize("path", MARKDOWN, ids=lambda p: p.name)
    def test_no_contrastive_not_construction(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        prose = re.sub(r"```.*?```", "", text, flags=re.S)
        assert not re.search(r"\b(?:is|are|was|were) not [^.\n]{1,40}, but\b", prose)
        assert not re.search(r"[a-z], not (?:a|an|the|just|only)\b", prose)

    @pytest.mark.parametrize("path", MARKDOWN, ids=lambda p: p.name)
    def test_no_claim_of_compliance(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8").lower()
        for phrase in ("is fedramp compliant", "is fedramp ready", "will be authorized"):
            assert phrase not in text, phrase

    def test_scripts_are_standard_library_only(self) -> None:
        stdlib = set(sys.stdlib_module_names)
        for script in (SKILL / "scripts").glob("*.py"):
            for line in script.read_text(encoding="utf-8").splitlines():
                match = re.match(r"(?:from|import) ([\w.]+)", line)
                if match and not line.startswith(" "):
                    assert match.group(1).split(".")[0] in stdlib, (script.name, line)

    def test_scripts_have_shebangs_and_are_executable(self) -> None:
        for script in (SKILL / "scripts").glob("*.py"):
            assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")
            assert script.stat().st_mode & 0o111, script.name


class TestEvals:
    def test_at_least_three_cases_exist(self) -> None:
        assert len(EVALS) >= 3

    @pytest.mark.parametrize("case", EVALS, ids=lambda p: p.name)
    def test_case_layout_and_prompt(self, case: Path) -> None:
        meta, body = split_frontmatter((case / "prompt.md").read_text(encoding="utf-8"))
        for field in ("name", "description", "tags", "runs", "max_turns", "timeout_seconds"):
            assert field in meta, (case.name, field)
        assert meta["name"] == case.name
        assert meta["runs"] == "1"
        assert 1 <= int(str(meta["max_turns"])) <= 200
        assert int(str(meta["timeout_seconds"])) <= 3600
        assert "gcp-review" not in body, "the prompt must not name the skill"
        assert body.strip()
        graders = list((case / "graders").glob("*.md"))
        assert graders, case.name
        for grader in graders:
            gmeta, _ = split_frontmatter(grader.read_text(encoding="utf-8"))
            assert gmeta["type"] in {
                "regex",
                "tool_used",
                "tool_order",
                "file_exists",
                "llm",
                "baseline",
            }

    def graders(self) -> list[tuple[Path, dict[str, object]]]:
        out = []
        for case in EVALS:
            for grader in (case / "graders").glob("*.md"):
                out.append((grader, split_frontmatter(grader.read_text(encoding="utf-8"))[0]))
        return out

    def test_a_should_trigger_case_uses_the_documented_skill_grader(self) -> None:
        pattern = '\'"skill"\\s*:\\s*"(?:[\\w-]+:)?gcp-review"\''
        hits = [
            g for g, m in self.graders()
            if m.get("type") == "tool_used" and m.get("tool") == "Skill"
            and m.get("input_match") == pattern and "max" not in m
        ]  # fmt: skip
        assert hits, "no should-trigger grader with the documented input_match"

    def test_a_near_miss_case_must_not_trigger_the_skill(self) -> None:
        hits = [
            g for g, m in self.graders()
            if m.get("tool") == "Skill" and m.get("min") == "0" and m.get("max") == "0"
            and m.get("arm") == "both"
        ]  # fmt: skip
        assert len(hits) >= 2

    def test_an_output_case_forbids_mutating_gcloud_calls(self) -> None:
        pattern = None
        for grader, meta in self.graders():
            if meta.get("tool") == "Bash" and meta.get("max") == "0" and "just-fix" in str(grader):
                pattern = str(meta["input_match"]).strip("'")
        assert pattern, "just-fix case lacks a no-mutation grader"
        regex = re.compile(pattern)
        for bad in (
            '{"command": "gcloud projects add-iam-policy-binding acme --role=roles/x"}',
            '{"command": "gcloud projects set-iam-policy acme p.json"}',
            '{"command": "gcloud services enable run.googleapis.com"}',
        ):
            assert regex.search(bad), bad
        for good in (
            '{"command": "python3 /x/scripts/gcloud_readonly.py projects get-iam-policy acme"}',
            '{"command": "gcloud projects get-iam-policy acme"}',
        ):
            assert not regex.search(good), good

    def test_the_direct_gcloud_grader_matches_only_unwrapped_calls(self) -> None:
        pattern = None
        for grader, meta in self.graders():
            if grader.name == "no-direct-gcloud.md":
                pattern = str(meta["input_match"]).strip("'")
        assert pattern
        regex = re.compile(pattern)
        assert regex.search('{"command": "gcloud projects list"}')
        assert not regex.search(
            '{"command": "python3 /x/scripts/gcloud_readonly.py projects list"}'
        )
