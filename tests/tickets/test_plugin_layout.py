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
    filing = land[land.index("**File the follow-ups**") : land.index("5. **comment**")]
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
    assert "File the follow-ups** as section 7's Review step 4" in held
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


def test_worker_moves_the_card_before_filing_a_capped_set_of_follow_ups() -> None:
    """A run with many follow-ups once risked its turn budget before the ticket was updated:
    the board moves first, filing is capped, and the comment that lists the tickets comes
    last, on the open-review path, the hold path and the held-review path alike."""
    body = flat(PLUGIN / "agents" / "ticket-worker.md")
    land = body[body.index("## 7. Land the work") : body.index("## 8. After the review opens")]
    after = land[land.index("Then, on the owning repo:") :]
    lane = after.index("3. **set-lane** with role `review`")
    filing = after.index("4. **File the follow-ups**")
    comment = after.index("5. **comment** once on the issue")
    assert lane < filing < comment
    assert "at most five new tickets per run" in after
    assert "Not filed, for a person to file:" in after
    hold = body[body.index("**Holding the ticket.**") : body.index("**Item handle.**")]
    # A blocked label never sits without its comment, so the Blocked comment precedes filing.
    assert hold.index("**set-lane** with role `blocked`") < hold.index("3. **comment** once")
    assert hold.index("3. **comment** once") < hold.index("under the same cap")
    assert hold.index("under the same cap") < hold.index("**comment** once more")
    held = body[body.index("## 9. Needs manual action") : body.index("## 10. Final report")]
    assert held.index("5. **set-lane** with role `blocked`") < held.index("6. **comment** once")
    assert held.index("6. **comment** once") < held.index("7. **File the follow")
    assert "`over the per-run cap`" in body[body.index("## 10. Final report") :]


def test_the_worker_reviews_in_at_most_two_rounds_with_core_reviewer_every_time() -> None:
    body = flat(PLUGIN / "agents" / "ticket-worker.md")
    review = body[body.index("**Pre-commit review.**") : body.index("**Commit.**")]
    assert "at most two rounds" in review and "whatever its size" in review
    assert "its DRY pass included" in review
    assert "Round two, when the rule calls for it" in review
    assert "spawn it once more" in review
    assert "blocked_review_findings" in review
    assert "no independent review ran" in review


def test_label_colors_live_once_in_ticket_labels() -> None:
    """The project and priority label color and description are defined once; every writer
    points there, the worker's follow-up filing included."""
    labels = flat(PLUGIN / "references" / "ticket-labels.md")
    section = labels[labels.index("## Label colors and descriptions") :]
    assert "| `project:<repo>` | `ededed` | `Product: <repo>` |" in section
    assert "| A priority value used as a label | `ededed` | `Priority: <name>` |" in section
    writers = [
        PLUGIN / "skills" / "write-ticket" / "SKILL.md",
        PLUGIN / "skills" / "daily-grooming" / "references" / "grooming.md",
        PLUGIN / "references" / "trackers" / "github.md",
        PLUGIN / "references" / "trackers" / "gitlab.md",
        PLUGIN / "agents" / "ticket-worker.md",
    ]
    for path in writers:
        text = flat(path)
        assert "ededed" not in text and "Product: <repo>" not in text, path
        assert "color and description" in text, path


def test_write_ticket_ready_plans_before_the_ready_lane() -> None:
    skill = flat(PLUGIN / "skills" / "write-ticket" / "SKILL.md")
    assert "`--ready` never files straight into the ready lane" in skill
    plan = skill[skill.index("6. **Plan it**") : skill.index("`--ticket N`:")]
    assert "plan-one-ticket.md" in plan and "`### Final Plan`" in plan
    assert "stays in the backlog lane and the report says why" in plan


def test_direct_mode_documents_the_locked_key_stop_and_its_resume() -> None:
    skill = flat(PLUGIN / "skills" / "ticket-worker" / "SKILL.md")
    section = skill[
        skill.index("**A locked signing key.**") : skill.index("## 5. Turn on Auto-fix")
    ]
    assert "`blocked_sandbox`" in section and "`signing key locked`" in section
    assert "never turns signing off" in section
    assert "`resume_worktrees` set from the result's `worktree_paths`" in section
    assert "except a resume after a locked signing key" in skill
    assert "and `resumed` `true`" in section and "git worktree list" in section
    assert "The one exception is a resume after a locked signing key (section 4)." in skill


def flat(path: Path) -> str:
    """A file's text with every run of whitespace collapsed, so a phrase can wrap across lines."""
    return " ".join(path.read_text(encoding="utf-8").split())


STANDARDS = "plugins/core/skills/eng/references/engineering-standards.md"


