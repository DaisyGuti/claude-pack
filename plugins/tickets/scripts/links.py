#!/usr/bin/env python3
"""Read the board's native blocked-by links, and turn old `Depends on:` lines into links.

A dependency is a native link: GitLab's `is_blocked_by` issue link, GitHub's issue dependency
("Blocked by"). This script makes the same calls as the tracker adapters' **list-blockers** and
**add-blocker** operations, for many issues at once.

`fetch` writes `deps.py`'s input for the named repos: every open issue with its title, body and
blockers, an entry for each blocker outside that list (with its state, so `deps.py` reports
nothing unknown), and `merged_reviews` for each open blocker (**merged-reviews**). A ticket
carrying the blocked label has its blockers read one by one, so a closed blocker is listed even
where the board-wide read leaves it out.

`migrate` reads the `Depends on:`, `Blocked by:` and `Blocked on:` lines in each open issue's
body, and every issue named in the latest `**Blocked: dependency**` comment of a ticket carrying
the blocked label, and plans one blocked-by link per ref. It does not link, and lists with the
reason, a ref to a review (an MR or pull request: link that review's issue instead), to an issue
that is closed or missing, or to a tracker or batch parent (with its open parts). It then runs
`deps.py`'s cycle check on the links as they would be. It links only within the `--repo`
list, and reads a `Blocked:` comment only from someone who can write to the repo, since what
it reads decides what `--apply` adds; a person reads the dry run before anyone applies it.
`--milestone` and `--label` narrow it to blocked tickets in that milestone carrying every
named label (a board view); a blocker may be anywhere. Without `--apply` it changes nothing.
With `--apply` it adds each planned link, except those on a cycle, and leaves the body text as
it is.

Usage:
    links.py fetch --tracker {github,gitlab} --host HOST --blocked-label NAME --repo REMOTE...
    links.py migrate --tracker {github,gitlab} --host HOST --blocked-label NAME --repo REMOTE...
        [--milestone TITLE] [--label NAME]... [--apply]

Exit codes: 0 done, 1 a tracker call failed (or, with --apply, a link could not be added),
2 bad input.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any
from urllib.parse import quote

if sys.version_info < (3, 11):  # noqa: UP036  (a clear message on an older python3)
    sys.exit("links.py needs Python 3.11 or newer; install it and run this again")

import deps  # noqa: E402  (after the version check, like the other scripts' imports)

EXIT_TRACKER = 1
OPEN, CLOSED = deps.OPEN, deps.CLOSED
# The old body lines that named a dependency, read only to migrate them.
DEPENDS_LINE = re.compile(r"^\W*(?:depends on|blocked (?:by|on))\b:?(.*)$", re.IGNORECASE)
BLOCKED_COMMENT = re.compile(r"^\s*\*\*Blocked:\s*(?P<kind>[\w ]+?)\s*\*\*", re.IGNORECASE)
DEPENDENCY_KIND = "dependency"
# A review named where an issue belongs: `!12`, or a merge request or pull request URL.
REVIEW_REF = re.compile(
    r"(?<![\w!])!(?P<n>\d+)\b|https?://\S+?/(?:-/merge_requests|pull)/(?P<url_n>\d+)"
)
# Who can write to a repo: GitHub's comment author association, GitLab's Developer access level.
WRITERS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
DEVELOPER_ACCESS = 30
# A batch parent's title (batches.md, "A batch parent's title").
BATCH_TITLE = "Batch: "
NOT_FOUND = re.compile(r"HTTP 404\b|404 Not found|Could not resolve to")


class TrackerError(Exception):
    """A tracker CLI call failed or answered with something unexpected."""


Run = Callable[[Sequence[str]], str]


def run_cli(argv: Sequence[str]) -> str:
    """Run a tracker CLI command and return its stdout; a non-zero exit is a TrackerError."""
    proc = subprocess.run(list(argv), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise TrackerError(f"'{' '.join(argv[:5])}' exited {proc.returncode}: {detail}")
    return proc.stdout


def json_documents(text: str) -> list[Any]:
    """Every JSON document in a CLI's output (a paginated call prints one per page)."""
    decoder, docs, at = json.JSONDecoder(), [], 0
    text = text.strip()
    while at < len(text):
        try:
            doc, at = decoder.raw_decode(text, at)
        except json.JSONDecodeError as err:
            raise TrackerError(
                f"the tracker CLI printed something that is not JSON ({err})"
            ) from err
        docs.append(doc)
        while at < len(text) and text[at].isspace():
            at += 1
    return docs


