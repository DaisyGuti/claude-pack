"""Layout checks for the tickets plugin: links resolve, chat-invocable skills, evals exist."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "tickets"
SKILLS = sorted(p.parent.name for p in (PLUGIN / "skills").glob("*/SKILL.md"))
EXPECTED_SKILLS = ["daily-grooming", "plan-ticket", "ticket-worker", "work-tickets", "write-ticket"]


def frontmatter(path: Path) -> dict[str, str]:
    """Read the top-level 'key: value' lines of a Markdown file's YAML frontmatter."""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path}: the opening --- must be line 1"
    block = text.split("---\n", 2)[1]
    return dict(re.findall(r"^([A-Za-z-]+):\s*(.*)$", block, re.M))


def test_the_five_skills_exist() -> None:
    assert SKILLS == EXPECTED_SKILLS


@pytest.mark.parametrize("skill", EXPECTED_SKILLS)
def test_skills_can_be_run_from_chat(skill: str) -> None:
    """The team works from chat, so no skill sets disable-model-invocation."""
    fields = frontmatter(PLUGIN / "skills" / skill / "SKILL.md")
    assert "disable-model-invocation" not in fields


@pytest.mark.parametrize("skill", EXPECTED_SKILLS)
def test_skill_name_matches_folder_and_description_fits(skill: str) -> None:
    fields = frontmatter(PLUGIN / "skills" / skill / "SKILL.md")
    assert fields["name"] == skill
    assert 0 < len(fields["description"]) <= 1024
    assert not re.search(r"claude|anthropic", fields["name"])


@pytest.mark.parametrize("skill", EXPECTED_SKILLS)
def test_skill_body_stays_under_500_lines(skill: str) -> None:
    lines = (PLUGIN / "skills" / skill / "SKILL.md").read_text(encoding="utf-8").splitlines()
    assert len(lines) < 500


def linked_paths(path: Path) -> list[str]:
    """Plugin-relative targets of every ${CLAUDE_PLUGIN_ROOT}/ or ${CLAUDE_SKILL_DIR}/ link."""
    text = path.read_text(encoding="utf-8")
    found = re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+?)(?=[)`\s]|$)", text)
    skill_dir = path.parent.relative_to(PLUGIN).as_posix()
    found += [
        f"{skill_dir}/{rel}"
        for rel in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/([\w./-]+?)(?=[)`\s]|$)", text)
    ]
    return found


@pytest.mark.parametrize("skill", EXPECTED_SKILLS)
def test_every_path_a_skill_links_exists(skill: str) -> None:
    targets = linked_paths(PLUGIN / "skills" / skill / "SKILL.md")
    assert targets, "a skill with no links to its references is suspicious"
    for rel in targets:
        if rel.endswith("/") or "*" in rel:
            continue  # a folder or a glob used in an allowed-tools rule
        assert (PLUGIN / rel).exists(), f"{skill}: {rel} does not exist"


def test_script_paths_in_allowed_tools_exist() -> None:
    for skill in EXPECTED_SKILLS:
        rules = frontmatter(PLUGIN / "skills" / skill / "SKILL.md").get("allowed-tools", "")
        for rel in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/(scripts/[\w.-]+)", rules):
            script = PLUGIN / rel
            assert script.is_file(), f"{skill}: allowed-tools names missing {rel}"
            assert script.stat().st_mode & 0o111, f"{rel} is not executable"


def test_reference_files_named_in_prose_exist() -> None:
    names = {p.name for p in (PLUGIN / "references").rglob("*.md")}
    names |= {p.name for p in PLUGIN.glob("skills/*/references/*.md")}
    for doc in [
        *PLUGIN.glob("references/*.md"),
        *PLUGIN.glob("skills/*/references/*.md"),
        *PLUGIN.glob("agents/*.md"),
    ]:
        for ref in re.findall(r"`([a-z][a-z-]+\.md)`", doc.read_text(encoding="utf-8")):
            if ref in {
                "registry.md",
                "registry.example.md",
                "SKILL.md",
                "CLAUDE.md",
                "AGENTS.md",
                "CONTRIBUTING.md",
                "README.md",
            }:
                continue
            assert ref in names, f"{doc.relative_to(PLUGIN)} names {ref}, which does not exist"


def test_worker_agent_is_isolated_and_least_privilege() -> None:
    fields = frontmatter(PLUGIN / "agents" / "ticket-worker.md")
    assert fields["name"] == "ticket-worker"
    assert fields["isolation"] == "worktree"
    assert "Skill" not in fields["tools"]
    assert fields["model"] in {"haiku", "sonnet", "opus", "inherit"}
    assert int(fields["maxTurns"]) > 0