def worker_section_6() -> str:
    """Section 6 of the ticket worker, whitespace collapsed."""
    body = flat(PLUGIN / "agents" / "ticket-worker.md")
    return body[body.index("## 6. Implement and test") : body.index("## 7. Land the work")]


def test_worker_merges_the_base_with_its_own_command_and_points_to_the_standards() -> None:
    """The merge command and `blocked_merge_conflict` are the worker's own; the merge-then-gate
    order, never rebasing and the report of which gates ran come from the standards file."""
    body = flat(PLUGIN / "agents" / "ticket-worker.md")
    section = worker_section_6()
    assert "merge --no-edit origin/<default_branch>" in section
    assert "`blocked_merge_conflict`" in section
    assert "standards' merge rule" in section
    assert "Never rebase." in section
    assert section.index("merge --no-edit") < section.index("Then run the gates once")
    assert "which gates ran and which were left to CI" in section
    assert "the gates that ran and the ones left to CI" in body[body.index("## 10. Final report") :]


def test_worker_section_6_points_to_the_standards_for_the_shared_rules() -> None:
    """Parallelism, waiting on a condition and environment variables are stated once, in the
    standards file the worker reads in full, not restated where the two copies would drift."""
    section = worker_section_6()
    for pointer in (
        "standards' parallelism rule",
        "standards' waiting rule",
        "standards' example-env rule",
    ):
        assert pointer in section
    for restated in ('pgrep -f "<text>"', "fake timers", "`.env.example`"):
        assert restated not in section
    standards = flat(PLUGIN.parents[1] / STANDARDS)
    for rule in (
        "**Run tests and gates at the repo's full parallelism.**",
        "**Wait on a condition, never on a fixed sleep or a self-matching command.**",
        "**Every new environment variable lands in the repo's example env file.**",
    ):
        assert rule in standards
    body = flat(PLUGIN / "agents" / "ticket-worker.md")
    assert "nothing you started is still running" in body[body.index("## 10. Final report") :]


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
    assert "A labelled ticket never waits in the backlog." in triage
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


def test_planning_and_grooming_check_dependencies_with_the_script() -> None:
    """No hold names a tracker or a chain back to itself; the label and the lane agree."""
    planning = flat(PLUGIN / "references" / "plan-one-ticket.md")
    assert "**A dependency is a blocked-by link.**" in planning
    assert "**Before linking a dependency.**" in planning and "`<scripts>/deps.py`" in planning
    assert "then **set-lane** with role `blocked`" in planning
    grooming = flat(PLUGIN / "skills" / "daily-grooming" / "references" / "grooming.md")
    audit = grooming[grooming.index("## 3. Audit") : grooming.index("## 3b.")]
    # The findings live in deps.py (tests/tickets/test_deps.py); the audit must run it.
    assert "Run `<scripts>/links.py fetch" in audit and "Run `<scripts>/deps.py <file>`" in audit
    assert "**The blocked label and the blocked lane agree, both ways.**" in audit
    assert (PLUGIN / "scripts" / "deps.py").is_file() and (
        PLUGIN / "scripts" / "links.py"
    ).is_file()


def test_grooming_cuts_ready_waves_with_the_script() -> None:
    grooming = flat(PLUGIN / "skills" / "daily-grooming" / "references" / "grooming.md")
    summary = grooming[grooming.index("- **Ready (in waves)**") : grooming.index("- **Backlog")]
    # The rules live in waves.py (tests/tickets/test_waves.py); the summary must run it.
    assert "`<scripts>/waves.py <file> --pool <N>`" in summary
    assert (PLUGIN / "scripts" / "waves.py").is_file()


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


