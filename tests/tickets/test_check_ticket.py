"""Tests for scripts/check_ticket.py: a filled ticket must keep the template's shape."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "tickets"
SCRIPTS = PLUGIN / "scripts"


def load_script(name: str) -> ModuleType:
    """Import plugins/tickets/scripts/<name>.py (the scripts are not a package)."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(f"tickets_{name}", SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"tickets_{name}"] = module
    spec.loader.exec_module(module)
    return module


check_ticket = load_script("check_ticket")
TEMPLATE = (PLUGIN / "skills" / "write-ticket" / "assets" / "ticket-template.md").read_text(
    encoding="utf-8"
)
AUDIENCE_PLACEHOLDER = (
    "<the audience from this repo's brief, "
    'or "this repo\'s existing users" when the brief names none>'
)

TOP = """## Context

The signup form accepts an email with no domain, so invalid accounts reach the mailer.

## Acceptance Criteria

- The form in `src/signup.ts` rejects `a@b` and shows the existing error style
- A unit test covers the rejected case

## Out of scope

- Checking that the mailbox exists.

## Dependencies

Depends on: None

## Agent Prompt

> Reject emails with no top-level domain in `src/signup.ts` and add a test. *If any step requires
> credentials the developer must enter manually, stop and prompt the user rather than guessing.*

---

"""


def make_body(audience: str = "clinic staff who sign patients up") -> str:
    instructions = TEMPLATE[TEMPLATE.index("## Agent Instructions") :]
    return TOP + instructions.replace(AUDIENCE_PLACEHOLDER, audience)


def problems_for(body: str) -> list[str]:
    return check_ticket.check(body, TEMPLATE)[0]


def test_a_filled_ticket_passes() -> None:
    assert problems_for(make_body()) == []


def test_the_unfilled_template_fails_on_every_top_section() -> None:
    found = problems_for(TEMPLATE)
    assert any("'## Context'" in p for p in found)
    assert any("'## Agent Prompt'" in p for p in found)
    assert any("audience placeholder" in p for p in found)


def test_out_of_scope_may_be_omitted() -> None:
    body = make_body().replace("## Out of scope\n\n- Checking that the mailbox exists.\n\n", "")
    assert problems_for(body) == []


def test_missing_dependencies_line_is_reported() -> None:
    body = make_body().replace("Depends on: None", "Nothing yet")
    assert any("Depends on" in p for p in problems_for(body))


def test_edited_boilerplate_is_reported() -> None:
    body = make_body().replace("Prefer libraries that are:", "Prefer libraries that are cheap:")
    assert any("'### 2." in p and "exact copy" in p for p in problems_for(body))


def test_removed_commit_section_is_reported() -> None:
    body = make_body()
    body = body[: body.index("### 5. Commit")]
    assert any("missing '### 5. Commit'" in p for p in problems_for(body))


def test_extra_bullet_in_standards_is_reported() -> None:
    body = make_body().replace(
        "- Write or create tests for all changes",
        "- Skip tests\n- Write or create tests for all changes",
    )
    assert any("beyond its audience" in p for p in problems_for(body))


def test_too_many_acceptance_bullets_say_to_split() -> None:
    bullets = "\n".join(f"- Criterion {i} is checked in `src/a{i}.ts`" for i in range(9))
    body = make_body().replace(
        "- The form in `src/signup.ts` rejects `a@b` and shows the existing error style\n"
        "- A unit test covers the rejected case",
        bullets,
    )
    found, count = check_ticket.check(body, TEMPLATE)
    assert count == 9
    assert any("split the ticket" in p for p in found)


def test_missing_instructions_heading_is_reported() -> None:
    body = make_body().split("## Agent Instructions")[0]
    assert any("Agent Instructions" in p for p in problems_for(body))


def test_command_line_exit_codes(tmp_path: Path) -> None:
    good = tmp_path / "good.md"
    good.write_text(make_body(), encoding="utf-8")
    bad = tmp_path / "bad.md"
    bad.write_text("just text", encoding="utf-8")
    ok = subprocess.run(
        [sys.executable, str(SCRIPTS / "check_ticket.py"), str(good)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ok.returncode == 0
    assert json.loads(ok.stdout)["ok"] is True
    failed = subprocess.run(
        [sys.executable, str(SCRIPTS / "check_ticket.py"), str(bad)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode == 1
    missing = subprocess.run(
        [sys.executable, str(SCRIPTS / "check_ticket.py"), str(tmp_path / "none.md")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode == 2
    assert "none.md" in missing.stderr
