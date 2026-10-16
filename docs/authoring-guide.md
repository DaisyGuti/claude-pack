# Anthropic authoring guide: skills, subagents, hooks, plugins (as of 2026-10-16)

All claims below were fetched live on 2026-10-16. Where a rule says "(CC vX)" it names the minimum Claude Code version the docs state.
Base URLs (the `.md` suffix returns raw markdown):
- CC = https://code.claude.com/docs/en/
- API = https://platform.claude.com/docs/en/agents-and-tools/agent-skills/

Fetch notes: the docs-map entry `plugins/plugin-evals` 404s; the live page is `CC plugin-evals`. The agentskills.io spec was not fetched, so its own limits are UNVERIFIED beyond what the Claude pages restate.

---

## 1. Skill authoring rules

### 1a. Frontmatter and limits
1. `name` (platform rule): max 64 chars, lowercase letters/digits/hyphens only, no XML tags, must not contain the reserved words "anthropic" or "claude". Source: API best-practices + overview. https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
2. `description` (platform rule): non-empty, max 1,024 chars, no XML tags; must say BOTH what the skill does AND when to use it. Source: same page.
3. Claude Code is more lenient than the platform: every frontmatter field is optional, only `description` is "recommended"; if omitted, the first non-empty markdown line is used. Claude Code documents no name length cap. Source: CC skills#frontmatter-reference. https://code.claude.com/docs/en/skills
4. In Claude Code the listing text is `description` + `when_to_use` combined, truncated at 1,536 chars (configurable via `skillListingMaxDescChars`). Put the key use case first. Source: CC skills (frontmatter table; "Skill descriptions are cut short").
5. The whole skill listing has a budget of 1% of the context window (`skillListingBudgetFraction`, or `SLASH_COMMAND_TOOL_CHAR_BUDGET`). On overflow, descriptions of the least-invoked skills are dropped first. `/doctor` estimates listing cost. Source: CC skills#skill-descriptions-are-cut-short.
6. Write the description in THIRD PERSON ("Processes Excel files..."), never "I can help you" or "You can use this". It is injected into the system prompt and mixed point-of-view hurts discovery. Source: API best-practices.
7. Be specific and include trigger terms/contexts. Avoid "Helps with documents", "Processes data". Claude picks among possibly 100+ skills from the description alone. Source: API best-practices.
8. skill-creator's addition: Claude tends to UNDERtrigger, so make descriptions a little "pushy" (list the situations, include "even if they don't explicitly ask for X"). All "when to use" info belongs in the description, not the body. Source: https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md

