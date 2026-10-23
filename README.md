# claude-pack

A private set of Claude Code plugins for a team building government software. It covers
tickets on GitHub and GitLab, choosing a model, UI and accessibility work, security and
compliance evidence, hardened builds, and team writing. Each person installs the plugins they
want. Where an official Claude Code plugin already does a job, this pack points you to it and
builds only the missing part.

Everything is written to be safe to share: no personal names, no secrets, no machine paths.
GitHub and GitLab are both supported wherever a tracker, pull request or CI is involved.

- [The plugins](#the-plugins)
- [Every skill and agent](#every-skill-and-agent)
- [Install on a new machine](#install-on-a-new-machine)
- [Updating, uninstalling, reloading](#updating-uninstalling-reloading)
- [Recommended companion plugins](#recommended-companion-plugins)
- [Sharing with a teammate](#sharing-with-a-teammate)
- [Moving to GitLab](#moving-to-gitlab)
- [Your own preferences file (optional)](#your-own-preferences-file-optional)
- [Contributing](#contributing)

## The plugins

| Plugin | What it carries |
| --- | --- |
| [`core`](plugins/core) | An engineering agent that lands work as a pull or merge request, a read-only reviewer, a forward-tester that runs a change like a user would, and repo setup that writes a repository's CLAUDE.md |
| [`tickets`](plugins/tickets) | The ticket flow for GitHub and GitLab: write, plan, groom and work tickets |
| [`models`](plugins/models) | Model choice, prompt optimizing, a Claude Code usage report, and an audit of how your product's code uses AI models |
| [`ui-design`](plugins/ui-design) | A UI/UX agent, UX review, web interface guidelines, React and React Native rules, and the U.S. Web Design System |
| [`accessibility`](plugins/accessibility) | Section 508 Accessibility Conformance Reports (VPAT) built from audit evidence. The WCAG scan, inspect, audit, fix and diff skills come from AccessLint (see [companions](#recommended-companion-plugins)) |
| [`security`](plugins/security) | Threat modeling, one merged scan from the free scanners, government compliance mapping, and a security-auditor agent |
| [`secure-build`](plugins/secure-build) | Hardened Dockerfiles and CI, image scanning, SBOMs and signing, a read-only Google Cloud review, and GitHub-to-GitLab migration |
| [`guardrails`](plugins/guardrails) | Hooks that block risky commands, secret leaks and pushes to the main branch while Claude works |
| [`team-comms`](plugins/team-comms) | Slack catch-ups and drafts, status updates and standups, design docs and decision records |

## Every skill and agent

A skill runs as `/plugin:skill`. An agent is called by name, as `@agent-plugin:name`, or Claude
hands work to it on its own. Claude also starts a skill when you ask for its job in chat, so you
do not need to type the command. Skills that change a tracker, send a message or move a repository
carry their own dry-run or confirmation step.

### core

| Invoke | What it does |
| --- | --- |
| `@agent-core:eng` | The engineering pass for a fix, feature, refactor or review. Reads the real code, builds the smallest complete change, reviews its own diff, runs the repo's checks, then pushes a branch and opens a pull or merge request. It never merges and never pushes to the default branch |
| `/core:eng` | Slash entry that hands a task to the `eng` agent |
| `@agent-core:reviewer` | A fast, read-only review of one diff, branch or pull request, with ranked findings and a file and line for each |
| `@agent-core:forward-tester` | Runs a finished change the way a user would (a command, a local server, a page) and reports what happened. Never edits code |
| `/core:project-setup` | Writes or refreshes a repo's CLAUDE.md from its real build, test and lint commands plus the team's rules |

### tickets

| Invoke | What it does |
| --- | --- |
| `/tickets:write-ticket` | Checks the premise against the repo, then files a ticket in the shape the workers need, with priority, model and run labels |
| `/tickets:plan-ticket` | Writes a short build plan on the next Ready ticket and sets its model and run labels |
| `/tickets:daily-grooming` | Tidies the board so Ready means safe to start. Try `--dry-run` first |
| `/tickets:work-tickets` | Works your Ready tickets in parallel, each in its own worktree on the model its label names, ending with a pull or merge request per ticket |
| `/tickets:ticket-worker` | Works one issue from plan to an open pull or merge request |
| `@agent-tickets:ticket-worker` | The worker the two skills above start. Do not call it directly |

### models

| Invoke | What it does |
| --- | --- |
| `/models:prompt-optimizer` | Rewrites a prompt against Anthropic's current guidance and says which model and effort should run it |
| `/models:model-recommender` | Which Claude model and effort suit a kind of work, using the current lineup and prices fetched when it runs |
| `/models:usage-report` | Token use and estimated cost across your Claude Code sessions, by model, subagent, project and session |
| `/models:model-usage-audit` | Audits how a codebase calls AI models: model ids, retries, cost, where data goes. Reports evidence and gaps |

### ui-design

| Invoke | What it does |
| --- | --- |
| `@agent-ui-design:ui-ux` | Renders a page in a real browser, looks at it, reviews it and fixes it |
| `/ui-design:ux-review` | Judges a screenshot, mockup or flow for usability, accessibility and visual craft, with a scored critique |
| `/ui-design:web-design-guidelines` | Reviews UI code against Vercel's Web Interface Guidelines, fetched fresh each time |
| `/ui-design:uswds` | Builds or reviews a UI with the U.S. Web Design System and the federal website requirements |
| `/ui-design:composition-patterns` | Vercel's React composition rules (compound components, explicit variants) |
| `/ui-design:react-best-practices` | Vercel's React and Next.js performance rules, ranked by impact |
| `/ui-design:react-native-skills` | Vercel's React Native and Expo rules for lists, animation, navigation and UI |

### accessibility

| Invoke | What it does |
| --- | --- |
| `/accessibility:section-508-report` | Builds an Accessibility Conformance Report on the VPAT 2.5Rev template from audit findings. Refuses to mark a row Supports without a passing check run by a person |

### security

| Invoke | What it does |
| --- | --- |
| `/security:threat-model` | A STRIDE threat model as a reviewable document with a data flow diagram and NIST 800-53 control mappings |
| `/security:security-scan` | Runs the free scanners you have installed (gitleaks, osv-scanner, grype, semgrep, trivy, checkov) and merges them into one report. Never installs anything |
| `/security:compliance-map` | An evidence-and-gaps table for FedRAMP, SSDF, 800-171 and CMMC, the DoD cloud SRG and FIPS 140-3. Never says a system is compliant |
| `@agent-security:security-auditor` | A read-only audit of a repo before a release or merge |

### secure-build

| Invoke | What it does |
| --- | --- |
| `/secure-build:dockerfile-harden` | Reviews and rewrites Dockerfiles and Compose files for container hardening |
| `/secure-build:image-supply-chain` | Scans an image, writes SBOMs, signs with cosign and verifies signatures |
| `/secure-build:ci-harden` | Audits and hardens GitHub Actions and GitLab CI, with reference pipelines that push to Artifact Registry using Workload Identity Federation |
| `/secure-build:gcp-review` | A read-only security review of Google Cloud projects. Reports evidence, gaps and drafted fixes |
| `/secure-build:gitlab-migration` | Plans a GitHub-to-GitLab move and carries it out one confirmed step at a time |

### guardrails

| Invoke | What it does |
| --- | --- |
| hooks (always on) | Block force-pushes and direct pushes to the main branch, skipped git hooks, downloaded code run unread, turned-off TLS checks, public Google Cloud access, service account keys, privileged containers, credentials written to files, and secret files read into the conversation |
| `/guardrails:guardrails-help` | Explains a block, lists the rules, and shows how a person allows one on purpose |

### team-comms

| Invoke | What it does |
| --- | --- |
| `/team-comms:slack-catchup` | Summarizes Slack channels, threads and DMs into decisions, asks, blockers and FYIs. Read-only |
| `/team-comms:slack-draft` | Drafts a Slack message or reply for a goal. Never posts |
| `/team-comms:slack-send` | Posts or saves a message you already approved, after one last confirmation |
| `/team-comms:status-update` | A standup or weekly update from your commits, pull requests and tickets |
| `/team-comms:design-doc` | A design doc with a required security and compliance section |
| `/team-comms:adr` | A numbered architecture decision record in MADR format |

## Install on a new machine

You need access to the private repository first. Ask the owner to add you as a collaborator
(see [Sharing with a teammate](#sharing-with-a-teammate)). Claude Code clones the marketplace
with the git credentials already on your machine and never asks for a password, so step 2 matters.

1. **Install Claude Code.**
   - macOS, Linux and WSL: `curl -fsSL https://claude.ai/install.sh | bash`
   - Windows PowerShell: `irm https://claude.ai/install.ps1 | iex`
   - Homebrew: `brew install --cask claude-code`

   Open a new terminal, run `claude --version`, then run `claude` once and sign in.
2. **Give git your GitHub credentials.** Install the GitHub CLI (<https://cli.github.com>), then:

   ```sh
   gh auth login
   gh auth setup-git
   ```

   `gh auth setup-git` is the step people miss. It makes plain `git clone` work for private repos,
   which is how Claude Code reads this marketplace. An SSH key loaded in `ssh-agent` also works.

   If the pack lives on GitLab, sign in there instead (see [Moving to GitLab](#moving-to-gitlab),
   step 3).
3. **Install the pack.** Pick one route.

   **Route A: the installer script.** It checks your setup, adds the marketplace, installs
   every plugin, and keeps a record so it can undo exactly what it did. It installs from the
   place you cloned it: a clone from GitLab (or any host other than GitHub) installs from that
   host, so there is nothing to pass.

   ```sh
   git clone https://github.com/DaisyGuti/claude-pack.git
   cd claude-pack
   ./install.sh
   ```

   Useful options:

   ```sh
   ./install.sh --only core,security,guardrails   # just these plugins
   ./install.sh --with-recommended                # also the official companion plugins
   ./install.sh --with-third-party                # also AccessLint and typography (read the warning below)
   ./install.sh --with-preferences                # copy the optional preferences file (only if you have none)
   ./install.sh --scope project                   # install for one repository instead of for you
   ./install.sh --dry-run                         # show the claude commands without running them
   ./install.sh --check                           # report what is missing or out of date
   ```

   **Route B: inside Claude Code.** No clone needed.

   ```text
   /plugin marketplace add DaisyGuti/claude-pack
   /plugin install core@claude-pack
   /plugin install tickets@claude-pack
   ```

   Repeat `/plugin install <name>@claude-pack` for each plugin you want. From a shell, one command
   does the add and the install together (Claude Code 2.1.292 or later):

   ```sh
   claude plugin install core --marketplace DaisyGuti/claude-pack
   ```
4. **Reload.** Restart Claude Code, or run `/reload-plugins` inside a session. Type `/` and look
   for names like `/core:project-setup`.
5. **Turn on automatic updates for this marketplace.** They are off by default for any
   marketplace that is not Anthropic's. In Claude Code run `/plugin`, open **Marketplaces**,
   choose `claude-pack`, and pick **Enable auto-update**. Updates apply the next time you start
   Claude Code. If the marketplace cannot be reached (offline, expired login), set
   `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1` so Claude Code keeps the last good copy
   and skips the re-clone.

### Claude Code versions

The installer prints a warning when your version is too old for a feature. Update with
`claude update` (or `brew upgrade claude-code`).

| Feature | Needs Claude Code |
| --- | --- |
| Guardrails hooks that block even when a hook crashes (`onFailure: block`) | 2.1.295 or later |
| The per-ticket effort label in `tickets` | 2.1.292 or later |
| Install and add a marketplace in one command (`--marketplace`) | 2.1.292 or later |
| `claude plugin eval`, used to test the skills | 2.1.269 or later |

## Updating, uninstalling, reloading

```sh
claude plugin marketplace update claude-pack     # refresh the list of plugins
claude plugin update core@claude-pack            # update one plugin
./install.sh --check                             # see which plugins are behind
./install.sh --uninstall                         # remove what install.sh installed, and nothing else
claude plugin uninstall core@claude-pack         # remove one plugin by hand
claude plugin marketplace remove claude-pack     # remove the marketplace (this also uninstalls its plugins)
```

In a session, `/plugin` has an **Installed** tab (enable, disable, update, uninstall) and a
**Marketplaces** tab (**Update marketplace** refreshes the list and updates the plugins you
installed from it). After any change, run `/reload-plugins` or restart Claude Code. Claude Code
can show what each plugin costs in every session: `claude plugin details <name>`.

`./install.sh --uninstall` removes the plugins, the marketplace, and the preferences file only
if this script added them. A plugin or a marketplace you added yourself stays.

## Recommended companion plugins

Install these alongside the pack. They do jobs this pack leaves to their authors. The installer
adds the official ones with `./install.sh --with-recommended`. By hand, add the official
marketplace once, then install what you want:

```sh
claude plugin marketplace add anthropics/claude-plugins-official
```

| Plugin | Why you want it | Install |
| --- | --- | --- |
| `code-review` | Multi-agent pull request review that can post comments | `claude plugin install code-review@claude-plugins-official` |
| `pr-review-toolkit` | Focused review agents for comments, tests, error handling and types | `claude plugin install pr-review-toolkit@claude-plugins-official` |
| `claude-security` | Deep vulnerability hunting in your own code, with verified findings and patches | `claude plugin install claude-security@claude-plugins-official` |
| `security-guidance` | Warnings on risky edits and a review of each diff | `claude plugin install security-guidance@claude-plugins-official` |
| `hookify` | Turn a repeated correction into a hook | `claude plugin install hookify@claude-plugins-official` |
| `frontend-design` | Distinctive visual design when you build new UI (use `ui-design:uswds` when a design system is prescribed) | `claude plugin install frontend-design@claude-plugins-official` |
| `claude-md-management` | Score and improve a CLAUDE.md that `core:project-setup` wrote | `claude plugin install claude-md-management@claude-plugins-official` |
| `claude-code-setup` | Recommends hooks, skills and servers for a codebase | `claude plugin install claude-code-setup@claude-plugins-official` |
| `session-report` | An HTML report of Claude Code usage | `claude plugin install session-report@claude-plugins-official` |
| `skill-creator` | Write and test your own skills | `claude plugin install skill-creator@claude-plugins-official` |
| `slack` | The way to connect Slack. `team-comms` uses it to read and post, and it adds `/slack:standup` and more | `claude plugin install slack@claude-plugins-official` |
| `github` | GitHub tools for Claude | `claude plugin install github@claude-plugins-official` |
| `gitlab` | GitLab tools for Claude | `claude plugin install gitlab@claude-plugins-official` |
| `terraform` | Terraform tools for Claude | `claude plugin install terraform@claude-plugins-official` |

To install the lot in one go:

```sh
for p in code-review pr-review-toolkit claude-security security-guidance hookify frontend-design \
  claude-md-management claude-code-setup session-report skill-creator slack github gitlab terraform; do
  claude plugin install "$p@claude-plugins-official"
done
```

`team-comms` needs Slack connected to read or post. Without it, the skills work from text you
paste in. [`plugins/team-comms/docs/connect-slack.md`](plugins/team-comms/docs/connect-slack.md)
lists every way to connect and what a workspace admin has to approve.

### From other authors (third party)

These come from their own marketplaces. Read what you are installing first.

**AccessLint** adds the WCAG 2.2 skills: scan one page, inspect with the keyboard and screen
reader, audit a whole site, fix, and diff.

```sh
claude plugin marketplace add accesslint/skills
claude plugin install accesslint@accesslint
```

Plain warning: AccessLint's skills and its bundled server run `npx -y @accesslint/...@latest`,
which downloads and runs whatever version npm serves at that moment. Nothing pins it. On a
government laptop, have your security contact review it before you install. The
[`accessibility`](plugins/accessibility) plugin works without it; it only needs audit results
from somewhere.

**Typography** (from the bencium marketplace) sets curly quotes, dashes and spacing in generated
UI text. Install only this one plugin from that marketplace.

```sh
claude plugin marketplace add bencium/bencium-marketplace
claude plugin install typography@bencium-marketplace
```

`./install.sh --with-third-party` installs both. The tools some skills call (gitleaks, trivy,
hadolint and others) are free, open-source programs. The skills list the ones they use and never
install them for you.

## Sharing with a teammate

1. **Give them read access to the repository.** On GitHub that means adding them as a
   collaborator (Settings, then Collaborators), or from a shell:

   ```sh
   gh api -X PUT repos/DaisyGuti/claude-pack/collaborators/THEIR-USERNAME -f permission=pull
   ```

   They accept the emailed invitation, then follow [Install on a new machine](#install-on-a-new-machine).
   On GitLab, add them as a project member with the Reporter role or higher (**Manage**, then
   **Members**); Guest cannot read the code of a private project.
2. **Or turn the pack on for a whole repository.** Put this in that repository's
   `.claude/settings.json` and commit it:

   ```json
   {
     "extraKnownMarketplaces": {
       "claude-pack": {
         "source": { "source": "github", "repo": "DaisyGuti/claude-pack" },
         "autoUpdate": true
       }
     },
     "enabledPlugins": {
       "core@claude-pack": true,
       "guardrails@claude-pack": true
     }
   }
   ```

   `claude plugin marketplace add DaisyGuti/claude-pack --scope project` writes the marketplace
   entry for you. Two things to know. First, Claude Code only reads this after a person accepts
   the trust prompt for that folder; in an untrusted folder, and in `claude -p` runs, it is
   ignored without a message. Second, committing the file does not download anything. Each person
   still needs repo access and git credentials (steps 1 and 2 above). If Claude Code says a plugin
   "is enabled in project settings but isn't installed", that person runs
   `claude plugin install core@claude-pack --scope project` once.

Cloud sessions do not load a repository's plugins.

## Moving to GitLab

The marketplace works from any git host. Nothing in the pack depends on GitHub, and every skill
that touches a tracker, pull request or pipeline already supports `gh` and `glab`.

1. Push this repository to GitLab (a normal `git push` to a new project).
2. Use the full clone URL. A bare `gitlab.example.com/group/repo` is read as a GitHub name and
   fails.

   ```sh
   claude plugin marketplace add https://gitlab.example.com/group/claude-pack.git
   ```

   or, with the installer:

   ```sh
   ./install.sh --source https://gitlab.example.com/group/claude-pack.git
   ```
3. Credentials work the same way as on GitHub: a git credential helper that already holds a
   token, or an SSH key in `ssh-agent`. Claude Code has no GitLab token setting and never
   prompts, so a credential git would have to ask for fails. The GitLab equivalent of
   `gh auth login && gh auth setup-git` is:

   ```sh
   glab auth login --hostname gitlab.example.com
   git config --global --add credential.https://gitlab.example.com.helper '!glab auth git-credential'
   ```

   Use your own host in place of `gitlab.example.com`. Newer `glab` releases can set the helper
   during login with `--setup-git-credential-helper`; run `glab auth login --help` to see
   whether yours does. `./install.sh --check` reports whether git can read the marketplace
   without a prompt and prints these two commands when it cannot.
4. A repo's `.claude/settings.json` uses the `git` source instead:

   ```json
   { "source": { "source": "git", "url": "https://gitlab.example.com/group/claude-pack.git" } }
   ```
5. To switch an existing install, run `./install.sh --uninstall`, then run `./install.sh` from a
   clone of the GitLab project (or pass `--source <the GitLab URL>`). `install.sh` refuses to
   reuse the `claude-pack` name from a different source on purpose.

## Your own preferences file (optional)

[`preferences/CLAUDE.md`](preferences/CLAUDE.md) is one person's working style: plain-English
replies, a check for a simpler path before building, free options before paid ones, the cheapest
model that does each job, and ticket status kept in step with the work. It is personal. Teammates
can skip it or write their own. `./install.sh --with-preferences` copies it to
`~/.claude/CLAUDE.md` only when you have no such file, and never overwrites one.

## Contributing

Read [`docs/conventions.md`](docs/conventions.md) first. It holds the rules every skill, agent
and hook must meet, and cites Anthropic's own rules in [`docs/authoring-guide.md`](docs/authoring-guide.md).
The short version:

- **Each engineer edits one plugin.** Change only `plugins/<name>/` and `tests/<name>/`. Shared
  files (`.claude-plugin/marketplace.json`, `pyproject.toml`, this README, `THIRD_PARTY_NOTICES.md`,
  `docs/`, `scripts/`, `install.sh`) change through the integrator.
- **Check the official plugins first** (`~/.claude/plugins/marketplaces/claude-plugins-official/`).
  Build only the gap.
- **No personal names, secrets or machine paths.** Everything here reaches every teammate.
- **Compliance skills produce evidence and gaps.** They never declare a system compliant.
- **Anything that posts, sends, pushes, merges or deploys drafts first** and acts only on the
  user's go, or runs `--dry-run` first where the skill offers it.

### Gates before a merge

```sh
uv run python scripts/validate.py <plugin>   # marketplace, plugin, skills, agents and frontmatter
uv run pytest tests/<plugin>
uv run ruff check
uv run ruff format --check
git ls-files -z '*.sh' | xargs -0 shellcheck -x   # every shell script
```

CI runs all of these over the whole pack on every pull request and on `main`
([`.github/workflows/ci.yml`](.github/workflows/ci.yml), or
[`.gitlab-ci.yml`](.gitlab-ci.yml) on GitLab). Its `check` job must pass before a merge.

`claude plugin validate --strict` cannot pass here, because `version` is left out on purpose so
updates follow the git commit. `scripts/validate.py` allows that one warning and fails on every
other error and warning. It also checks the frontmatter itself, because `claude plugin validate`
passes some broken files (a description cut off at ` #`, a plain value that holds `: `).

### Evals

Every skill has at least three cases under `plugins/<name>/evals/`, and every agent has one.
Writing them is required. Running the whole suite is not, because it spends your plan's
allowance. Run one case once to prove it loads:

```sh
claude plugin eval plugins/<name>/evals/<case> --max-cost-usd 1
```

Things that trip people up:

- A typed `/plugin:skill` command makes no Skill tool call. A case that types the command
  grades the trace with a `regex` grader (`target: trace`); a natural-language case keeps the
  `tool_used: Skill` grader.
- Quote an eval `description:` that holds a colon. Write long text as a folded block (`>-`),
  because a plain value is cut at a space followed by `#`.
- Regex graders reject inline flags like `(?i)`. Use the `flags:` field.
- An eval that grants `Bash` fails on a machine whose `~/.docker` holds a symlink.

The conventions file has the full list and the grader format.

### Third-party material and notices

A skill adapted from another project keeps that project's license text in its own folder and
gets a row in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Read every bundled file of an
outside skill before it lands.

Branch, open a pull request (a merge request on GitLab), and merge once the gates pass. The
integrator rebases before merging.
