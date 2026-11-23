# Engineering standards

These are the standing rules for every engineer working with this pack. They bind across
the whole engineering pass, in any repo. The repo's own CLAUDE.md wins every question of
house style; this file is about how you work.

## Contents

- Run independent work in parallel
- Run tests and gates at the repo's full parallelism
- Merge the base branch first, then run only the gates the diff touches, once
- Wait on a condition, never on a fixed sleep or a self-matching command
- Hold the industry standard of the technology you are standing in
- Follow the codebase's patterns, and use one that removes branches
- Look for a design before you write a loop or a string literal
- Parse data once into a typed model
- Say each thing once
- Keep it simple while covering the whole requirement
- Mark a deliberate shortcut
- Find where a bug lives, then fix its cause by design
- A refactor keeps behaviour
- Delete what the change leaves unused
- Keep only tests that prove needed behaviour
- Never game a quality count
- Write guidance from the rule the check applies
- Keep hashed and exported bytes stable
- Comment the hard part briefly, for a junior reading it cold
- Run a docs pass on every change
- Say what could be better; don't go build it
- Before you call it built, consider the next version up
- Review every change adversarially, in at most two rounds, before the tests run
- Land the work as a pull or merge request, and stop there
- Look at anything rendered before calling it done
- Build to five system-design disciplines
- Anything that runs records its own timing
- Nothing is created without a surface
- Every new environment variable lands in the repo's example env file
- Everything is sourced
- Treat secrets and controlled data as a hazard in every file you touch
- Give a CI setup cost controls on day one

**Run independent work in parallel.** Independent reads, searches and commands go
out together, and independent units of work go to subagents (the eng agent's
Split the work section says how). Sequence only what depends on an earlier answer,
and never guess an argument to make a call look independent. In the code you
write, run calls that do not depend on each other concurrently (`asyncio.gather`,
`Promise.all`, a task group). Do not retrofit
code you were not asked to touch.

**Run tests and gates at the repo's full parallelism.** Waiting on a gate is usually the
longest part of a pass, so work out how this repo parallelizes before the first run. Do not
assume it:

1. **Use the repo's own entry point.** Look in this order: the commands in CLAUDE.md or
   AGENTS.md, Makefile, justfile or Taskfile targets, `package.json` scripts, a test runner
   under `scripts/`, then the CI workflow's test step. A repo runner often owns things a
   bare test command lacks, such as a database or port per worker or its own temp folder.
   Bypassing it loses those and usually its parallelism too.
2. **Read how it parallelizes, then use its default.** Check the runner and test config for
   the framework's parallel switch: pytest-xdist `-n`, Playwright `workers`, Jest or Vitest
   pools, `go test -p`, Gradle `--parallel` or `maxParallelForks`, `cargo test` threads,
   `make -j` over independent targets. When the framework supports it, the repo has not
   turned it on and the tests do not share state, pass the automatic setting (`-n auto`,
   for example) and say so in the report.
3. **Never lower the worker count without a stated reason** (shared state, a fixed port, a
   memory ceiling). When you do, name the reason in the report.
4. **Run independent gates at the same time.** Lint, type checks, unit tests and the build
   usually depend on nothing but the source. Start them together (background jobs awaited
   together, or `make -jN` when they are separate targets) and sequence only what consumes
   another's output, such as codegen before type checks.
5. **Keep targeted runs isolated.** Run a subset through the same runner. When you call the
   framework directly, give it a temp folder of its own (pytest `--basetemp`, a per-run
   `TMPDIR`), because concurrent sessions sharing one temp folder can stall on cleanup.
6. **Report each gate's wall time,** so a slow gate shows up as a number rather than a
   guess.

**Merge the base branch first, then run only the gates the diff touches, once.** Gates run
on the code CI will see, so bring the base in before the first run:
`git fetch <remote> <base> && git merge <remote>/<base>`. Never rebase a branch someone may
have pulled. When the merge would overwrite uncommitted files, commit by path first. Then run,
once, on the merged tree, the gates the diff touches: the tests that cover the changed code,
the lint and type checks for the languages in the diff, and the build when it touches build
inputs. Do not run the repo's full suite locally when CI runs it; with no CI, the full gates
are the check. Never run the gates before the merge and again after it. While you iterate,
run only the test or check you are working on. Say in the report what ran and what was left
to CI. Everything in the parallelism rule above applies to the run you do make.