### 1b. Every optional frontmatter field Claude Code documents for skills
Source for the whole table: https://code.claude.com/docs/en/skills#frontmatter-reference (field names must match exactly; unknown fields are silently ignored).
9. `name` (command name; defaults to directory name; in a plugin it replaces only the last segment).
10. `description`, `when_to_use` (appended to description, shares the 1,536 cap).
11. `argument-hint` (autocomplete hint, e.g. `[issue-number]`), `arguments` (named positional args, space string or YAML list, used as `$name`).
12. `disable-model-invocation: true` = only the user can invoke; also blocks preload into subagents and use by scheduled tasks. Use for side-effect workflows (deploy, commit, send).
13. `user-invocable: false` = hidden from `/` menu, only Claude invokes (background knowledge).
14. `allowed-tools` (space/comma string or YAML list; supports `Bash(git *)`). It PRE-APPROVES for the invoking turn only (clears on next user message). It does NOT restrict the tool pool and does not override deny rules. Ignored in project/personal skills when `allowManagedPermissionRulesOnly` is set.
15. `disallowed-tools` removes tools from the pool while the skill is active (clears next message).
16. `model` (same values as `/model`, or `inherit`; applies for the turn only), `effort` (`low|medium|high|xhigh|max`).
17. `context: fork` runs the skill in a forked subagent that does NOT see conversation history (skill body must stand alone); `agent` picks the subagent type (`Explore`, `Plan`, `general-purpose`, or a custom `.claude/agents/` name); `background: false` waits for the result (default true; CC v2.1.218).
18. `hooks` (registered when the skill is invoked, live for the rest of the session; `once: true` is honored only in skill frontmatter). See https://code.claude.com/docs/en/hooks#hooks-in-skills-and-agents
19. `paths` (glob list; skill auto-loads only when working on matching files), `shell` (`bash` default or `powershell` for `!` injection).
20. Spec fields Claude Code accepts but does not act on: `license`, `compatibility` (string, max 500 chars), `metadata` (free-form map).
21. Booleans accept true/false/yes/no/on/off/1/0 in any case (v2.1.218+). The opening `---` MUST be line 1 or the whole file is treated as body. Unparseable YAML loads the skill with NO metadata (so `/name` works but Claude cannot match the description). Run `claude --debug` or `claude plugin validate .claude/skills` (v2.1.233) to find it.
22. Portability: claude.ai uploads, the Skills API and `package_skill.py` accept ONLY `name, description, license, compatibility, metadata, allowed-tools`; any other key (e.g. `argument-hint`) is a hard "Unexpected key(s)" error. Claude Code-only fields: `when_to_use, argument-hint, arguments, disable-model-invocation, user-invocable, disallowed-tools, model, effort, context, agent, background, hooks, paths, shell`. Source: CC skills#using-skill-frontmatter-outside-claude-code.
23. String substitutions in body: `$ARGUMENTS`, `$ARGUMENTS[N]`/`$N` (0-based), `$name`, `${CLAUDE_SESSION_ID}`, `${CLAUDE_EFFORT}`, `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PROJECT_DIR}`, and (plugin skills only) `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`. Escape a literal `$1` as `\$1`. Using `${CLAUDE_SKILL_DIR}` in both the body and `allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/x.sh *)` lets a bundled script run without a prompt.
24. Dynamic context: `` !`cmd` `` or a ```` ```! ```` block runs BEFORE Claude sees the skill; non-zero exit aborts the invocation (append `|| true`); 2-minute timeout; checked against permission rules; `disableSkillShellExecution` turns it off by policy. Does not work in claude.ai/API.

### 1c. Size, progressive disclosure, nesting
25. Keep SKILL.md body under 500 lines; split into separate files before that. Sources: API best-practices; CC skills ("Key recommendations"); skill-creator.
26. Three levels: metadata always loaded (~100 tokens/skill) -> SKILL.md body on trigger (<5k tokens) -> bundled files on demand (zero cost until read; scripts cost only their output). Source: API overview.
27. Keep references ONE level deep from SKILL.md. Claude may `head -100` a file reached through another reference and see partial content. Source: API best-practices#avoid-deeply-nested-references.
28. Reference files longer than 100 lines (API) / 300 lines (skill-creator) need a table of contents at the top. (The two sources disagree on the threshold; use 100.)
29. Use patterns: high-level guide + reference files; per-domain files (`reference/finance.md`); conditional details. Name files descriptively (`form_validation_rules.md`, not `doc2.md`). Forward slashes only in paths.
30. After auto-compaction only the first ~5,000 tokens of each invoked skill are re-attached (25,000-token total budget, newest first), so put the most important instructions at the TOP of SKILL.md. Skill content is NOT re-read on later turns. Source: CC skills#skill-content-lifecycle.
31. Rules that must hold EVERY time belong in a hook, not a skill. Source: CC skills#claude-stops-following-a-skill; CC plugins/components#skills.

### 1d. Scripts vs instructions, degrees of freedom
32. Match freedom to fragility: high freedom (text steps) when many approaches are valid; medium (parameterized scripts/templates) when a preferred pattern exists; low (exact script, "do not modify flags") for fragile operations such as migrations. Source: API best-practices#set-appropriate-degrees-of-freedom.
33. Ship scripts for deterministic work (validation, parsing, form fill): more reliable, cheaper than regenerating code, consistent. State whether Claude should EXECUTE ("Run x.py") or READ ("See x.py for the algorithm"). Source: API best-practices#provide-utility-scripts.
34. Scripts must handle errors themselves ("solve, don't defer") and justify constants (no "voodoo constants"). Make validators verbose with specific, actionable messages. Source: API best-practices.
35. Use plan-validate-execute (write a `changes.json`, validate with a script, then apply) for batch, destructive or high-stakes work. Use validate -> fix -> repeat feedback loops.
36. List required packages explicitly and don't assume tools are installed. Claude API has no network and no runtime installs; claude.ai varies; Claude Code has full network but installing packages globally is discouraged. Source: API overview#runtime-environment-constraints.
37. Qualify MCP tools as `ServerName:tool_name` in skill text to avoid "tool not found". Source: API best-practices#mcp-tool-references.
38. Provide a default, not a menu ("Use pdfplumber; for scanned PDFs use pdf2image+pytesseract"). Provide templates (strict or flexible) and input/output example pairs when style matters.

### 1e. Naming, time-sensitivity, terminology
39. Prefer gerund names (`processing-pdfs`) or noun/action forms; avoid `helper`, `utils`, `tools`, `documents`, `data`, `files`, and reserved words. Keep one pattern across a collection. Source: API best-practices#naming-conventions.
40. Reserved in Claude Code: `anthropic-skills` and `anthropic-skills:*` (synced claude.ai skills) and `synced`. Names may not contain zero-width/control/bidi/private-use chars, `<`, `>`, or non-single spaces. Source: CC skills#how-a-skill-gets-its-command-name.
41. No time-sensitive statements ("before August 2025 use X"). Put legacy material in a collapsed "Old patterns" section. Source: API best-practices#avoid-time-sensitive-information.
42. Use one term per concept throughout (always "field", never mixed with "box"/"element").
43. Write imperative instructions and explain the WHY; avoid shouting MUST/ALWAYS in caps where reasoning works (skill-creator). Explain what Claude does not already know; "the context window is a public good" (API best-practices#concise-is-key).

### 1f. Testing and evaluation
44. Build evaluations BEFORE writing extensive docs: run Claude without the skill, record failures, write 3 scenarios, baseline, write minimal instructions, iterate. Checklist requires at least THREE evaluations. Source: API best-practices#evaluation-and-iteration. (Docs note: no built-in runner for the API-side eval JSON.)
45. Test with every model you will use: Haiku (enough guidance?), Sonnet (clear/efficient?), Opus (not over-explaining?). Same page.
46. Iterate with "Claude A" (author) and "Claude B" (fresh session using the skill); watch navigation (unexpected read order, missed links, files never read). Same page.
47. Baseline comparison in Claude Code: run realistic prompts in a FRESH session with the skill on and off (`skillOverrides: {"name": "off"}` for personal/project skills; `claude plugin eval` for plugin skills). Source: CC skills#evaluate-and-iterate-on-a-skill.
48. skill-creator plugin (`/plugin install skill-creator@claude-plugins-official`): stores `evals/evals.json` in the skill dir, one subagent per case, `grading.json`, `benchmark.json` (with vs without), blind A/B between versions, and description tuning. Its trigger-eval recipe: 20 queries (8-10 should-trigger, 8-10 near-miss should-not-trigger), 60/40 train/test split, 3 runs per query, up to 5 optimization iterations. Its `evals.json` format is NOT interchangeable with `claude plugin eval`. Source: CC skills#run-evals-with-skill-creator; skill-creator SKILL.md.
49. Trigger testing for a plugin skill: eval grader `type: tool_used`, `tool: Skill`, `input_match: '"skill"\s*:\s*"(?:[\w-]+:)?your-skill-name"'`. Source: CC plugin-evals.
50. Cost/usage audit: `/skill-doctor` (CC v2.1.252+, needs feature-flag fetching). See section 5.

### 1g. Where skills live; commands vs skills
51. Precedence on same name: enterprise > personal (`~/.claude/skills/`) > project (`.claude/skills/`). Plugin skills are namespaced `/plugin:skill` so they never collide. Nested `.claude/skills/` in subdirs load when files there are touched. A skill beats a same-named `.claude/commands/` file. Source: CC skills#resolve-skills-that-share-a-name.
52. Custom commands ARE merged into skills: `.claude/commands/deploy.md` and `.claude/skills/deploy/SKILL.md` both create `/deploy`; old command files keep working; commands take the same frontmatter except `name` and `paths`; skills add a directory for supporting files. Plugin docs: "skills supersede commands for new work". Sources: CC skills (intro note); CC plugins/components#commands.
53. Cloud/Cowork/routine sessions do not read `~/.claude/skills/`; enable the skill on the claude.ai account or commit it to the repo's `.claude/skills/`. Source: CC skills#skills-in-cowork-and-cloud-sessions.
54. Security: install skills only from trusted sources; audit all bundled files, especially anything fetching external URLs. Source: API overview#security-considerations.

---

## 2. Subagent authoring rules
Source for all of section 2 unless noted: https://code.claude.com/docs/en/sub-agents (frontmatter table at #supported-frontmatter-fields).

55. File = Markdown with YAML frontmatter; body becomes the system prompt (it REPLACES the default Claude Code system prompt). Location precedence: managed > `--agents` JSON > `.claude/agents/` > `~/.claude/agents/` > plugin `agents/`.
56. Required: `name` (<=256 chars, no `:`, no leading `-`; filename need not match), `description`. A file with no `name` is skipped silently; bad `name`/missing description/bad YAML is skipped with a debug-log entry. Opening `---` must be line 1.
57. camelCase field names, exact match; unknown fields are ignored (find typos with `claude --debug`, v2.1.296).
58. Documented optional fields: `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `autoCompactWindow` (100000-1000000), `skills`, `mcpServers`, `hooks`, `memory`, `background`, `omitClaudeMd`, `effort`, `isolation`, `color`, `initialPrompt`, `experimental` (`cacheTtl: 5m|1h`).
59. `model`: `sonnet`, `opus`, `haiku`, `fable`, a full ID (e.g. `claude-opus-5-5`), or `inherit`. Resolution order: per-invocation param -> frontmatter -> `CLAUDE_CODE_SUBAGENT_MODEL` -> parent model. A family alias equal to the parent's family resolves to the parent's exact model. `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` makes the env var win over everything (and ignores the frontmatter `model`).
60. `permissionMode`: `default` (alias `manual`), `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions`, `plan`. If the parent runs `bypassPermissions`/`acceptEdits`/`auto`, the parent's mode wins and the field is ignored.
61. `tools` is an allowlist (comma string or YAML list; omit = inherit all); `disallowedTools` is a denylist applied first, then `tools` resolves against what remains. MCP forms: `mcp__<server>`, `mcp__<server>__*`, `mcp__*` (denylist only). A `tools` list that resolves to nothing fails to launch. Do not put `Skill` in `tools`; use `skills:`.
62. `Agent(worker, reviewer)` in `tools` restricts which subagents a MAIN-THREAD agent (run via `--agent`) may spawn; it is ignored inside normal subagent definitions. Subagents never get `AskUserQuestion`, `EnterPlanMode`, `Workflow`, `ScheduleWakeup`, etc. Default nesting depth is 3 (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`); default 20 concurrent (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`).
63. Background subagents (the default when Claude spawns them) get a reduced built-in tool set (Read, Grep, Glob, LSP, Bash, Edit, Write, WebFetch, WebSearch, TodoWrite, Skill, ...) but keep all MCP tools.
64. `skills:` injects the FULL content of each listed skill (up to 32) at startup. Subagents do not inherit the parent's skills or conversation otherwise. Skills with `disable-model-invocation: true` cannot be preloaded.
65. `memory: user|project|local` gives a persistent `MEMORY.md` dir (`~/.claude/agent-memory/<name>/`, `.claude/agent-memory/<name>/`, `.claude/agent-memory-local/<name>/`); first 200 lines / 25KB are injected; Read/Write/Edit are auto-enabled.
66. `isolation: worktree` runs the agent in a throwaway git worktree, auto-removed if unchanged. `color`: red, blue, green, yellow, purple, orange, pink, cyan.
67. Delegation: Claude delegates from the `description` plus context. Phrase it with "Use proactively after..." / "Use when...". Keep descriptions BRIEF (combined subagent descriptions over 15,000 tokens trigger a startup warning). Put detail in the body, not the description. @-mention (`@"name (agent)"` or `@agent-name`) forces a specific agent.
68. Subagents start WITHOUT the conversation history: put everything the agent needs in the delegation prompt and system prompt. They do receive the CLAUDE.md hierarchy (skip with `omitClaudeMd: true`, v2.1.271) and git status (Explore/Plan skip both).
69. Restrict tools to the minimum (read-only reviewer: `tools: Read, Grep, Glob`). For read-only DB-style guards, pair `tools: Bash` with a `PreToolUse` hook script that exits 2 on disallowed commands (documented example).
70. PLUGIN agents silently IGNORE `permissionMode`, `hooks`, `mcpServers` and `initialPrompt`. Supported in plugin agents: `name, description, model, effort, maxTurns, autoCompactWindow, tools, disallowedTools, skills, memory, background, omitClaudeMd, isolation, color, experimental.cacheTtl`. Ship hooks via `hooks/hooks.json` and MCP via `.mcp.json` instead. Source: https://code.claude.com/docs/en/plugins/components#agents
71. Plugin agents are named `<plugin>:<name>`; subfolders add segments (`agents/review/security.md` -> `my-plugin:review:security`). Frontmatter that fails to parse still loads the agent, named after the file with description "Agent from <plugin> plugin" (run `claude plugin validate`).
72. Measure delegation reliability for plugin agents with `claude plugin eval` (prompt with and without the plugin).