def test_cleanup_after_each_ticket_is_in_the_instructions() -> None:
    """Daisy's rule: worktrees and test data never pile up across a run. The orchestrator
    removes a worker's worktree as it is reaped (safely, never with --force, unlocking only its
    own session's lock); the worker stops what it started and drops its own test data."""
    procedure = (PLUGIN / "skills" / "work-tickets" / "references" / "orchestrator.md").read_text(
        encoding="utf-8"
    )
    cleanup = procedure[procedure.index("**Cleanup.**") : procedure.index("**7d.**")]
    cleanup = " ".join(cleanup.split())  # the prose wraps; match its words, not its line breaks
    for needed in ("worktree unlock", "worktree remove", "worktree prune", "never --force"):
        assert needed in cleanup, needed
    assert "another pid" in cleanup
    # A refused remove puts the lock back with its original reason; a partial one is an orphan.
    assert 'worktree lock --reason "<original reason>"' in cleanup
    assert "Worktrees kept" in cleanup and "orphan" in cleanup
    # The process check fails closed and states its blind spot.
    assert "any stderr warning" in cleanup and "Any non-zero exit" in cleanup
    assert "a cwd outside it" in cleanup and "stop what you started" in cleanup
    # One removal per worktree; a racing remove's errors are re-checked before "kept" (#47).
    assert "One removal per worktree at a time" in cleanup
    assert "`could not open directory`" in cleanup and "`is not a working tree`" in cleanup
    assert cleanup.index("Re-check first") < cleanup.index("another removal may be in progress")
    # Lock start times are compared as parsed datetimes, never as padded strings (#47).
    assert "strptime" in procedure and "never as strings" in procedure
    assert "**Cleanup**" in procedure[procedure.index("**7d.**") :]
    worker = (PLUGIN / "agents" / "ticket-worker.md").read_text(encoding="utf-8")
    final = worker[worker.index("## 10. Final report") :]
    assert "Clean up before you return" in final
    assert "FORCE" in final and "shared database server" in final
    notes = (PLUGIN / "references" / "platform-notes.md").read_text(encoding="utf-8")
    assert "about 110 worktrees" in notes
    flat = " ".join(notes.split())
    assert 'worktree lock --reason "<reason>"' in flat and "fails closed" in flat
    assert "from a cwd outside it" in flat and "stop what you started" in flat


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
    # The pre-commit review names the Codex CLI on purpose (core's optional Codex read:
    # "Codex CLI", "Codex read", `codex review`); any other Codex text is a port leftover.
    banned = re.compile(
        r"(?-i:/Users/)|\bcodex\b(?!\s+(?:review|CLI|read)\b)"
        r"|\$work-tickets|\$ticket-worker|\$write-ticket",
        re.I,
    )
    for path in PLUGIN.rglob("*"):
        if (
            path.is_file()
            and path.suffix in {".md", ".py", ".json"}
            and "evals/results" not in str(path)
        ):
            hit = banned.search(path.read_text(encoding="utf-8"))
            assert hit is None, f"{path.relative_to(PLUGIN)} mentions {hit.group(0)!r}"


def test_both_tracker_adapters_define_every_operation_the_procedures_name() -> None:
    """A procedure runs a named operation on either tracker, so each adapter lists the same
    operations, gives each a section, and covers every operation planning names."""
    trackers = PLUGIN / "references" / "trackers"
    listed = {}
    for name in ("github", "gitlab"):
        text = (trackers / f"{name}.md").read_text(encoding="utf-8")
        contents = text[text.index("## Contents") :].split("\n## ", 1)[0]
        ops = set(re.findall(r"^- ([a-z]+(?:-[a-z]+)+)$", contents, re.M))
        for op in ops:
            assert f"\n## {op}\n" in text, f"{name}.md lists {op} but has no section for it"
        listed[name] = ops
    assert listed["github"] == listed["gitlab"]
    planning = (PLUGIN / "references" / "plan-one-ticket.md").read_text(encoding="utf-8")
    named = set(re.findall(r"\*\*([a-z]+(?:-[a-z]+)+)\*\*", planning))
    assert {"read-milestone", "set-milestone"} <= named
    assert named <= listed["github"], named - listed["github"]


def test_the_worker_splits_independent_units_to_sub_workers_and_reports_the_split() -> None:
    """On 2026-11-20 two of three workers on large tickets built everything inline: the worker
    sends each independent unit to a sub-worker in its own worktree, keeps the merge, review
    and result, and the RESULT line records the split."""
    body = flat(PLUGIN / "agents" / "ticket-worker.md")
    split = body[body.index("**Split the work.**") : body.index("**Quality bar.**")]
    assert body.index("**Split the work.**") < body.index("**Merge the default branch")
    assert "Spawn every sub-worker in one message" in split
    assert "`<worktree_root>/<slot_id>/`, never a primary clone and never your own tree" in split
    assert "`model-selection.md`" in split and "`git commit -S`" in split
    assert "no attribution lines" in split and "scratch file" in split
    assert "share an interface" in split and split.index("interface") < split.index("Spawn")
    assert "Design decisions, merging, the review and the result stay with you" in split
    report = body[body.index("## 10. Final report") : body.index("## 11. Working a batch")]
    result = json.loads(report[report.index("RESULT {") + len("RESULT ") :].split("```")[0])
    assert set(result["split"]) == {"sub_workers", "kept_inline"}
    assert "`split` is always present" in report
    batches = flat(PLUGIN / "references" / "batches.md")
    assert "may be built in parallel by sub-workers" in batches


def test_the_context_preflight_names_a_script_core_ships() -> None:
    rel = "skills/project-setup/scripts/check_context_budget.py"
    orchestrator = PLUGIN / "skills/work-tickets/references/orchestrator.md"
    assert rel in orchestrator.read_text(encoding="utf-8")
    assert (PLUGIN.parent / "core" / rel).is_file()