After each merge, rerun the repo's setup step (dependency install, codegen, its worktree setup
target) before any gate, because a stale environment gives false type errors. Run tests
through the repo's own runner, and check that every test path you name exists: a runner
given a missing path can collect nothing and still exit 0. The run-once rule holds per
merge: when you merge the base again later (a conflict fix, a review round), run the touched
tests once more on that new merged head, because CI's fast lane may not run them.

**Wait on a condition, never on a fixed sleep or a self-matching command.** A test you
write waits for the state it needs (an event seen, a value reached, fake timers for polling
code), and keeps a real timeout only as a backstop against a hang, sized well above the
normal time so it passes on a busy machine. Wait on a process by its PID, or by the
completion of the background job you started it as. A `pgrep -f "<text>"` loop matches its
own command line and never ends. Before you hand back, nothing you started is still running:
stop each dev server, watcher or background run by its PID.

**Hold the industry standard of the technology you are standing in.** Follow each
framework's documented idioms; code that fights its framework breaks on the next upgrade. The repo's own
conventions (language version, type checking, test layout, logging, where secrets
live) are the standard you are held to. Before writing new code against a
fast-moving library or API, read its current documentation. When it is
unreachable, mark the line `UNVERIFIED:` with your assumption and say so in your
report. Never present a guessed API as one you read.

**Follow the codebase's patterns, and use one that removes branches.** Before you write
anything new, find the pattern the repo already uses for the same job and follow it. Then
look for where a fitting pattern removes branches or duplication: a strategy or registry in
place of an `if` chain on a kind, table-driven dispatch in place of a `switch`, a typed
model in place of the same checks at every caller. A pattern with one call site and no
branch to remove is bloat with a good name. When you saw a fitting pattern and chose not to
use it, say which and why in the review.

**Look for a design before you write a loop or a string literal.** Before a `for` loop,
check for a better shape: a comprehension, a lookup table or registry built once, a typed
model's method, a library call, or a query that does the work in the database. Write the
loop only when none fits, and say why in one line of the review. A string that is reused,
or that names a code, status, key, path, label or setting, becomes a static constant (an
enum or a `Final`, one list per fact, at the level the whole product reads from; search for
an existing one first) or configuration when its value varies by system or environment.
Never scatter the same literal across files.

**Parse data once into a typed model.** Parse input at the boundary into a typed model (a
dataclass, a Pydantic model, a TypeScript type with a parser) and pass that model on.
Functions never hand string-keyed dicts to each other.

**Say each thing once.** The first review round includes a DRY pass over the diff and the
code it touches. Collapse duplicated logic into one owning helper, and duplicated doc facts
into the doc that owns them, with a link from the others. When an owner already exists, the
copy goes.

**Keep it simple while covering the whole requirement.** Cover everything asked and
add nothing that was not: no helper for a single call site, no abstraction for a
future that has not arrived, no config flag nobody set, no defensive branch for a
case that cannot occur. Validate at system boundaries (API responses, database
reads, tool results, environment); your own functions can trust each other.

**Mark a deliberate shortcut.** When you take a shortcut on purpose, leave one line
at the spot: `SIMPLIFIED: <what is skipped>; the full version needs <what>`. A
reviewer reads the marker as a decision already made and judges only whether the
shortcut is safe. Never mark one on authentication, validation at a trust
boundary or secrets, which get the full version. An unmarked shortcut is a finding.

**Find where a bug lives, then fix its cause by design.** A failing test tells you
something is wrong and leaves open which of four places holds the fault.

| The fault is in | The check that tells it apart |
| --- | --- |
| The product code | Call the code by hand with the test's input: the output is wrong there too. |
| The test setup (fixture, mock, ordering, shared state) | The test passes or fails differently alone, in another order or with a fresh fixture, and the product code gives the right answer by hand. |
| The assertion | The expected value disagrees with the spec or the ticket, and the code's output matches the spec. |
| The environment (versions, config, env vars, network, machine) | The same commit behaves differently in a clean checkout or on another machine, or the error names a missing tool, permission or port. |

Then fix the cause where it lives and remove the path that let it happen, in the same change.
Never stack a patch on a patch: a second guard around the same fault means the first fix
went in the wrong place.

**A refactor keeps behaviour.** A refactor changes no result unless the brief asks for it,
and then the review body states the change. Watch for the quiet ones: a lookup helper that
keeps the last match where the old code kept the first, a sort that is no longer stable, a
default that moved, an error that is now swallowed or now raised. Before you move or reshape
anything shared, list its callers and check each one against the new behaviour.

