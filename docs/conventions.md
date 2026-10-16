# Conventions for every skill, agent and hook in this repo

Every author reads this before writing. Rule numbers in parentheses (G55, G94) point to
the numbered rules in [`authoring-guide.md`](authoring-guide.md), which holds Anthropic's
current rules with a source URL for each. Where this file and the guide differ, the guide
is the platform fact and this file is the house choice built on it.

## Who touches what

1. **Own your plugin.** Each engineer edits only `plugins/<their plugin>/` and
   `tests/<their plugin>/`.
2. **Shared files go through the integrator.** These change only through the integrator:
   `.claude-plugin/marketplace.json`, `pyproject.toml`, `README.md`,
   `THIRD_PARTY_NOTICES.md`, `docs/`, `scripts/`, `.gitignore`. If you need a change in
   one, say so in your hand-off message.
3. **Official first.** Before building, check
   `~/.claude/plugins/marketplaces/claude-plugins-official/` (plugins and
   `external_plugins`). Where an official plugin already covers the job, the README
   recommends installing it and this repo builds only the gap. Today that includes
   `claude-security`, `security-guidance`, `code-review`, `pr-review-toolkit`,
   `feature-dev`, `frontend-design`, `claude-md-management`, `claude-code-setup`,
   `commit-commands`, `hookify`, `skill-creator`, `session-report`, and the `github` and
   `gitlab` integrations. Re-read that folder at build time; the list moves.

## Team-safe content

4. **Nothing personal.** No personal names, no references to any author's other companies,
   brands or private tools, no personal subscriptions, no machine paths such as `/Users/...`
   or `~/<project>`. Anything committed here reaches every teammate who installs it.
5. **No secrets and no customer data** in any file, fixture or eval.
6. **Third-party material.** Vet it before it lands: read every bundled file, check the
   license, and keep the upstream license text in the skill folder as `LICENSE.txt`. Report
   the upstream, license and files to the integrator, who adds the row to
   `THIRD_PARTY_NOTICES.md` (G54).

## Platform choices

7. **GitHub and GitLab parity.** Wherever a tracker, pull request or merge request, or CI
   is involved, the skill covers both. The team is on GitHub now and moving to GitLab.
   Use `gh` and `glab`; put per-host commands in a reference file so the main instructions
   stay host-neutral.
8. **GCP first** for cloud. **Docker** for containers.
9. **Free open-source tools first**: trivy, grype, syft, cosign, gitleaks, semgrep CE,
   hadolint, dockle, checkov, osv-scanner, zizmor. A paid tool appears only as a noted
   alternative. List every tool a skill needs and say how to check it is installed (G36).

## Compliance and risk

10. **Evidence and gaps only.** A compliance skill produces evidence, findings and gaps.
    It never declares a system compliant, authorized or ready for an authorization
    decision. A person with the authority decides.
11. **Cite real IDs.** Every control, criterion or standard ID a skill cites exists in the
    source document. Never invent one. When unsure, leave the ID out and say why.
12. **Fetch fast-moving facts at run time.** Baselines, deprecations, pinned versions and
    benchmark editions are fetched by the skill when it runs, from the named source. They
    are never frozen in the file (G41).
13. **Draft first for anything with a side effect.** A skill that posts, sends, pushes,
    merges or deploys drafts the action, shows it, and acts only on the user's explicit go.
    It sets `disable-model-invocation: true` (G12). `allowed-tools` only pre-approves and
    does not restrict (G14).

## Skills

14. **Frontmatter.** `name` is lowercase letters, digits and hyphens, 64 characters or
    fewer, with no "claude" or "anthropic" in it (G1). Prefer gerund or action names and
    avoid `helper`, `utils`, `tools` (G39). Keep one naming pattern inside a plugin.
15. **Description.** Third person, says what the skill does and when to use it, key use
    case first, with the trigger terms a user would type (G2, G6, G7). Keep `description`
    plus `when_to_use` under 1,536 characters (G4). Claude under-triggers, so list the
    situations and add "even if they do not name X" where it fits (G8). Put every
    "when to use" in the description and none in the body.
16. **Valid fields only.** Use the field names in G9 to G19 exactly. Unknown fields are
    silently ignored, so a typo does nothing. The opening `---` is line 1 (G21). Skills in
    this repo run in Claude Code, so Claude-Code-only fields are fine (G22).
17. **Size.** SKILL.md stays under 500 lines (G25). Put the most important instructions at
    the top, because only the first 5,000 tokens survive compaction (G30). Reference files
    sit one level deep from SKILL.md, are named for their content, and get a table of
    contents when they pass 100 lines (G27, G28, G29).
18. **Scripts for deterministic work.** The skill says whether Claude runs a script or reads
    it (G33). Reference bundled files through `${CLAUDE_SKILL_DIR}` (G23). Match freedom to
    fragility: exact commands for fragile steps, guidance for open ones (G32). Name one
    default tool or approach and give an alternate only for the case that needs it (G38).
    Use plan, validate, execute for batch or destructive work (G35).
19. **A rule that must hold every time belongs in a hook** in the `guardrails` plugin, since
    a skill is only advice Claude may skip (G31).
20. **One term per concept** inside a skill (G42). No time-sensitive statements such as
    "before 2026 use X" (G41).