def test_worker_reviews_its_diff_before_committing() -> None:
    """The worker holds the Agent tool, runs core:reviewer before any commit on both landing
    paths (section 7 and the held review in section 9), and reports the review in each body."""
    path = PLUGIN / "agents" / "ticket-worker.md"
    tools = [t.strip() for t in frontmatter(path)["tools"].split(",")]
    assert "Agent" in tools
    body = path.read_text(encoding="utf-8")
    land = body[body.index("## 7. Land the work") : body.index("## 8. After the review opens")]
    held = body[body.index("## 9. Needs manual action") : body.index("## 10. Final report")]
    assert land.index("**Pre-commit review.**") < land.index("**Commit.**")
    assert "`core:reviewer`" in land
    assert "blocked_review_findings" in land
    assert "before committing or pushing any of them" in land
    assert "**Pre-commit review**" in held
    assert "the review summary" in land
    assert "the review summary" in held
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert "core" in manifest.get("dependencies", [])


def test_worker_files_a_follow_up_ticket_for_every_unfixed_finding_and_known_gap() -> None:
    """Daisy's rule: nothing the worker leaves behind stays only in a report. The agent files
    it after the review opens, on both landing paths, and reports it in the RESULT line, and
    both dispatchers hand it the template and checker it files with."""
    body = (PLUGIN / "agents" / "ticket-worker.md").read_text(encoding="utf-8")
    build = body[body.index("## 6. Implement and test") : body.index("## 7. Land the work")]
    land = body[body.index("## 7. Land the work") : body.index("## 8. After the review opens")]
    held = body[body.index("## 9. Needs manual action") : body.index("## 10. Final report")]
    final = body[body.index("## 10. Final report") :]
    for gap in ("`TODO` left in code", "a path you did not test", "an assumption", "pre-existing"):
        assert gap in build, gap
    assert "wrong gets a one-line reason in the review summary and no ticket" in land
    filing = land[land.index("**File the follow-ups**") : land.index("4. **comment**")]
    assert land.index("**open-review**") < land.index("**File the follow-ups**")
    for part in (
        "**search-issues**",
        "`files.check_ticket`",
        "Found in <review link>",
        "**set-lane** with role `backlog`",
        "**assign** to",
        "**read-issue**",
    ):
        assert part in filing, part
    assert "File the follow-ups** as section 7's step 3" in held
    # A stop files them too, linking the ticket in place of a review.
    assert "(no review opened)" in body[body.index("**Holding the ticket.**") : body.index("## 5.")]
    assert "**Follow-ups** heading" in final
    assert '"follow_up_refs": [' in final
    for dispatcher in (
        PLUGIN / "skills" / "ticket-worker" / "SKILL.md",
        PLUGIN / "skills" / "work-tickets" / "references" / "orchestrator.md",
    ):
        text = dispatcher.read_text(encoding="utf-8")
        assert "`files.ticket_template`" in text and "`files.check_ticket`" in text, dispatcher
    assert (PLUGIN / "skills" / "write-ticket" / "assets" / "ticket-template.md").is_file()
    assert (PLUGIN / "scripts" / "check_ticket.py").is_file()


def flat(path: Path) -> str:
    """A file's text with every run of whitespace collapsed, so a phrase can wrap across lines."""
    return " ".join(path.read_text(encoding="utf-8").split())


def test_worker_merges_the_base_then_runs_only_the_gates_the_diff_touches_once() -> None:
    """Ticket workers share one laptop: the default branch is merged in first (never a rebase),
    then the gates the diff touches run once on the merged tree, and the full suite is left to
    CI. The worker says in its report which gates ran."""
    body = flat(PLUGIN / "agents" / "ticket-worker.md")
    section = body[body.index("**Merge the default branch, then run the gates once.**") :]
    section = section[: section.index("**Waiting.**")]
    assert "merge --no-edit origin/<default_branch>" in section
    assert "Never rebase." in section
    assert "only the ones the diff touches" in section
    assert "Do not run the repo's full suite: CI runs it on the review." in section
    assert "Never run the gates before the merge and again after it" in section
    assert section.index("merge --no-edit") < section.index("run the gates on the merged tree")
    assert "which gates ran and which were left to CI" in section
    assert "the gates that ran and the ones left to CI" in body[body.index("## 10. Final report") :]


def test_worker_waits_by_pid_never_by_a_self_matching_pgrep() -> None:
    body = flat(PLUGIN / "agents" / "ticket-worker.md")
    section = body[body.index("**Waiting.**") : body.index("## 7. Land the work")]
    assert 'Never loop on `pgrep -f "<text>"`' in section
    assert "by its PID" in section and "completion of the background job" in section
    assert "nothing you started is still running" in section
    assert "nothing you started is still running" in body[body.index("## 10. Final report") :]