---

## 3. Hooks in plugins
Sources: https://code.claude.com/docs/en/hooks ; https://code.claude.com/docs/en/plugins/components#hooks ; https://code.claude.com/docs/en/plugins/manifest-reference

73. A plugin ships hooks in `hooks/hooks.json` at the plugin root with a top-level `"hooks"` wrapper key: `{"hooks": {"PostToolUse": [{"matcher": "Write|Edit", "hooks": [{"type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/scripts/format.sh\""}]}]}}`. Same shape as `hooks` in settings.json, so settings hooks copy over unchanged. The manifest `hooks` key can also hold a path to such a file, an inline map (NO wrapper), or an array of both; they merge with `hooks/hooks.json`. A file without the `"hooks"` wrapper fails to load.
74. Plugin hooks register when the session loads the plugin and fire on their events whether or not any skill of the plugin runs. Narrow with `matcher` and `if`.
75. Path variables: `${CLAUDE_PLUGIN_ROOT}` (install dir; CHANGES on update, never write state there), `${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/<id>/`, survives updates), `${CLAUDE_PROJECT_DIR}`. Hook processes also get `CLAUDE_PLUGIN_OPTION_<KEY>` for each `userConfig` value. These variables are NOT in the environment of Bash-tool commands Claude runs.
76. Quoting: shell form (no `args`) must wrap the variable in double quotes (`"${CLAUDE_PLUGIN_ROOT}"/x.sh`); exec form (`command` + `args` array) needs no quoting and is preferred. `${user_config.*}` is rejected in shell-form hook commands; use exec form args or the env var.
77. Event names (31+ in the live docs): SessionStart, Setup, InstructionsLoaded, UserPromptSubmit, UserPromptExpansion, MessageDisplay, PreToolUse, PermissionRequest, PostToolUse, PostToolUseFailure, PostToolBatch, PermissionDenied, Notification, SubagentStart, SubagentStop, TaskCreated, TaskCompleted, Stop, StopFailure, TeammateIdle, ConfigChange, CwdChanged, DirectoryAdded, FileChanged, WorktreeCreate, WorktreeRemove, PreCompact, PostCompact, PreModelSwitch, PostModelSwitch, SessionEnd, Elicitation, ElicitationResult.
78. Handler types: `command` (`command`, optional `args`, `shell`, `async`, `asyncRewake`, `onFailure`), `http` (`url`, `headers`, `allowedEnvVars`), `mcp_tool` (`server`, `tool`, `input`; plugin servers are `plugin:<plugin>:<server>`), `prompt` (`prompt`, `model`), `agent`. Common: `if` (permission-rule syntax such as `Bash(rm *)`, best-effort only), `timeout` (600s command/http/mcp_tool, 30s prompt, 60s agent; 30s on UserPromptSubmit), `statusMessage`, `once` (skill frontmatter only).
79. Matcher: `*`/empty/omitted = all; letters, digits, `_`, `-`, spaces, commas, `|` = exact list; anything else = unanchored JavaScript regex. For tool events it matches tool name. Plugin MCP tool names are `mcp__plugin_<plugin>_<server>__<tool>`; a matcher on the server name alone NEVER fires.
80. Input: JSON on stdin (`session_id, transcript_path, cwd, permission_mode, hook_event_name, tool_name, tool_input`, plus `agent_id/agent_type` in subagents).
81. BLOCKING CONTRACT, exit codes: `0` = success (stdout parsed as JSON only if the whole output is ONE JSON object); `2` = blocking error on blocking events (PreToolUse blocks the tool call, UserPromptSubmit rejects the prompt, Stop/SubagentStop make Claude continue, etc.), message = stderr (or the JSON reason); exit 2 beats any JSON, even `permissionDecision: "allow"`; any other code = non-blocking error and the action PROCEEDS (unless `onFailure: "block"`, v2.1.295). Exit 2 is ignored on PermissionRequest (use the `decision` object) and cannot block PostToolUse (tool already ran; stderr is shown to Claude). Choose one approach per hook: exit codes alone OR exit 0 + JSON.
82. BLOCKING CONTRACT, JSON (exit 0): `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}`. Values `allow` (skips the prompt but deny/ask rules still apply), `deny`, `ask`, `defer`. Also `updatedInput` (rewrite tool args), `additionalContext`. Top-level `{"decision":"block","reason":"..."}` is used by UserPromptSubmit, PostToolUse, Stop, etc. Universal fields: `continue:false` + `stopReason`, `systemMessage`. PermissionRequest uses `hookSpecificOutput.decision.behavior: allow|deny`.
83. A timeout on a PreToolUse command hook does NOT block (permission flow continues); set `onFailure: "block"` for fail-closed. `if` is best-effort; use permission rules for hard enforcement.
84. Two plugins sharing a manifest name: only one registers its `hooks/hooks.json`; the other's hooks are silently left out (shown in `/plugin` Errors tab).
85. Hooks from all scopes merge and run in parallel; identical handlers run once. `disableAllHooks` cannot disable managed hooks.