def split_ref(ref: str) -> tuple[str, int]:
    repo, _, number = ref.rpartition("#")
    return repo, int(number)


class Target(Enum):
    """What a ref names, as the tracker sees it."""

    ISSUE = "issue"
    REVIEW = "review"
    MISSING = "missing"


@dataclass(frozen=True)
class Resolved:
    target: Target
    state: str = OPEN


@dataclass(frozen=True)
class Issue:
    """One open issue: its text and its current blockers as (ref, state)."""

    ref: str
    repo: str
    title: str
    body: str
    labels: tuple[str, ...]
    blockers: tuple[tuple[str, str], ...]
    milestone: str | None = None


@dataclass(frozen=True)
class Scope:
    """Which blocked tickets `migrate` links: in this milestone and carrying every label."""

    milestone: str | None = None
    labels: tuple[str, ...] = ()

    def covers(self, issue: Issue) -> bool:
        in_milestone = self.milestone is None or issue.milestone == self.milestone
        return in_milestone and all(label in issue.labels for label in self.labels)


EVERY_TICKET = Scope()


class Tracker:
    """The calls both trackers answer; each subclass runs its own CLI."""

    cli: str

    def __init__(self, host: str, run: Run = run_cli) -> None:
        self.host = host
        self.run = run

    def api(self, *args: str) -> str:
        return self.run([self.cli, "api", "--hostname", self.host, *args])

    def open_issues(self, repo: str) -> list[Issue]:
        raise NotImplementedError

    def blockers(self, ref: str) -> list[tuple[str, str]]:
        """Every issue blocking one issue, open or closed, as (ref, state)."""
        raise NotImplementedError

    def resolve(self, ref: str) -> Resolved:
        raise NotImplementedError

    def latest_blocked_comment(self, ref: str) -> str | None:
        raise NotImplementedError

    def merged_reviews(self, ref: str) -> list[str]:
        raise NotImplementedError

    def add_blocker(self, ref: str, blocker: str) -> None:
        raise NotImplementedError


def refs_line(repo: str, number: int) -> str:
    return f"{repo.lower()}#{number}"


def refs_test(number: int, url_kinds: str) -> str:
    """The jq test for a `Refs` line naming issue <number> (tracker adapters, merged-reviews)."""
    return f'any(test("^\\\\W*refs?\\\\b"; "i") and test("(#|/(?:{url_kinds})/){number}(\\\\D|$)"))'