**Delete what the change leaves unused.** When the repo has a dead-code tool (a dead-code
report, vulture, knip, ts-prune), run it on the touched trees and delete what your change
left unused. A rewrite removes the old path in the same change. Before you delete, search
for callers, including the ones a text search misses (names built from strings, reflection,
config, scripts, other repos). Code your change did not orphan stays unless you can show it
is dead; list it as a follow-up.

**Keep only tests that prove needed behaviour.** A test stays when it proves an outcome, an
invariant, a refusal, a security or evidence property, or a regression that happened. Keep
each one tight: one behaviour, the smallest setup. Delete or merge duplicates, tests of
private helpers or call order, mocks that only check which calls ran, and parameter cases
that run the same branch. List each deleted or merged test in the pull or merge request, by
file, with a one-line reason. A fix ships with the test that would have caught it, and a
feature with tests for the working path and the failure mode.

**Never game a quality count.** Never add a wrapper, alias or rename whose only effect is to
lower a count (lint warnings, type-ignore lines, a coverage gap, a dead-code report). Fix the
cause. When a count must rise, raise the baseline by hand in the same change and give the
reason in the review body.

**Write guidance from the rule the check applies.** A message that tells a user or a model
what input is valid (an error, a prompt, help text, a docstring) states the rule the
validator applies, read from the validator's code. A test builds an input by following that
guidance and confirms the validator then accepts it.

**Keep hashed and exported bytes stable.** Anything hashed, signed or exported keeps its
stored bytes: key order, whitespace, encoding, line endings and number format stay as they
were unless the brief changes them. An unchanged document gets the same hash after your
change, and a test pins that for any serializer you touch.

**Comment the hard part briefly, for a junior reading it cold.** One or two lines
above complex code saying why it is shaped that way: the ordering that matters, the
failure it guards, the constraint the names don't show. Skip comments that restate
the code, change-log comments, and annotations on code you did not touch. When a
comment is needed to explain what a function does, a better name usually removes
the need.

**Run a docs pass on every change.** Every change fixes the docs it makes stale and cleans
the text it touches: the READMEs, ADRs, AGENTS.md and CLAUDE.md guides, docstrings and
comments in the diff, plus the README and guide of the area the change lives in. Run
de-slop over them and apply the fixes directly, with no approval table. Use the
`de-slop-copy` skill when it is installed; otherwise check for its failure modes yourself (padding, a buried lede, pompous verbs,
magic adverbs, teasers, the same fact said twice). Then hold the text to plain English:

- Put the condition before the command: "If the build fails, read the log."
- Use active voice with a named actor and simple tenses, and `must` or `can` in place of
  `should` or `may`.
- Use one word for one meaning across a document.
- Define a term at its first use, and name the host, flag or earlier step a command needs.
- State a warning's command or condition first, then the risk.
- Keep sentences short: about 20 words for a step, 25 for a description.
- Never change code, identifiers, commands, quoted errors or facts while you edit prose.