---

## 4. Plugins and marketplaces

### 4a. Layout
Sources: https://code.claude.com/docs/en/plugins/manifest-reference#standard-layout ; https://code.claude.com/docs/en/plugins/create
86. Only `plugin.json` lives inside `.claude-plugin/`. Everything else is at the plugin ROOT: `skills/<name>/SKILL.md`, `commands/*.md` (legacy), `agents/*.md`, `hooks/hooks.json`, `.mcp.json`, `.lsp.json`, `output-styles/`, `workflows/`, `themes/`, `monitors/monitors.json`, `bin/` (put on Bash PATH; claude.ai/Cowork reject a plugin with top-level `bin/`), `settings.json` (only `agent` and `subagentStatusLine` take effect), `scripts/` (by convention). Components placed inside `.claude-plugin/` do not load.
87. A `CLAUDE.md` at the plugin root is NOT loaded (validate warns). Put instructions in a skill.
88. The manifest is optional; without it the name comes from the marketplace entry or directory name. Write one for metadata, `userConfig`, or non-default paths.
89. Skills dirs scan: `skills/` default plus any `skills` manifest paths (ADDS). `commands`, `agents`, `outputStyles`, `workflows`, `experimental.themes`, `experimental.monitors` REPLACE their default dir (validate warns "Default <folder>/ folder is ignored"). `hooks`, `mcpServers`, `lspServers` MERGE. All manifest paths must start with `./`, stay inside the plugin root and exist.
90. A plugin with a root `SKILL.md`, no `skills/` and no `skills` key loads as one skill: set `name` in its frontmatter.