class GitHub(Tracker):
    cli = "gh"
    ISSUES = """query($owner: String!, $name: String!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    issues(states: OPEN, first: 100, after: $endCursor) {
      pageInfo { hasNextPage endCursor }
      nodes { number title body milestone { title } labels(first: 50) { nodes { name } }
        blockedBy(first: 100) { nodes { number state repository { nameWithOwner } } } }
    }
  }
}"""

    def open_issues(self, repo: str) -> list[Issue]:
        owner, name = repo.split("/", 1)
        out = self.api(
            "graphql", "--paginate", "-f", f"owner={owner}", "-f", f"name={name}",
            "-f", f"query={self.ISSUES}",
        )  # fmt: skip
        issues = []
        for page in json_documents(out):
            for node in page["data"]["repository"]["issues"]["nodes"]:
                blockers = tuple(
                    (refs_line(b["repository"]["nameWithOwner"], b["number"]), b["state"].lower())
                    for b in node["blockedBy"]["nodes"]
                )
                issues.append(
                    Issue(
                        ref=refs_line(repo, node["number"]),
                        repo=repo,
                        title=node["title"],
                        body=node["body"] or "",
                        labels=tuple(label["name"] for label in node["labels"]["nodes"]),
                        blockers=blockers,
                        milestone=(node.get("milestone") or {}).get("title"),
                    )
                )
        return issues

    def blockers(self, ref: str) -> list[tuple[str, str]]:
        repo, n = split_ref(ref)
        out = self.api(
            "--paginate", f"repos/{repo}/issues/{n}/dependencies/blocked_by?per_page=100"
        )
        return [
            (refs_line(b["repository_url"].split("/repos/", 1)[1], b["number"]), b["state"])
            for page in json_documents(out)
            for b in page
        ]

    def issue(self, ref: str) -> dict[str, Any]:
        repo, n = split_ref(ref)
        return dict(json_documents(self.api(f"repos/{repo}/issues/{n}"))[0])

    def resolve(self, ref: str) -> Resolved:
        try:
            found = self.issue(ref)
        except TrackerError as err:
            if NOT_FOUND.search(str(err)):
                return Resolved(Target.MISSING)
            raise
        target = Target.REVIEW if "pull_request" in found else Target.ISSUE
        return Resolved(target, found["state"])

    def latest_blocked_comment(self, ref: str) -> str | None:
        repo, n = split_ref(ref)
        out = self.api("--paginate", f"repos/{repo}/issues/{n}/comments?per_page=100")
        # Only a comment by someone who can write to the repo counts: on a public repo anyone
        # may comment, and a comment here decides which links `--apply` adds.
        bodies = [
            c["body"] or ""
            for page in json_documents(out)
            for c in page
            if c.get("author_association") in WRITERS
        ]
        return next((b for b in reversed(bodies) if BLOCKED_COMMENT.match(b)), None)

    def merged_reviews(self, ref: str) -> list[str]:
        repo, n = split_ref(ref)
        default = self.run(
            ["gh", "repo", "view", repo, "--json", "defaultBranchRef", "--jq",
             ".defaultBranchRef.name"]
        ).strip()  # fmt: skip
        jq = (
            '[.[] | select(.event == "cross-referenced" and '
            ".source.issue.pull_request.merged_at != null) | .source.issue"
            f' | select(.repository.full_name | ascii_downcase == "{repo.lower()}")'
            f' | select((.body // "") | split("\\n") | {refs_test(n, "issues")})'
            " | {number, url: .html_url}]"
        )
        out = self.api("--paginate", f"repos/{repo}/issues/{n}/timeline?per_page=100", "--jq", jq)
        urls = []
        for page in json_documents(out):
            for review in page:
                base = self.run(
                    ["gh", "pr", "view", str(review["number"]), "--repo", repo, "--json",
                     "baseRefName", "--jq", ".baseRefName"]
                ).strip()  # fmt: skip
                if base == default:
                    urls.append(review["url"])
        return list(dict.fromkeys(urls))

    def add_blocker(self, ref: str, blocker: str) -> None:
        repo, n = split_ref(ref)
        blocker_id = self.issue(blocker)["id"]
        self.api(
            "-X", "POST", f"repos/{repo}/issues/{n}/dependencies/blocked_by",
            "-F", f"issue_id={blocker_id}",
        )  # fmt: skip