def test_worker_tests_wait_on_conditions_not_sleeps() -> None:
    body = flat(PLUGIN / "agents" / "ticket-worker.md")
    section = body[body.index("**Tests.**") : body.index("**Gate command**")]
    assert "never on a fixed sleep" in section
    assert "fake timers for polling code" in section
    assert "only as a backstop against a hang" in section


def test_a_locked_signing_key_blocks_the_ticket_and_the_orchestrator_resumes_all_together() -> None:
    """No long retry windows and signing is never turned off: the worker keeps the change
    staged and ends `blocked_sandbox`; the orchestrator asks the user to unlock once and
    resumes every such worker in one message from the trees the worker reported."""
    worker = flat(PLUGIN / "agents" / "ticket-worker.md")
    land = worker[worker.index("**A locked signing key.**") : worker.index("**Review.** Per repo")]
    assert "do not wait out retry windows and never turn signing off" in land
    assert "status=blocked_sandbox" in land and "signing key locked" in land
    assert "worktree_paths" in land and "resume_worktrees" in land
    assert "A locked signing key stops the run as section 7 describes" in worker
    assert "**Resuming after a locked signing key.**" in worker
    orchestrator = flat(PLUGIN / "skills" / "work-tickets" / "references" / "orchestrator.md")
    reap = orchestrator[orchestrator.index("`blocked_sandbox` and the `reason`") :]
    reap = reap[: reap.index('`status == "review_opened"`')]
    assert "Ask the user once" in reap and "Do not ask per worker" in reap
    assert "resume all of those workers together" in reap
    assert "`resume_worktrees` set from its `worktree_paths`" in reap


def test_the_orchestrator_has_one_poller_and_runs_flaky_test_and_ci_tickets_first() -> None:
    text = flat(PLUGIN / "skills" / "work-tickets" / "references" / "orchestrator.md")
    poller = text[text.index("- **One poller.**") : text.index("- **Preflight**")]
    assert "is the only thing that polls the tracker" in poller
    assert "never start a polling loop per review or per worker" in poller
    assert "rate limit is shared" in poller
    assert "Nothing here merges a review." in poller
    assert "a flaky-test or CI ticket (judged from its title and labels) goes ahead" in text
    assert "so flaky-test and CI tickets fill slots first" in text


def test_ready_means_planned_in_planning_and_grooming() -> None:
    """A ticket is in Ready only with a Final Plan and no open blocker, and a planned,
    unblocked ticket moves to Ready in the step that plans it."""
    planning = flat(PLUGIN / "references" / "plan-one-ticket.md")
    assert "**Ready means planned.**" in planning
    assert "only with a `### Final Plan` and no open blocker" in planning
    assert "never left in the backlog" in planning
    assert "**Lane.**" in planning and "**set-lane** with role `ready`" in planning
    grooming = flat(PLUGIN / "skills" / "daily-grooming" / "references" / "grooming.md")
    triage = grooming[grooming.index("## 4. Triage the lanes") : grooming.index("## 5.")]
    assert "**Ready means planned.**" in triage
    assert "| Planned, with no open blocker | ready |" in triage
    assert "| Not planned yet | backlog until step 7 plans it" in triage
    assert "carries the blocked label and sits in the ready lane" in triage
    for doc in (
        PLUGIN / "skills" / "daily-grooming" / "SKILL.md",
        PLUGIN / "README.md",
    ):
        assert "Ready means planned" in flat(doc), doc


def test_model_label_is_sized_to_the_plans_scope() -> None:
    labels = flat(PLUGIN / "references" / "ticket-labels.md")
    section = labels[labels.index("## Model label") : labels.index("## Blocked")]
    assert "read from the scope of the plan" in section
    assert "only adds or edits tests or documents, or touches one small file" in section
    assert "A normal multi-file change" in section
    assert "Security, authentication or gate logic" in section
    assert "tricky invariants" in section
    planning = flat(PLUGIN / "references" / "plan-one-ticket.md")
    assert "Size it to the plan's scope" in planning


def test_grooming_reports_ready_in_waves_that_share_no_file() -> None:
    grooming = flat(PLUGIN / "skills" / "daily-grooming" / "references" / "grooming.md")
    summary = grooming[grooming.index("- **Ready (in waves)**") : grooming.index("- **Backlog")]
    assert "touch no file in common" in summary
    assert "at most the pool size" in summary
    assert "Flaky-test and CI tickets come first" in summary
    assert "adds a migration gets a wave to itself" in summary