### 4b. plugin.json
Source: https://code.claude.com/docs/en/plugins/manifest-reference
91. Required: `name` only (kebab-case; no spaces, `@`, `:`, path separators). Validate ERRORS on names starting `claude-`, `anthropic-`, `anthropics-`, `cc-plugin-`, equal to `claude`/`anthropic`/`claude-code`, or pairing `official` with claude/anthropic; WARNS on those words as a whole word elsewhere.
92. Optional: `$schema`, `displayName`, `version`, `description`, `author` {`name` required, `email`, `url`}, `homepage` (must parse as URL or plugin fails to load), `repository`, `license`, `keywords`, `metadata`, `defaultEnabled`, `dependencies` (names, `name@marketplace`, or `{name, marketplace, version}`), `settings`, `userConfig` (typed prompts: string/number/boolean/directory/file; `sensitive`, `options`, `required`, `default`), `channels`, `skills`, `commands`, `agents`, `hooks`, `mcpServers`, `lspServers`, `outputStyles`, `workflows`, `types`, `experimental` {`themes`, `monitors`, `evals`}, plus directory-listing fields (`icon`, `documentationUrl`, `supportUrl`, `privacyPolicyUrl`, `termsOfServiceUrl`).
93. Unknown top-level keys are stripped (warning); unknown keys inside `userConfig`, `channels`, `lspServers`, `monitors` entries are ERRORS and the plugin won't load.
94. `version`: a pinned string keeps users on the cached copy until you change it. Either bump it every release, or omit it everywhere (then git sources use the commit SHA). Do not set it in both plugin.json and the marketplace entry (plugin.json wins, validate warns). Source: https://code.claude.com/docs/en/plugins/loading#versions-and-updates