class GitLab(Tracker):
    cli = "glab"
    ISSUES = """query($path: ID!, $endCursor: String) {
  project(fullPath: $path) {
    issues(state: opened, first: 100, after: $endCursor) {
      pageInfo { hasNextPage endCursor }
      nodes { iid title description milestone { title } labels { nodes { title } }
        blockedByIssues { nodes { state reference(full: true) } } }
    }
  }
}"""

    def __init__(self, host: str, run: Run = run_cli) -> None:
        super().__init__(host, run)
        self.projects: dict[str, dict[str, Any]] = {}
        self.writers: dict[tuple[str, int], bool] = {}

    def project(self, repo: str) -> dict[str, Any]:
        if repo not in self.projects:
            self.projects[repo] = dict(
                json_documents(self.api(f"projects/{quote(repo, safe='')}"))[0]
            )
        return self.projects[repo]

    @staticmethod
    def state(value: str) -> str:
        return OPEN if value in ("opened", "OPENED", "open") else CLOSED

    def open_issues(self, repo: str) -> list[Issue]:
        out = self.api("graphql", "--paginate", "-f", f"path={repo}", "-f", f"query={self.ISSUES}")
        issues = []
        for page in json_documents(out):
            for node in page["data"]["project"]["issues"]["nodes"]:
                blockers = tuple(
                    (b["reference"].lower(), self.state(b["state"]))
                    for b in node["blockedByIssues"]["nodes"]
                )
                issues.append(
                    Issue(
                        ref=refs_line(repo, int(node["iid"])),
                        repo=repo,
                        title=node["title"],
                        body=node["description"] or "",
                        labels=tuple(label["title"] for label in node["labels"]["nodes"]),
                        blockers=blockers,
                        milestone=(node.get("milestone") or {}).get("title"),
                    )
                )
        return issues

    def blockers(self, ref: str) -> list[tuple[str, str]]:
        repo, n = split_ref(ref)
        out = self.api(f"projects/{quote(repo, safe='')}/issues/{n}/links")
        return [
            (link["references"]["full"].lower(), self.state(link["state"]))
            for page in json_documents(out)
            for link in page
            if link["link_type"] == "is_blocked_by"
        ]

    def resolve(self, ref: str) -> Resolved:
        repo, n = split_ref(ref)
        try:
            found = json_documents(self.api(f"projects/{quote(repo, safe='')}/issues/{n}"))[0]
        except TrackerError as err:
            if NOT_FOUND.search(str(err)):
                return Resolved(Target.MISSING)
            raise
        return Resolved(Target.ISSUE, self.state(found["state"]))

    def latest_blocked_comment(self, ref: str) -> str | None:
        repo, n = split_ref(ref)
        out = self.api(
            "--paginate", "--output", "ndjson",
            f"projects/{quote(repo, safe='')}/issues/{n}/notes?sort=desc&order_by=created_at"
            "&per_page=100",
        )  # fmt: skip
        for note in json_documents(out):
            body = note.get("body") or ""
            if note.get("system") or not BLOCKED_COMMENT.match(body):
                continue
            # Only a comment by a Developer or above counts (see GitHub's note above).
            if self.can_write(repo, int(note["author"]["id"])):
                return str(body)
        return None

    def can_write(self, repo: str, user_id: int) -> bool:
        key = (repo, user_id)
        if key not in self.writers:
            try:
                member = json_documents(
                    self.api(f"projects/{quote(repo, safe='')}/members/all/{user_id}")
                )[0]
                self.writers[key] = int(member.get("access_level", 0)) >= DEVELOPER_ACCESS
            except TrackerError as err:
                if not NOT_FOUND.search(str(err)):
                    raise
                self.writers[key] = False
        return self.writers[key]

    def merged_reviews(self, ref: str) -> list[str]:
        repo, n = split_ref(ref)
        project = self.project(repo)
        out = self.api(
            "--paginate", "--output", "ndjson",
            f"projects/{quote(repo, safe='')}/issues/{n}/related_merge_requests?per_page=100",
        )  # fmt: skip
        urls = []
        for mr in json_documents(out):
            lines = (mr.get("description") or "").splitlines()
            refs = any(
                re.match(r"^\W*refs?\b", line, re.IGNORECASE)
                and re.search(rf"(#|/(?:issues|work_items)/){n}(\D|$)", line)
                for line in lines
            )
            if (
                refs
                and mr["state"] == "merged"
                and mr["project_id"] == project["id"]
                and mr["target_branch"] == project["default_branch"]
            ):
                urls.append(mr["web_url"])
        return urls

    def add_blocker(self, ref: str, blocker: str) -> None:
        repo, n = split_ref(ref)
        blocker_repo, blocker_n = split_ref(blocker)
        self.api(
            "-X", "POST", f"projects/{quote(repo, safe='')}/issues/{n}/links",
            "-f", f"target_project_id={self.project(blocker_repo)['id']}",
            "-f", f"target_issue_iid={blocker_n}", "-f", "link_type=is_blocked_by",
        )  # fmt: skip


TRACKERS: dict[str, type[Tracker]] = {"github": GitHub, "gitlab": GitLab}


@dataclass
class Board:
    """The open issues of the named repos, each with its blockers as the tracker holds them."""

    issues: list[Issue]
    blocked_label: str
    repos: frozenset[str] = frozenset()

    def held(self, issue: Issue) -> bool:
        return self.blocked_label in issue.labels


def read_board(tracker: Tracker, repos: Sequence[str], blocked_label: str) -> Board:
    issues = []
    for repo in repos:
        for issue in tracker.open_issues(repo):
            if blocked_label in issue.labels:
                # The board-wide read may leave out a closed blocker; a held ticket needs them all.
                issue = replace(issue, blockers=tuple(tracker.blockers(issue.ref)))
            issues.append(issue)
    return Board(issues, blocked_label, frozenset(repo.lower() for repo in repos))


