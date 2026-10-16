## Context

<One paragraph. What this is, why it exists, and what it is conditional on. Name the bet or the failure it answers.>

## Acceptance Criteria

- <Concrete and checkable by someone who did not write the ticket>
- <Name the file, route, library, gate or observable behaviour>
- <Include the performance or quality target where there is one, with its number>

## Out of scope

- <Only what a reader would otherwise reasonably include. Say which version it belongs to when it is deferred.>

## Dependencies

Depends on: <#87, group/project#66, or None>

## Agent Prompt

> <One paragraph a worker can act on without reading the rest. State the target, the constraints, and the numbers. End with: *If any step requires credentials the developer must enter manually, stop and prompt the user rather than guessing.*>

---

## Agent Instructions

### 1. Review the existing codebase first
- Review current dependencies in `package.json` (or `requirements.txt` / `pubspec.yaml` / `pyproject.toml`)
- Identify existing patterns for the relevant area: env loading, API calls, polling, rendering, etc.
- Note any existing tests or fixtures that should be reused

### 2. If a required library is not yet set up, recommend the best-in-class option
Prefer libraries that are:
- Well-maintained with recent activity
- High stars and strong community adoption
- Officially supported or backed

### 3. Do not assume any specific library is in use
Evaluate first, then build using whatever is already there — or recommend an upgrade if the current choice is outdated or poorly supported.

### 4. Standards to follow
- Follow and reuse existing styles and UI — improve only to meet best industry standards for <the audience from this repo's brief, or "this repo's existing users" when the brief names none>
- Use best-in-class industry coding standard design patterns
- Zero console errors or warnings when complete
- Update setup and run scripts if anything changes
- Add file-level doc comments to all new files, inline comments on complex logic, and TODOs where future work is needed
- Write or create tests for all changes
- Update README to reflect any new dependencies, endpoints, or run instructions

### 5. Commit
When complete, create a concise git commit message that resolves this ticket. The closing commit message must use the `Closes #<ticket-number>` keyword so the ticket auto-closes on merge, and the worker should comment on the ticket with the review link, confirming acceptance criteria are met and tests pass.