### 4c. marketplace.json
Source: https://code.claude.com/docs/en/plugins/marketplace-reference
95. Lives at `.claude-plugin/marketplace.json`; relative plugin sources resolve from the repo/marketplace ROOT, not from `.claude-plugin/`.
96. Required top level: `name`, `owner` ({`name` required, `email`, `url`}), `plugins`. Optional: `$schema`, `description`, `version`, `metadata.{description,version,pluginRoot}`, `forceRemoveDeletedPlugins`, `allowCrossMarketplaceDependenciesOn`, `renames`. Marketplace `name`: letters/digits/`.`/`_`/`-`, starts alphanumeric. Reserved: official Anthropic names (`claude-plugins-official`, `anthropic-*`, `agent-skills`, ...), impersonating names, `inline`, `builtin`, `skills-dir`, `synced`, `npm|pip|uv|cargo|github|gh`, anything starting `claudeai-`.
97. Plugin entry: required `name`, `source`; optional `description, version, category, tags, strict (default true), relevance, dependencies, defaultEnabled, displayName, metadata, headers, headersHelper`, plus any plugin.json field (`commands, agents, skills, hooks, outputStyles, themes, mcpServers, ...`). If no plugin.json exists the entry IS the manifest.
98. Plugin `source` types: relative path string (`./plugins/x`, must start `./`, no `..`), `github` {repo, ref, sha}, `url` {url, ref, sha} (any git URL; no owner/repo shorthand), `git-subdir` {url, path, ref, sha}, `npm` {package, version, registry}, `archive` {url (https zip), sha256}, `command` {command, timeout, mode}. `sha` = full 40-char commit.
99. Strict mode: `strict:true` (default) = plugin.json is the authority and entry component fields are appended (hooks: entry matchers replace the manifest's per event). `strict:false` + plugin.json + entry component fields = load error "conflicting manifests".
100. Entry-level `hooks` must be an inline object; a file path/array passes validate but never runs. A `url`-hosted marketplace (bare marketplace.json) cannot use relative-path entries.
101. Keep the entry `name` equal to the plugin.json `name`. Never rename a published plugin; use `renames` to migrate users (append-only, chains followed from the oldest name; `null` = removed) and `displayName` for a new label.

### 4d. Adding a marketplace and private GitHub repos on a new machine
Sources: https://code.claude.com/docs/en/plugins/host-marketplace#grant-access-to-a-private-marketplace ; https://code.claude.com/docs/en/plugins/install#add-a-private-marketplace
102. Claude Code has NO git token of its own and marketplace.json has no credential field. It runs plain `git` with prompts disabled, using whatever credentials the machine holds.
103. GitHub `owner/repo` shorthand: probes `ssh -T git@github.com`; uses SSH if it works, else HTTPS. `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1` skips the probe and forces HTTPS. SSH needs a key with no passphrase prompt (loaded in ssh-agent) and the host in `known_hosts`. HTTPS needs a credential already stored in a helper: `gh auth login` then `gh auth setup-git` (or macOS Keychain / Git Credential Manager / git-credential-store).
104. A bare `GITHUB_TOKEN`/`GH_TOKEN` in the environment does NOT by itself authenticate the background check; it only works through a credential helper that reads it (the `gh` helper does). In GitHub Actions/CI export `GH_TOKEN` then run `gh auth setup-git`.
105. Background auto-update of a private marketplace uses the same helpers and never prompts. If the check can't authenticate, Claude Code RE-CLONES and replaces the checkout; if that fails the old checkout stays. `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1` skips the re-clone on failure and keeps the last good copy.
106. Auto-update is OFF by default for every non-Anthropic marketplace. Turn on per marketplace in `/plugin` > Marketplaces > Enable auto-update, or `"autoUpdate": true` on its `extraKnownMarketplaces` entry. It fires up to ~10 min after your first message. `DISABLE_AUTOUPDATER`, `DISABLE_UPDATES` or `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` turn it off (`FORCE_AUTOUPDATE_PLUGINS=1` overrides). Source: https://code.claude.com/docs/en/plugins/loading#when-auto-update-runs
107. Commands: `claude plugin marketplace add <source> [--scope user|project|local] [--sparse ...]` (default scope `user`); in a session `/plugin marketplace add <source>`. Sources: `owner/repo[#ref|@ref]`, `git@host:path.git`, full `https://...git[#ref]` URL, hosted `https://.../marketplace.json`, `./dir`, `./file.json`. Also `claude plugin marketplace list|update <name>|remove <name>` (remove UNINSTALLS its plugins). One-shot: `claude plugin install <plugin> --marketplace owner/repo` (v2.1.292) or `/plugin install <plugin> --marketplace owner/repo` (v2.1.275). Source: https://code.claude.com/docs/en/plugins/cli-reference
108. GitLab / Bitbucket / GHES / other git hosts WORK: give the FULL URL, e.g. `/plugin marketplace add https://gitlab.example.com/team/plugins.git` (or `git@host:path.git`); a bare `gitlab.example.com/x/y` is read as GitHub shorthand and rejected. `gitlab.com` nested subgroups work. In settings use `{"source":"git","url":"https://git.example.com/security/plugins.git"}`. Credentials: same git credential helper/SSH rules; there is no GitLab-specific token variable. Hosts without a `.git` URL suffix (e.g. CodeCommit) must be declared as a `git` source in `extraKnownMarketplaces`. Source: https://code.claude.com/docs/en/settings-reference#extraknownmarketplaces
109. Install / update / uninstall: `claude plugin install <plugin>@<marketplace> [--scope user|project|local]`, `claude plugin update <plugin>@<marketplace>`, `claude plugin uninstall <plugin>@<marketplace> [--scope ...]`, `claude plugin enable|disable <plugin>@<marketplace>`, `claude plugin list`, `claude plugin details <name>`, `claude plugin prune`, `claude plugin tag` (creates `<name>--v<version>`). In session: `/plugin`, `/plugin install`, `/reload-plugins` (`--force` if it would invalidate the prompt cache). `claude plugin update` says "already at the latest version" when the computed version is unchanged. There is no update-everything command; per marketplace use `/plugin` > Marketplaces > Update marketplace.
110. Namespacing: plugin skills are `/<plugin>:<skill>` (frontmatter `name` replaces only the last segment; a name already starting with `<plugin>:` isn't double-prefixed from v2.1.246); commands `/<plugin>:<file>` (subdirs add `:segments`); agents `<plugin>:<name>`, explicit call `@agent-<plugin>:<name>`. Plugin ids are `name@marketplace`. Same-name plugins from different origins follow a fixed precedence (managed > `--plugin-dir` > installed > skills-dir > synced). Source: https://code.claude.com/docs/en/plugins/loading#name-conflicts

### 4e. Team pre-registration in a repo's `.claude/settings.json`
Sources: https://code.claude.com/docs/en/settings-reference#extraknownmarketplaces ; https://code.claude.com/docs/en/plugins/org#require-plugins-per-repository
111. `extraKnownMarketplaces` is an OBJECT keyed by marketplace name -> `{ "source": {...}, "autoUpdate": bool }` (NOT an array of URLs). Source types: `github` {repo, ref, path}, `git` {url, ref, path}, `url` {url, headers, headersHelper}, `file` {path}, `directory` {path}, `settings` {name, plugins}. The key must equal the marketplace's own `name`. `additionalMarketplaces` is an alias (v2.1.232).
   ```json
   {
     "extraKnownMarketplaces": {
       "acme-tools": { "source": { "source": "github", "repo": "acme-corp/claude-plugins" }, "autoUpdate": true }
     },
     "enabledPlugins": { "code-formatter@acme-tools": true }
   }
   ```
112. `enabledPlugins` is an object `"plugin@marketplace": true|false`. Project settings override user settings; to opt out personally of a project-enabled plugin use `.claude/settings.local.json`.
113. TRUST GATE: repo-level `extraKnownMarketplaces` entries apply only after the user accepts the workspace trust dialog for that folder; in an untrusted folder (and in `-p` runs there) they are ignored WITHOUT a message. For `-p`/CI the folder must have been trusted interactively (or `hasTrustDialogAccepted` set in `~/.claude.json`).
114. Registering is not installing: a plugin whose marketplace entry is a RELATIVE path loads from the marketplace copy once the marketplace registers. A plugin with an EXTERNAL source (github/npm/url) is NOT installed by the settings alone: each contributor sees `Plugin "<name>" is enabled in project settings but isn't installed` until they run `claude plugin install <name>@<marketplace> --scope project`. Cloud sessions load none of the repo's plugins.
115. Shortcut: `claude plugin marketplace add your-org/repo --scope project` writes the settings entry for you; commit the file. For CI set `CLAUDE_CODE_SYNC_PLUGIN_INSTALL=1` so a `-p` run waits for background installs. Managed (fleet) settings use the same two keys plus `strictKnownMarketplaces` (allowlist), `blockedMarketplaces`, `disableSideloadFlags`.

---

## 5. Validation and evals

### 5a. `claude plugin validate`
Source: https://code.claude.com/docs/en/plugins/cli-reference#plugin-validate
116. `claude plugin validate <path> [--strict] [--json]`. Path may be a marketplace root, plugin dir, manifest file, or a `skills`/`agents`/`commands`/`.claude` directory (component-only validation, v2.1.233). With both marketplace.json and plugin.json present it validates both (v2.1.289). Exit codes: 0 pass (or pass with warnings), 1 failure (warnings too under `--strict`), 2 validator crashed. `--json` returns `{success, strict, target, manifest, contents[]}` (v2.1.259).
117. It checks manifest schema, component paths (exist, `./`, contained), frontmatter of skills/agents/commands, MCP server entries (v2.1.281), reserved names, and plugin.json vs marketplace-entry version mismatch. It does NOT read a plugin-root SKILL.md, does not open plugin files from a marketplace run (validate each plugin dir), does not follow symlinks, and cannot catch fetch errors or file-path `hooks` in a marketplace entry. Use `--strict` in CI (drop it only if you deliberately omit `version`).
118. Structure vs behavior: `validate` checks files; `eval` tests behavior; `/skill-doctor` reports usage and context cost. It is not a linter.

### 5b. `claude plugin eval`
Sources: https://code.claude.com/docs/en/plugin-evals ; https://code.claude.com/docs/en/plugins/cli-reference#plugin-eval (needs CC v2.1.269, git 2.31+ if git is present)
119. `claude plugin eval init [name] [--bare] [-i] [--eval-dir dir]` scaffolds a suite (interview in a terminal; `--bare <name>` writes a blank case). `claude plugin eval [target] [options]`: target = plugin dir, one `prompt.md`/`case.yaml`, installed `name[@marketplace]`, or `name@skills-dir`. Put target BEFORE `--tag`, `--allow-tools`, `--json`.
120. Layout: `evals/<case>/prompt.md` (frontmatter: `name, description, tags, plugins, runs (default 3, 1-50), expected_outcome, model, max_turns (10, <=200), timeout_seconds (300, <=3600), allowed_tools, append_system_prompt, env (keys must match EVAL_*)`; body = the user prompt) + `evals/<case>/graders/<name>.md` (at least one grader per case; frontmatter `type`, `weight`, `arm`). Optional `case.yaml` (requires `schema_version: "1.1"` and `name`) for `context.scaffold_script` (needs `--scaffold`), `context.history_file`, `context.add_dirs`. Suite-wide mocks in `evals/mocks/<server>/<tool>.md`. Results in `evals/results/<timestamp>/` (gitignore it). Custom eval dir: `--eval-dir` or `"experimental": {"evals": "quality/evals"}` in plugin.json.
121. Grader types (no custom-code graders): `regex` (pattern, flags, match contains|not_contains|count:N, target), `tool_used` (tool, input_match, min, max; "never call" = min 0 max 0), `tool_order` (before, after), `file_exists` (path glob, exists), `llm` (criteria rubric; judge votes 2 of 3), `baseline` (baseline_file, criteria). `target`/`focus` values: `last_message` (default), `trace`, `files`, `{source: file, path}`, `mock_calls`. Prefer deterministic graders for long output; keep `llm` rubrics as concrete PASS/FAIL conditions.
122. Each run is a fresh isolated non-interactive session with only the plugin loaded, 3 runs per case by default, plus a no-plugin baseline arm; the report shows WITH, W/OUT and delta. `Skill`-fired graders are excluded from scoring in two-arm runs unless `arm: both`. Default threshold 1.0 (`--threshold`). Tools beyond read-only need `--allow-tools` (e.g. `Bash`, `mcp__plugin_<plugin>_<server>__*`). `--max-cost-usd` caps spend. `-j/--concurrency` 1-8. `--trust-plugin` is required in CI/`--json` (the trust prompt can't ask).
123. Exit codes: 0 pass, 1 failing case/load error/untrusted dir/API-error run, 2 partial (cost ceiling or rejected credential), 130 interrupted, 143 terminated. Outputs: `aggregate-result.json` (same as `--json`) and `report.html` (may publish privately to claude.ai unless `--no-publish`).
124. Run the suite before each release (publish checklist) and after trimming descriptions (to confirm triggering did not break). Source: https://code.claude.com/docs/en/plugins/publish#prepare-your-plugin-for-release
125. Availability caveat: the local embedded notes in this environment say a server-side kill switch can print "`plugin eval` is currently unavailable" (exit 1). The public pages list no such switch; treat it as environment-specific.

### 5c. `/skill-doctor`
Sources: https://code.claude.com/docs/en/skills#find-unused-skills ; https://code.claude.com/docs/en/plugins/measure
126. `/skill-doctor` (CC v2.1.252+; unavailable when feature-flag fetching is skipped; not over Remote Control) reports each skill's context cost and invocation count, flags skills in the listing that were NEVER invoked and says where to turn them off, and lists unused plugins. Interactive: opens the `/plugin` manager Stats tab; `-p`: prints text. Covers user/project/plugin skills, not bundled or enterprise ones. Start with high-cost, unused skills.
127. Also: `claude plugin details <name>` (shell) shows Always-on tokens (names + descriptions + `when_to_use` of skills/agents/commands) and per-component cost; shorten descriptions or split the plugin to lower it. `/plugin` Installed tab shows "Not used recently" (14 days and 10 sessions). `/doctor` flags unused skills/MCP/plugins.

---

## 6. What changed recently / contradicts older practice
128. Custom slash commands are merged into skills; `.claude/commands/` still works but docs say prefer `skills/` for new work (CC skills; plugins/components).
129. Description cap is no longer just 1,024: Claude Code uses a combined `description` + `when_to_use` cap of 1,536 (platform and claude.ai uploads still enforce 1,024 and the 6-field frontmatter allowlist).
130. Many new skill fields: `when_to_use`, `arguments`, `disable-model-invocation`, `user-invocable`, `disallowed-tools`, `effort`, `context/agent/background`, `hooks`, `paths`, `shell`. `allowed-tools` pre-approves, it does not restrict.
131. `skillOverrides` (`on | name-only | user-invocable-only | off`) hides/collapses skills from settings; does not apply to plugin skills. Also `disableBundledSkills`, `disableSkillShellExecution`, `skillListingMaxDescChars`, `skillListingBudgetFraction`.
132. Subagent model values now include `fable` and `inherit`; `CLAUDE_CODE_SUBAGENT_MODEL` ranks BELOW frontmatter (it ranked first before v2.1.251) unless `..._FORCE=1`. New fields: `maxTurns`, `memory`, `isolation`, `omitClaudeMd`, `effort`, `autoCompactWindow`, `initialPrompt`, `background`, `color`.
133. Plugin agents ignore `hooks`, `mcpServers`, `permissionMode` (security restriction).
134. Hooks went far beyond command hooks: `http`, `mcp_tool`, `prompt`, `agent` handlers; `if` filter; `defer` decision; `onFailure: "block"`; exec form with `args`; 30+ events.
135. Plugin names beginning `claude-`/`anthropic-` now ERROR in validate (affects names like `claude-tools`); marketplace names have a long reserved list.
136. Plugins gained `userConfig`, `dependencies` with semver ranges, `claude plugin tag` (`name--vX.Y.Z`), `bin/`, `monitors`, `experimental.evals`, `archive` and `command` plugin sources, and `renames`/`forceRemoveDeletedPlugins`.
137. `claude plugin eval` and `claude plugin eval init` are new (v2.1.269); `/skill-doctor` (v2.1.252); `claude plugin validate` now covers skills/agents frontmatter and MCP entries.
138. Skills synced from claude.ai appear as `/anthropic-skills:<name>` and plugins as `<name>@synced`; the namespace is reserved.
139. Current Anthropic guidance on skill authoring puts evaluations first ("create evaluations BEFORE writing extensive documentation"), recommends gerund names, and still asks for tests on Haiku, Sonnet and Opus (API best-practices).

---

## 7. Pre-publish checklists

### One skill
- [ ] `name`: lowercase/digits/hyphens, <=64 chars, no "anthropic"/"claude", not vague (`helper`, `utils`); consistent with sibling skills.
- [ ] `description`: third person, says what + when, trigger keywords first, whole thing (with `when_to_use`) well under 1,536 chars; add a little push if it undertriggers.
- [ ] Frontmatter parses (opening `---` on line 1); only documented field names (typos are silent). If it must also work on claude.ai/API, only the six spec fields.
- [ ] Side-effect skill? `disable-model-invocation: true`. Background-only knowledge? `user-invocable: false`. `allowed-tools` only pre-approves.
- [ ] SKILL.md under 500 lines; critical instructions at the top; detail in files linked directly from SKILL.md (one level deep); ToC on files over 100 lines.
- [ ] Degrees of freedom match fragility; deterministic work is a script with explicit error handling, constants justified, execute-vs-read stated.
- [ ] Forward-slash paths; dependencies listed; MCP tools written `Server:tool`; no time-sensitive text; one term per concept.
- [ ] Any must-always rule moved to a hook.
- [ ] At least 3 evals (with vs without skill, fresh sessions); tried on Haiku, Sonnet and Opus; trigger test with should/should-not queries; plugin skills get a `tool_used: Skill` grader.
- [ ] `claude plugin validate <skills dir>`; run `/skill-doctor` later to catch never-invoked or heavy skills.

### One agent
- [ ] `name` (<=256, no `:`) and `description` present; description short, says when to delegate ("Use proactively after..."), details in the body; frontmatter on line 1.
- [ ] Minimal `tools` allowlist (or `disallowedTools`); no `Skill` in `tools` (use `skills:`); MCP via `mcp__server` forms.
- [ ] `model` chosen deliberately (`haiku`/`sonnet` for mechanical work, `opus` for judgment, `inherit` otherwise); optional `effort`, `maxTurns` as a cost guard.
- [ ] Body is self-contained (no conversation history reaches it); states output format and what to return.
- [ ] If it will ship in a plugin: do not rely on `hooks`, `mcpServers`, `permissionMode`, `initialPrompt` (ignored); ship hooks/MCP at plugin level; expect the name `plugin:name`.
- [ ] Need isolation? `isolation: worktree`. Need memory? `memory: project`.
- [ ] `claude plugin validate`; eval delegation with `claude plugin eval` (prompt should trigger the agent; grade with `tool_used`/`llm`).

### Plugin / marketplace (bonus)
- [ ] Only `plugin.json` inside `.claude-plugin/`; components at root; `./` paths; `claude plugin validate --strict` clean.
- [ ] Permanent kebab-case name not starting `claude-`/`anthropic-`; versioning decision made (bump every release or omit everywhere); marketplace entry `name` == plugin.json `name`.
- [ ] Hooks file has the `"hooks"` wrapper; scripts executable and referenced as `"${CLAUDE_PLUGIN_ROOT}/..."`.
- [ ] Marketplace add tested from a clean machine with only git credentials (`gh auth setup-git` or ssh-agent); auto-update enabled deliberately; repo `.claude/settings.json` entry committed and trust dialog behavior understood; external-source plugins still need a one-time `claude plugin install ... --scope project`.