def deps_input(
    board: Board,
    extra_links: Sequence[tuple[str, str]] = (),
    merged: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """`deps.py`'s input: the open issues with their blockers (plus any planned links), and an
    entry with its state for each blocker outside them."""
    planned: dict[str, list[str]] = {}
    for ref, blocker in extra_links:
        planned.setdefault(ref, []).append(blocker)
    merged = merged or {}
    tickets: list[dict[str, Any]] = []
    known = {issue.ref for issue in board.issues}
    outside: dict[str, str] = {}
    for issue in board.issues:
        blocked_by = [b for b, _ in issue.blockers] + planned.get(issue.ref, [])
        entry: dict[str, Any] = {
            "ref": issue.ref,
            "repo": issue.repo,
            "state": OPEN,
            "title": issue.title,
            "body": issue.body,
            "blocked_by": list(dict.fromkeys(blocked_by)),
        }
        if merged.get(issue.ref):
            entry["merged_reviews"] = merged[issue.ref]
        tickets.append(entry)
        for ref, state in issue.blockers:
            if ref not in known:
                outside[ref] = state
    for ref, state in sorted(outside.items()):
        entry = {"ref": ref, "repo": split_ref(ref)[0], "state": state}
        if merged.get(ref):
            entry["merged_reviews"] = merged[ref]
        tickets.append(entry)
    return {"tickets": tickets}


def fetch(tracker: Tracker, repos: Sequence[str], blocked_label: str) -> dict[str, Any]:
    board = read_board(tracker, repos, blocked_label)
    named = {b for issue in board.issues for b, state in issue.blockers if state == OPEN}
    merged = {ref: urls for ref in sorted(named) if (urls := tracker.merged_reviews(ref))}
    return deps_input(board, merged=merged)


@dataclass(frozen=True)
class Planned:
    ref: str
    blocker: str
    source: str


@dataclass(frozen=True)
class NotLinked:
    ref: str
    named: str
    reason: str
    source: str


@dataclass
class Migration:
    links: list[Planned] = field(default_factory=list)
    already: list[Planned] = field(default_factory=list)
    not_linked: list[NotLinked] = field(default_factory=list)
    cycles: list[list[dict[str, str]]] = field(default_factory=list)

    def on_a_cycle(self, link: Planned) -> bool:
        return any(
            step["from"] == link.ref and step["to"] == link.blocker
            for cycle in self.cycles
            for step in cycle
        )


def named_dependencies(issue: Issue, comment: str | None) -> list[tuple[str, str]]:
    """(text, source) for each body dependency line, and the latest `Blocked: dependency`
    comment."""
    found = [
        (m.group(1), "body") for line in issue.body.splitlines() if (m := DEPENDS_LINE.match(line))
    ]
    kind = BLOCKED_COMMENT.match(comment or "")
    if comment and kind and kind.group("kind").strip().lower() == DEPENDENCY_KIND:
        found.append((comment[kind.end() :], "Blocked comment"))
    return found


def plan_migration(
    board: Board,
    resolve: Callable[[str], Resolved],
    comments: dict[str, str | None],
    scope: Scope = EVERY_TICKET,
) -> Migration:
    """The links to add, and each named ref that is not linked with why. Calls no write."""
    plan = Migration()
    tracker_board = deps.build_board([deps.parse_ticket(t) for t in deps_input(board)["tickets"]])
    by_ref = {issue.ref: issue for issue in board.issues}
    resolved: dict[str, Resolved] = {}
    for issue in board.issues:
        if not scope.covers(issue):
            continue
        linked = {b for b, _ in issue.blockers}
        seen: set[str] = set()
        for text, source in named_dependencies(issue, comments.get(issue.ref)):
            for review in REVIEW_REF.finditer(text):
                number = review.group("n") or review.group("url_n")
                plan.not_linked.append(
                    NotLinked(issue.ref, f"review {number}", "a review: link its issue", source)
                )
            for named in deps.refs_in(issue.repo, text):
                if named == issue.ref or named in seen:
                    continue
                seen.add(named)
                if named in linked:
                    plan.already.append(Planned(issue.ref, named, source))
                    continue
                if board.repos and split_ref(named)[0] not in board.repos:
                    plan.not_linked.append(
                        NotLinked(issue.ref, named, "outside the named repos", source)
                    )
                    continue
                if named not in resolved:
                    in_board = by_ref.get(named)
                    resolved[named] = Resolved(Target.ISSUE) if in_board else resolve(named)
                found = resolved[named]
                reason = None
                if found.target is Target.REVIEW:
                    reason = "a review: link its issue"
                elif found.target is Target.MISSING:
                    reason = "not found"
                elif found.state != OPEN:
                    reason = "closed: nothing to wait on"
                elif (parent := by_ref.get(named)) and parent.title.startswith(BATCH_TITLE):
                    reason = "a batch parent: link the child it needs"
                elif parts := tracker_board.part_numbers.get(named):
                    open_parts = [p for p in sorted(parts, key=parts.__getitem__) if p in by_ref]
                    reason = f"a tracker: link its part ({', '.join(open_parts) or 'none open'})"
                if reason:
                    plan.not_linked.append(NotLinked(issue.ref, named, reason, source))
                else:
                    plan.links.append(Planned(issue.ref, named, source))
    to_be = deps_input(board, [(link.ref, link.blocker) for link in plan.links])
    board_to_be = deps.build_board([deps.parse_ticket(t) for t in to_be["tickets"]])
    plan.cycles = [
        [{"from": a, "to": b, "via": via.value} for a, b, via in cycle]
        for cycle in deps.find_cycles(board_to_be)
    ]
    return plan


def migrate(
    tracker: Tracker,
    repos: Sequence[str],
    blocked_label: str,
    apply: bool,
    scope: Scope = EVERY_TICKET,
) -> int:
    board = read_board(tracker, repos, blocked_label)
    comments = {
        issue.ref: tracker.latest_blocked_comment(issue.ref)
        for issue in board.issues
        if board.held(issue) and scope.covers(issue)
    }
    plan = plan_migration(board, tracker.resolve, comments, scope)
    verb = "add" if apply else "would add"
    for link in plan.links:
        note = "  (on a cycle: not added)" if plan.on_a_cycle(link) else ""
        print(f"{verb}: {link.ref} blocked by {link.blocker}  [{link.source}]{note}")
    for miss in plan.not_linked:
        print(f"not linked: {miss.ref} -> {miss.named}: {miss.reason}  [{miss.source}]")
    for cycle in plan.cycles:
        chain = " -> ".join([cycle[0]["from"]] + [f"{s['to']} ({s['via']})" for s in cycle])
        print(f"cycle once linked: {chain}")
    failed = 0
    if apply:
        for link in plan.links:
            if plan.on_a_cycle(link):
                continue
            try:
                tracker.add_blocker(link.ref, link.blocker)
            except TrackerError as err:
                failed += 1
                print(f"failed: {link.ref} blocked by {link.blocker}: {err}", file=sys.stderr)
    on_cycles = sum(plan.on_a_cycle(link) for link in plan.links)
    print(
        f"summary: {len(plan.links)} links to add ({on_cycles} on a cycle), "
        f"{len(plan.already)} already linked, {len(plan.not_linked)} not linked, "
        f"{len(plan.cycles)} cycles once linked"
        + (f", {failed} failed" if apply else ", nothing changed (dry run)")
    )
    return EXIT_TRACKER if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch", "migrate"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--tracker", choices=sorted(TRACKERS), required=True)
        cmd.add_argument("--host", required=True)
        cmd.add_argument("--blocked-label", required=True)
        cmd.add_argument("--repo", action="append", required=True, help="a registry Remote")
        if name == "migrate":
            cmd.add_argument("--apply", action="store_true", help="add the links")
            cmd.add_argument("--milestone", help="only tickets in this milestone")
            cmd.add_argument(
                "--label", action="append", default=[], help="only tickets with this label"
            )
    args = parser.parse_args(argv)
    # Each line shows as it is printed, so a long run can be watched and stopped.
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    tracker = TRACKERS[args.tracker](args.host)
    try:
        if args.command == "fetch":
            print(json.dumps(fetch(tracker, args.repo, args.blocked_label), indent=2))
            return 0
        scope = Scope(args.milestone, tuple(args.label))
        return migrate(tracker, args.repo, args.blocked_label, args.apply, scope)
    except (TrackerError, KeyError, TypeError, ValueError) as exc:
        print(f"links.py: {exc}", file=sys.stderr)
        return EXIT_TRACKER


if __name__ == "__main__":
    sys.exit(main())
