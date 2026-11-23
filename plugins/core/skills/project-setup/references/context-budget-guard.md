# The context-budget guard

Install this only after the user says yes. It fails CI when an agent instruction file passes
the size limit, and a ratchet keeps a file that is already large from growing.

## Install

1. Copy `${CLAUDE_SKILL_DIR}/scripts/check_context_budget.py` into the repo's own scripts folder
   (`scripts/` or the folder the repo already uses). It is standard library only, so the copy
   needs nothing installed. Keep it executable.
2. From the repo root, run `python3 <copy> . --all --write-baseline`. It writes `.context-budget.toml`
   with the default limits (40 KB per file, 60 KB in total) and a `[baseline]` entry for each file
   that is over the limit now. A baselined file may not grow, and when it shrinks the check fails
   until `--write-baseline` lowers its entry, so the entry only goes down (it never raises one). Show the file to the
   user. Raising a limit or a baseline is the user's call, never this skill's.
3. Add one entry that runs `python3 <copy> . --all`, in the form the repo already uses for checks: a
   Makefile target, a package script, a pre-commit hook, a test, or a step in the existing CI
   job. Match the repo's own commands (the scan lists them). Add no new CI job when an existing
   one can run it.
4. Run the entry once and confirm it exits 0. Print the diff and leave landing to the user.

## What it tells a failing author

The output names each file that is over and by how many bytes. The fix is to move the new text
into an area guide and link it from the index (progressive disclosure), not to raise a limit.
`--all` counts every CLAUDE.md and AGENTS.md in the repo and enforces the per-file limit and
the baselines, not the total; `--path <folder>` counts the guides on
the way to one folder, for a check of one area.

The limits live in `.context-budget.toml` at the repo root: `guide_bytes`, `total_bytes` and a
`[baseline]` table of `"path" = bytes`.
