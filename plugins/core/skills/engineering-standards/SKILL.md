---
name: engineering-standards
description: >-
  Loads the pack's engineering standards: the rules for building, reviewing and planning a
  code change in any repo (design patterns, loops and string literals, typed models, DRY,
  dead code, tests, refactors, exported bytes, the docs pass, gates and landing). Agents in
  other plugins preload it to reach the one shared copy. Use when asked what the
  engineering standards say, or before writing, reviewing or planning code when an agent or
  skill tells you to load them, even if the user does not name the standards.
user-invocable: false
---

# Engineering standards

Read `${CLAUDE_PLUGIN_ROOT}/skills/eng/references/engineering-standards.md` in full before
you write, review or plan code. It is the one copy of the rules; this skill only points to
it. The repo's own CLAUDE.md, AGENTS.md and CONTRIBUTING.md win every question of house
style.

When the user only asked what the standards say, answer from that file and quote the rule
titles you used.