def test_ticket_worker_skill_turns_on_auto_fix_for_an_opened_review() -> None:
    """The session that started the worker turns Auto-fix on, never the worker, and only for a
    review that is open for merging; the held `needs_manual_action` review is skipped."""
    skill = (PLUGIN / "skills" / "ticket-worker" / "SKILL.md").read_text(encoding="utf-8")
    section = skill[skill.index("## 5. Turn on Auto-fix") : skill.index("## 6. Report")]
    for tool in ("get_status", "bind_pr", "set_monitor"):
        assert f"mcp__ccd_pr__{tool}" in section
    assert "`auto_fix` true" in section and "`address_comments` true" in section
    assert "needs_manual_action" in section
    assert "Never enable auto-merge" in section
    assert "Auto-fix is on for each" in skill[skill.index("## 6. Report") :]
    assert "ccd_pr" not in (PLUGIN / "agents" / "ticket-worker.md").read_text(encoding="utf-8")


def test_work_tickets_runs_a_rolling_pool_and_says_so_everywhere() -> None:
    """The skill and its procedure agree on the pool size, and no file still says waves."""
    skill = (PLUGIN / "skills" / "work-tickets" / "SKILL.md").read_text(encoding="utf-8")
    procedure = (PLUGIN / "skills" / "work-tickets" / "references" / "orchestrator.md").read_text(
        encoding="utf-8"
    )
    default = re.compile(r"max-parallel`? \(5 by default\)|\*\*max-parallel:\*\* 5")
    assert default.search(skill), "SKILL.md must state the default pool size of 5"
    assert default.search(procedure), "orchestrator.md must state the default pool size of 5"
    assert "run_in_background: true" in procedure
    # With background workers the loop must end on "nothing running", not on an empty record:
    # a worker that ends without a RESULT line stays in `active` for the next run.
    assert "no worker is still running" in procedure
    assert "until every\ndispatched worker has returned" in procedure
    stale = [
        str(path.relative_to(PLUGIN))
        for path in (
            PLUGIN / "README.md",
            PLUGIN / "skills" / "work-tickets" / "SKILL.md",
            PLUGIN / "skills" / "work-tickets" / "references" / "orchestrator.md",
        )
        if re.search(r"\bwaves?\b", path.read_text(encoding="utf-8"), re.I)
    ]
    assert not stale, f"still describes waves: {stale}"


def test_planning_runs_on_opus_whatever_the_session_model() -> None:
    """A plan steers a cheaper worker, so every planning step names the opus alias."""
    for skill in ("plan-ticket", "write-ticket"):
        assert frontmatter(PLUGIN / "skills" / skill / "SKILL.md").get("model") == "opus", skill
    grooming = " ".join((PLUGIN / "skills" / "daily-grooming" / "SKILL.md").read_text().split())
    assert "Plan each ticket in its own subagent started with `model: opus`" in grooming
    selection = (PLUGIN / "references" / "model-selection.md").read_text()
    assert "## Planning runs on frontier" in selection


def test_scripts_are_executable_with_a_shebang() -> None:
    for script in (PLUGIN / "scripts").glob("*.py"):
        assert script.stat().st_mode & 0o111, f"{script.name} is not executable"
        assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")


@pytest.mark.parametrize("skill", EXPECTED_SKILLS)
def test_each_skill_has_trigger_and_no_trigger_evals(skill: str) -> None:
    cases = sorted((PLUGIN / "evals").glob(f"{skill}-*/prompt.md"))
    assert len(cases) >= 3
    for prompt in cases:
        assert list((prompt.parent / "graders").glob("*.md")), f"{prompt.parent.name} has no grader"
    near_miss = (PLUGIN / "evals" / f"{skill}-near-miss" / "graders").glob("*.md")
    texts = [g.read_text(encoding="utf-8") for g in near_miss]
    assert any("min: 0" in t and "max: 0" in t and "arm: both" in t for t in texts)


def test_the_agent_has_a_delegation_eval() -> None:
    graders = (PLUGIN / "evals" / "ticket-worker-agent-delegates-when-asked" / "graders").glob(
        "*.md"
    )
    assert any("tool: Agent" in g.read_text(encoding="utf-8") for g in graders)


def test_no_personal_paths_or_tool_names_leak_into_the_plugin() -> None:
    banned = re.compile(
        r"(?-i:/Users/)|\bcodex\b|\$work-tickets|\$ticket-worker|\$write-ticket", re.I
    )
    for path in PLUGIN.rglob("*"):
        if (
            path.is_file()
            and path.suffix in {".md", ".py", ".json"}
            and "evals/results" not in str(path)
        ):
            hit = banned.search(path.read_text(encoding="utf-8"))
            assert hit is None, f"{path.relative_to(PLUGIN)} mentions {hit.group(0)!r}"