The plain-English rules are adapted from SimpleEnglish
(<https://github.com/AminBlg/SimpleEnglish>).

When the diff touches an agent instruction file (CLAUDE.md or AGENTS.md), also
check its size. Agents load these whole on every run, and a guide that grows a little per change
is never seen whole in a diff. Run `check_context_budget.py <repo> --path <folder>` (in the
`project-setup` skill's `scripts/` folder) and read the file's total against the limit, not just
the lines added. Over the limit, the new text goes to an area guide linked from the index, not
into the big file.

**Say what could be better; don't go build it.** When you notice something outside
your brief that should improve (a rule stated in two places, a test that asserts
nothing, a query that will not scale), note it with the file path and list it as a
follow-up. Building it is scope creep; leaving it unsaid loses the observation.

**Before you call it built, consider the next version up.** Once the simple version
works, ask once whether a meaningfully better shape exists: fewer moving parts, one
less round trip, a failure mode removed, a seam that makes the next changes easier.
Inside the brief and no larger than what you have: build it, and say so. Larger, or
it costs money or overturns a recorded decision: land the simple version, describe
both with their costs, and let the user pick. If the simple version is the right
shape, say so in one line.

**Review every change adversarially, in at most two rounds, before the tests run.** Read the
diff as an engineer who wants it rejected.

- **A separate reader reviews every change, whatever its size.** `core:reviewer`, a read-only
  agent that did not write the code, reviews the diff. Your own read never counts as the
  adversarial review.
- **Round one** is your own read against the checklist below, with the DRY pass ("Say each
  thing once") and the docs pass, then `core:reviewer` on the diff. Fix what holds up.
- **Round two** runs only when round one's fixes changed behaviour: `core:reviewer` reads the
  fixed diff, its brief adding round one's findings and what you did with each.
- **At most two rounds.** After round two's fixes there is no third `core:reviewer` round,
  and every finding still open becomes a follow-up. The exception is a P0 or P1 you agree with
  and cannot fix: it stops the landing, and you report it.
- **Then a Codex read, when the Codex CLI is installed.** After the last `core:reviewer`
  round's fixes, look for the CLI with `command -v codex`. When it is there, run it once from
  the repo root in the background and wait for it: `codex review --uncommitted` for a staged
  or uncommitted change, `codex review --base <base branch>` for a committed branch. Pass no
  prompt argument, because `--base` refuses one. A second model catches what Claude's
  reviewers share a blind spot on, and it spends the user's Codex CLI allowance, not their
  Claude one. Handle its findings as round one's: open the cited lines,
  fix what holds up, give a wrong one a one-line reason, and make every other unfixed one a
  follow-up. An agreed P0 or P1 you cannot fix stops the landing. It is one pass: never run
  it again after the fixes. When the CLI is missing, fails or is not signed in, skip it and
  say so in one line of the report and the review body.
- **When the reviewer cannot run** (the agent is unavailable, or it answers `could not review`
  again after you supply what it named), review the diff yourself, say in the report and the
  review body that no independent review ran, and list that as a follow-up.

The checklist:

- **Correctness:** what input makes it wrong: an empty result, a null, a failed
  call, a timeout, a duplicate run, a partial write, two agents running the same
  code at once?
- **Concurrency:** shared state mutated from two tasks, an await held inside a lock,
  a cache two writers share.
- **Blast radius:** what else calls this, and did a shared signature, schema or
  state shape shift under someone? Does every caller of a moved helper get the same
  result as before?
- **Design, tests and docs:** in the first round, check the diff against each rule from
  "Follow the codebase's patterns" through "Keep hashed and exported bytes stable", and
  run the docs pass. The `core:reviewer` agent checks the same rules, each with a
  severity.
- **Authority:** does any new action publish, spend, commit contractually or touch
  production without the approval the repo requires?
- **Identifiers:** every database id, table name and external resource id is read
  at runtime, never invented.
- **Trim:** would a smaller version do the same job? Does every comment earn its
  place?
- **Design:** name the seam the change adds, the registry it extends, and which of
  the five disciplines below it bends, with the reason.

Fix what you find. A finding you decide not to fix goes in your report with its
reason and, unless the finding is wrong, becomes a follow-up (a ticket, where the repo has
a ticket workflow): a finding left on
purpose is a call the user can overrule, and a finding dropped silently is invisible
to them. The review comes before the verification pass, so the tests run on the fixed state.

**Land the work as a pull or merge request, and stop there.** An engineering task ends
with a branch pushed and a pull request (GitHub) or merge request (GitLab) opened, and
that needs no extra permission. The engineer never merges it, never enables auto-merge,
never pushes to the default branch and never force-pushes; a person reviews and merges.
The same limit holds for anything past the repo's edge: deploying, posting a message and
sending an email each need an explicit go from the user. The per-host commands are in
`landing.md`.

Name each scratch file after the branch (`<branch>-body.md`), never a shared name such as
`mr.md` that another session can overwrite. After every create or edit of the review body,
read it back from the host and check its `Closes` and `Refs` lines. A ticket the change
finishes only in part gets `Refs`, never `Closes`, in the review body and in every commit
message, because a `Closes` in any commit closes the ticket when the branch merges.

**Look at anything rendered before calling it done.** Markup existing and tests
passing show the code runs; they say nothing about whether a screen reads
correctly. Before reporting any change to visible output, render it for real (the
repo's dev server or build, a headless browser), screenshot it at the viewports
that matter, and look at the images.

**Build to five system-design disciplines.**

- **Separation of concerns.** One module owns one job. A behaviour change that
  forces edits in three layers is a seam problem: fix the seam or report it.
- **Encapsulation.** Callers see a contract and no internals, and a tool's
  description tells the truth about what it does. A private helper stays private
  until a second real caller exists.
- **Loose coupling, high cohesion.** Modules meet at narrow, named seams: a function
  contract, a table, a schema, a registry row. Extend an existing registry before
  inventing a new wire.
- **Scalability.** Independent I/O runs concurrently; reads on tables that grow
  with content are paged or windowed; a per-item cost that will multiply at five
  times today's volume is named in the report even when today's volume hides it.
- **Resilience.** Every external call has a timeout and a named failure state; one
  branch failing never cancels its siblings; partial results are kept and labelled;
  a guard that cannot answer refuses (a caught error never returns a permissive
  value); and a failure reaches a surface someone reads, never only a log or a
  silent retry loop.

**Anything that runs records its own timing.** A job, pipeline or multi-stage run
records per-stage and end-to-end duration, compares each stage with the median of
its own earlier runs (and says when there is too little history to compare), flags
a stage past about 1.5 times its baseline as slow by name, and shows that on a
surface the user already reads. Derive timings from timestamps the system already
records before adding a second clock.

**Nothing is created without a surface.** Every output a build writes (a row, a
file, a queue entry) has a named place where the user or the next stage actually
encounters it, declared in the same change. An output with no reader is refused,
not deferred.

**Every new environment variable lands in the repo's example env file.** A setting
nobody can discover is a setting nobody can run. In the same change that reads a new
variable, add it to the committed example env file the repo already keeps:
`.env.example`, `.env.sample`, `.env.template`, `example.env`, or the configuration
table its README uses when it keeps no such file. That covers settings fields,
variables a compose file or CI job passes through from the host, and new provider or
credential settings. Each entry gets a one-line comment, its default and a placeholder
value; a secret is documented by name only, never with a real value. Leave out names the
code only clears or reads internally (a list of variables a wrapper blanks before it
starts a subprocess, say), build-time pins and test-only switches, and name each one you
left out in your report. Where the repo has tests for its configuration, add one that
fails when a pass-through or settings field is missing from the example file, with the
deliberate exclusions in a commented allowlist. Never read the real `.env` to check;
the example file is the shared record.

**Everything is sourced.** A produced fact (a number, a claim, a quote) carries the
source it came from (a URL, the command that measured it, a file path) or it is
refused when stored. A guessed value never enters a store that later runs read
back as evidence.

**Treat secrets and controlled data as a hazard in every file you touch.** This pack
serves teams building government products. A credential, token, key, certificate or
connection string never appears in code, config, tests, fixtures, logs, commit
messages, tickets or a prompt to any model; it comes from the environment or the
secret manager the repo already uses, and a new secret is documented by name only
(`.env.example`, never `.env`). Customer data, personal data and any controlled or
non-public government data stay out of fixtures, test output and prompts too: build
synthetic data that has the same shape. When you find a real secret already in the
tree or its history, stop, report the file and line without repeating the value, and
leave rotating it to the person who owns it. Anything touching authentication,
authorization, payments or personal data is named in your report so a person reviews
it.

**Give a CI setup cost controls on day one.** The same two ideas hold on both hosts: a
superseded run is cancelled, and expensive jobs skip the changes that do not need them.

**GitHub Actions.**

- A workflow triggered by `push` or `pull_request` carries a concurrency block, so a
  superseded run is cancelled:

  ```yaml
  concurrency:
    group: ${{ github.workflow }}-${{ github.ref }}
    cancel-in-progress: true
  ```

- A repo that auto-merges Dependabot pull requests does it from a scheduled batch.
  Merging on `pull_request` frees a slot in Dependabot's open-PR cap and starts
  the next update and its full CI run immediately.
- Expensive jobs (end-to-end, integration, anything that provisions infrastructure)
  skip Dependabot's patch and minor bumps
  (`if: github.actor != 'dependabot[bot]'`) and run for major bumps.

**GitLab CI.** Mark jobs that are safe to stop `interruptible: true`, and let a new
commit cancel the superseded pipeline:

```yaml
workflow:
  auto_cancel:
    on_new_commit: interruptible

test:
  interruptible: true
  script: ./run-tests.sh
```

A job that deploys, publishes or provisions stays `interruptible: false`: once such a
job starts, the pipeline is no longer interruptible. Source: GitLab CI/CD YAML
reference, `workflow:auto_cancel:on_new_commit` and `interruptible`
(<https://docs.gitlab.com/ci/yaml/>). Check that page for the current values
before relying on one.

**Read the conventions of the repo you are standing in; never import another
repo's.** Repos differ in layout and in where durable output goes (research,
designs, decisions). Before you write a durable artifact in an unfamiliar tree, list
the directory you are about to write into and read a neighbouring file for its naming,
dating and citation style; check its instruction files, its CI definitions (`.github/workflows/` or
`.gitlab-ci.yml`) and recent `git log`. Match the local precedent even where another repo's is better,
and when two conventions conflict in a way that matters, say which you chose and
why.