21. **Qualify MCP tools** as `Server:tool` in skill text (G37).

## Agents

22. **Frontmatter.** `name` and `description` present, opening `---` on line 1 (G56). The
    description is short and says when to delegate ("Use proactively after..."); detail
    goes in the body (G67).
23. **Least privilege.** Set a `tools` allowlist. Reviewer-type agents are read-only
    (`Read, Grep, Glob`). Never put `Skill` in `tools`; list skills under `skills:` (G61,
    G64, G69).
24. **Model by difficulty.** Choose `model` and `effort` on purpose: `haiku` or `sonnet` for
    mechanical work, `opus` for judgment, `inherit` otherwise (G59). Set `maxTurns` as a
    cost guard.
25. **Self-contained body.** No conversation history reaches a subagent, so the body states
    its inputs, the output format and what to return (G68).
26. **Plugin agents ignore** `permissionMode`, `hooks`, `mcpServers` and `initialPrompt`
    (G70). Ship hooks in the `guardrails` plugin and MCP servers in `.mcp.json`.
27. **No CLAUDE.md at a plugin root.** It is not loaded (G87). Put standing instructions in
    a skill.

## Hooks (`guardrails`)

28. `hooks/hooks.json` has the top-level `"hooks"` wrapper (G73). Reference scripts as
    `"${CLAUDE_PLUGIN_ROOT}/hooks/<script>"`, in exec form with `args` where possible
    (G75, G76). Never write state under `${CLAUDE_PLUGIN_ROOT}`; use `${CLAUDE_PLUGIN_DATA}`.
29. **Fail closed.** A blocking hook exits 2 with the reason on stderr (G81). Any other
    non-zero exit lets the action proceed, and a timeout does not block, so set
    `onFailure: "block"` on hooks that guard secrets or destructive commands (G83).
30. Plugin MCP tool names for matchers are `mcp__plugin_<plugin>_<server>__<tool>` (G79).
31. Test each hook by feeding its script the JSON a tool call would send on stdin (G80) and
    asserting the exit code and message.

## Scripts and tests

32. **Python 3.11+ standard library only, or POSIX sh.** No third-party runtime
    dependencies. Scripts are executable (`chmod +x`), start with a shebang, and fail with
    an explicit message that names the file or input and the fix (G34). Justify any
    constant.
33. **Tests live in `tests/<plugin>/`** and run under `uv run pytest tests/<plugin>`. Every
    script has tests, including the failure paths. Tests need no network and no
    credentials.
34. **Style gates.** `uv run ruff check` and `uv run ruff format --check` pass.

## Evals

35. **At least three `claude plugin eval` cases per skill** under `plugins/<plugin>/evals/`.
    At least one is a should-trigger case with a `tool_used` grader on `Skill`, and at
    least one is a near-miss that should not trigger it (`min: 0`, `max: 0`, `arm: both`)
    (G47, G49, G120, G121). Each agent gets at least one delegation case.
36. **Layout.** `evals/<skill>-<case>/prompt.md` with the prompt phrased as a user would
    type it (without naming the skill), plus `evals/<skill>-<case>/graders/<name>.md`.
    Prefer deterministic graders (`regex`, `tool_used`, `file_exists`); write `llm` rubrics
    as concrete PASS and FAIL conditions. The trigger grader:

    ```markdown
    ---
    type: tool_used
    tool: Skill
    input_match: '"skill"\s*:\s*"(?:[\w-]+:)?your-skill-name"'
    ---
    ```

37. **Writing cases is required. Running the full suite is not**, because it spends the
    subscription allowance. Run one case with one run to prove the case loads:
    `claude plugin eval plugins/<plugin>/evals/<case> --max-cost-usd 1`. Run the suite
    before a release, never in a loop. `evals/results/` is gitignored.

## Versioning and the validate gate

38. **`version` is omitted everywhere** in `plugin.json` and `marketplace.json`, so an update
    follows the git commit (G94). Never add it in only one place.
39. **`--strict` cannot pass while `version` is omitted**, because it turns the validator's
    "No version specified" warning into a failure. The gate is
    `uv run python scripts/validate.py [plugin ...]`: it runs `claude plugin validate` and
    fails on any error and on any warning except that one.
40. **Names.** No plugin name starts with `claude-` or `anthropic-` (G91). The marketplace
    entry `name` equals the plugin's `plugin.json` `name` (G101). Plugin skills appear as
    `/<plugin>:<skill>` and agents as `<plugin>:<name>` (G110).

## Local gates before any merge

41. Run all three from the repo root; each prints its result and exits non-zero on failure:

    ```sh
    uv run python scripts/validate.py <plugin>   # claude plugin validate, version warning allowed
    uv run pytest tests/<plugin>
    uv run ruff check
    ```

    The integrator runs `scripts/validate.py` with no arguments (marketplace and every
    plugin) and plain `uv run pytest` before the final merge.

## Writing style

42. Plain, direct sentences in every file: skills, agents, docs, comments, test names.
43. Never use "X, not Y" contrastive constructions ("measured, not guessed", "a signal, not
    noise"). Say what the thing is and stop.
44. No counts of things that grow (skills, rules, checks) and no invented numbers.
45. Conventional Commits for commit messages (`feat(core): ...`, `fix(security): ...`).
