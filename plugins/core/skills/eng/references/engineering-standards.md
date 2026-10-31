# Engineering standards

These are the standing rules for every engineer working with this pack. They bind across
the whole engineering pass, in any repo. The repo's own CLAUDE.md wins every question of
house style; this file is about how you work.

## Contents

- Run independent work in parallel
- Run tests and gates at the repo's full parallelism
- Hold the industry standard of the technology you are standing in
- Use the design pattern the problem calls for, and no more
- Keep it simple while covering the whole requirement
- Mark a deliberate shortcut
- Find where a bug lives before you fix it there
- Delete code only when you can show it is unused
- Comment the hard part briefly, for a junior reading it cold
- Say what could be better; don't go build it
- Before you call it built, consider the next version up
- Review your own diff adversarially, before anything runs the tests
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

**Hold the industry standard of the technology you are standing in.** Follow each
framework's documented idioms; code that fights its framework breaks on the next upgrade. The repo's own
conventions (language version, type checking, test layout, logging, where secrets
live) are the standard you are held to. Before writing new code against a
fast-moving library or API, read its current documentation. When it is
unreachable, mark the line `UNVERIFIED:` with your assumption and say so in your
report. Never present a guessed API as one you read.

**Use the design pattern the problem calls for, and no more.** A named pattern
earns its place when it removes a real branch or a real coupling. Applied to one
call site it is bloat with a good name. Usually the pattern already exists in the
repo; match it.

**Keep it simple while covering the whole requirement.** Cover everything asked and
add nothing that was not: no helper for a single call site, no abstraction for a
future that has not arrived, no config flag nobody set, no defensive branch for a
case that cannot occur. Validate at system boundaries (API responses, database
reads, tool results, environment); your own functions can trust each other. A fix ships
with the test that would have caught it, and a feature with tests for the working
path and the failure mode.

**Mark a deliberate shortcut.** When you take a shortcut on purpose, leave one line
at the spot: `SIMPLIFIED: <what is skipped>; the full version needs <what>`. A
reviewer reads the marker as a decision already made and judges only whether the
shortcut is safe. Never mark one on authentication, validation at a trust
boundary or secrets, which get the full version. An unmarked shortcut is a finding.

**Find where a bug lives before you fix it there.** A failing test tells you
something is wrong and leaves open which of four places holds the fault.

| The fault is in | The check that tells it apart |
| --- | --- |
| The product code | Call the code by hand with the test's input: the output is wrong there too. |
| The test setup (fixture, mock, ordering, shared state) | The test passes or fails differently alone, in another order or with a fresh fixture, and the product code gives the right answer by hand. |
| The assertion | The expected value disagrees with the spec or the ticket, and the code's output matches the spec. |
| The environment (versions, config, env vars, network, machine) | The same commit behaves differently in a clean checkout or on another machine, or the error names a missing tool, permission or port. |

**Delete code only when you can show it is unused.** Search for callers,
including the ones a text search misses (names built from strings, reflection,
config, scripts, other repos). When you still cannot show it is dead, ask before
you delete it.

**Comment the hard part briefly, for a junior reading it cold.** One or two lines
above complex code saying why it is shaped that way: the ordering that matters, the
failure it guards, the constraint the names don't show. Skip comments that restate
the code, change-log comments, and annotations on code you did not touch. When a
comment is needed to explain what a function does, a better name usually removes
the need.

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

**Review your own diff adversarially, before anything runs the tests.** Read the
diff as an engineer who wants it rejected.

- **Correctness:** what input makes it wrong: an empty result, a null, a failed
  call, a timeout, a duplicate run, a partial write, two agents running the same
  code at once?
- **Concurrency:** shared state mutated from two tasks, an await held inside a lock,
  a cache two writers share.
- **Blast radius:** what else calls this, and did a shared signature, schema or
  state shape shift under someone?
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
