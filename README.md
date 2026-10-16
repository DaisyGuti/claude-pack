# claude-pack

A private Claude Code plugin marketplace for the team: portable skills, agents and hooks
for engineering work on government products, covering tickets on GitHub and GitLab,
model choice, design and accessibility, security and compliance evidence, hardened
builds, and team communication. Each person installs only the plugins they want. Where
an official Claude Code plugin already covers a job, this pack recommends it and builds
only the gap. The rules every author follows are in
[`docs/conventions.md`](docs/conventions.md), built on Anthropic's rules in
[`docs/authoring-guide.md`](docs/authoring-guide.md).

| Plugin | What it carries |
| --- | --- |
| [`core`](plugins/core) | Engineering agent, read-only reviewer and forward-tester agents, and repo setup that writes a repository's CLAUDE.md |
| [`tickets`](plugins/tickets) | GitHub and GitLab ticket flow: write, plan, groom and work tickets |
| [`models`](plugins/models) | Model choice, prompt optimizing, a Claude Code usage report, and an audit of how the product's code uses AI models |
| [`design`](plugins/design) | UI/UX agent and design skills: typography, UX review, web interface guidelines, React patterns, U.S. Web Design System |
| [`accessibility`](plugins/accessibility) | WCAG 2.2 scan, inspect, audit, fix and diff, plus Section 508 conformance reports |
| [`security`](plugins/security) | Threat modeling, secure code review, secret and dependency scans, government compliance mapping, security-auditor agent |
| [`secure-build`](plugins/secure-build) | Hardened Dockerfiles and images, image scanning, signing and SBOMs, hardened GitHub Actions and GitLab CI, GCP security review, GitHub-to-GitLab migration |
| [`guardrails`](plugins/guardrails) | Hooks that block risky commands and secret leaks while Claude works |
| [`team-comms`](plugins/team-comms) | Slack thread summaries and replies, status updates, standups, design docs and decision records |

## Install

Filled in by the integrator.

## Developing

```sh
uv run python scripts/validate.py [plugin]   # claude plugin validate; the missing-version warning is allowed
uv run pytest tests/<plugin>
uv run ruff check
```

See [`docs/conventions.md`](docs/conventions.md) for the full rules, including evals.
