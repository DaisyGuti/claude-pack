"""Tests for scripts/links.py: the migration's plan and its writes, and the board fetch."""

from __future__ import annotations

from tickets_helpers import load_script

links = load_script("links")

REPO = "acme/app"


def issue(n: int, body: str = "", *blockers: tuple[str, str], title: str = "A ticket",
          labels: tuple[str, ...] = ()) -> object:  # fmt: skip
    return links.Issue(f"{REPO}#{n}", REPO, title, body, labels, tuple(blockers))


class FakeTracker(links.Tracker):
    """Answers from fixed data and records every link it is asked to add."""

    def __init__(self, issues: list, elsewhere: dict | None = None, comments: dict | None = None,
                 blockers: dict | None = None, merged: dict | None = None) -> None:  # fmt: skip
        super().__init__("example.com", run=lambda argv: "")
        self.issues, self.elsewhere = issues, elsewhere or {}
        self.comments, self.held_blockers = comments or {}, blockers or {}
        self.merged, self.added = merged or {}, []

    def open_issues(self, repo: str) -> list:
        return [i for i in self.issues if i.repo == repo]

    def blockers(self, ref: str) -> list:
        return self.held_blockers[ref]

    def resolve(self, ref: str) -> object:
        return self.elsewhere.get(ref, links.Resolved(links.Target.MISSING))

    def latest_blocked_comment(self, ref: str) -> str | None:
        return self.comments.get(ref)

    def merged_reviews(self, ref: str) -> list:
        return self.merged.get(ref, [])

    def add_blocker(self, ref: str, blocker: str) -> None:
        self.added.append((ref, blocker))


def test_old_lines_become_links_and_what_cannot_be_linked_says_why(capsys) -> None:
    board = [
        issue(1, "Depends on: #2, !7, #3, #4, #5, #6\nA note naming #9 is not read."),
        issue(2, "Depends on: #1", ("acme/app#1", "open")),
        issue(5, "Cut into parts."),
        issue(6, title="Batch: export: tidy"),
        issue(8, "Part 1 of 2, cut by layer from #5"),
        issue(10, "**Blocked: dependency**\n\nWaits on #2.", labels=("blocked",)),
        issue(11, "", labels=("blocked",)),
    ]
    tracker = FakeTracker(
        board,
        elsewhere={
            "acme/app#3": links.Resolved(links.Target.ISSUE, "closed"),
            "acme/app#4": links.Resolved(links.Target.REVIEW),
        },
        comments={
            "acme/app#10": "**Blocked: dependency**\n\nWaits on #2.\n\nUnblocks when: #2 closes.",
            "acme/app#11": "**Blocked: decision**\n\nPick #2 or #6.",
        },
        blockers={"acme/app#10": [], "acme/app#11": []},
    )
    links.migrate(tracker, [REPO], "blocked", apply=False)
    out = capsys.readouterr().out
    assert "would add: acme/app#1 blocked by acme/app#2  [body]" in out
    assert "would add: acme/app#10 blocked by acme/app#2  [Blocked comment]" in out
    assert "acme/app#1 -> review 7: a review: link its issue" in out
    assert "acme/app#1 -> acme/app#3: closed: nothing to wait on" in out
    assert "acme/app#1 -> acme/app#4: a review: link its issue" in out
    assert "acme/app#1 -> acme/app#5: a tracker: link its part (acme/app#8)" in out
    assert "acme/app#1 -> acme/app#6: a batch parent: link the child it needs" in out
    assert "#9" not in out and "acme/app#11 blocked by" not in out
    assert "1 already linked" in out and tracker.added == []


def test_apply_adds_every_planned_link_except_one_that_closes_a_cycle(capsys) -> None:
    board = [
        issue(1, "Depends on: #2"),
        issue(2, "", ("acme/app#3", "open")),
        issue(3, "Depends on: #1"),
        issue(4, "Depends on: #2"),
    ]
    tracker = FakeTracker(board)
    links.migrate(tracker, [REPO], "blocked", apply=True)
    out = capsys.readouterr().out
    assert "cycle once linked: acme/app#1 -> acme/app#2 (blocked by)" in out
    assert tracker.added == [("acme/app#4", "acme/app#2")]


def test_fetch_lists_a_held_tickets_closed_blockers_and_where_work_merged() -> None:
    review = "https://example.com/acme/app/-/merge_requests/9"
    board = [issue(1, "", labels=("blocked",)), issue(2, "", ("other/lib#4", "open"))]
    tracker = FakeTracker(
        board,
        blockers={"acme/app#1": [("acme/app#7", "closed")]},
        merged={"other/lib#4": [review]},
    )
    tickets = {t["ref"]: t for t in links.fetch(tracker, [REPO], "blocked")["tickets"]}
    assert tickets["acme/app#1"]["blocked_by"] == ["acme/app#7"]
    assert tickets["acme/app#7"]["state"] == "closed"
    assert tickets["other/lib#4"]["state"] == "open"
    assert tickets["acme/app#2"]["blocked_by"] == ["other/lib#4"]
    assert tickets["other/lib#4"]["merged_reviews"] == [review]


def test_github_reads_each_page_of_a_paginated_answer() -> None:
    pages = '{"data": {"repository": {"issues": {"nodes": [NODE]}}}}'
    node = (
        '{"number": %d, "title": "T", "body": null, "labels": {"nodes": [{"name": "blocked"}]},'
        ' "blockedBy": {"nodes": [{"number": 3, "state": "CLOSED",'
        ' "repository": {"nameWithOwner": "Acme/App"}}]}}'
    )
    out = pages.replace("NODE", node % 1) + "\n" + pages.replace("NODE", node % 2)
    tracker = links.GitHub("github.com", run=lambda argv: out)
    found = tracker.open_issues("Acme/App")
    assert [i.ref for i in found] == ["acme/app#1", "acme/app#2"]
    assert found[0].blockers == (("acme/app#3", "closed"),)


def test_a_scope_links_only_the_tickets_in_its_milestone_with_its_labels(capsys) -> None:
    board = [
        links.Issue(f"{REPO}#1", REPO, "T", "Depends on: #9", ("team:a",), (), "v0.3"),
        links.Issue(f"{REPO}#2", REPO, "T", "Depends on: #9", ("team:b",), (), "v0.3"),
        links.Issue(f"{REPO}#3", REPO, "T", "Depends on: #9", ("team:a",), (), "v0.4"),
        links.Issue(f"{REPO}#9", REPO, "T", "", (), (), None),
    ]
    tracker = FakeTracker(board)
    links.migrate(tracker, [REPO], "blocked", True, links.Scope("v0.3", ("team:a",)))
    assert tracker.added == [("acme/app#1", "acme/app#9")]
