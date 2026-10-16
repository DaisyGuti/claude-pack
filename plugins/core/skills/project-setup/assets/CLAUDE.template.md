# {{project name}}

<!--
Template from the project-setup skill; its SKILL.md says how to fill it. Delete this comment
and every {{placeholder}}. Keep the file a short router under 200 lines: one owner per fact,
links in place of copies. The Security rules section is the team's standing text; keep it,
and add only rules the repo itself states.
-->

{{One paragraph: what the product does, who uses it, and what "working" means for it.}}

## Where the rules live

{{List each file that owns project rules and what it owns, for example "`CONTRIBUTING.md`:
conventions and review rule". Link to them; copy nothing. If the repo has an AGENTS.md, this
section is the single line `@AGENTS.md` plus what Claude Code needs on top of it. Delete this
section when this file is the only rules file.}}

## Commands

Every command below is copied from a file in the repo; the source is in parentheses.

- Install: `{{command}}` ({{source}})
- Run locally: `{{command}}`
- Tests, one file: `{{command}}`
- Tests, all: `{{command}}`
- Lint, format, types: `{{command}}`
- Build: `{{command}}`

## Definition of done

- {{The checks that must pass before work counts as done, as the CI file runs them.}}
- {{How to exercise the real path: a dev server URL, a CLI invocation, a fixture.}}
- {{For visible changes: render the page and look at it before reporting.}}

## Landing changes

- Branch from `{{default branch}}`, push the branch and open a {{pull request|merge request}}.
  Never commit or push to `{{default branch}}`, and never force-push a shared branch.
- {{Review requirements the repo's files state: code owners, the template to fill, title or
  label conventions, what must pass before a merge. Delete the line if there are none.}}
- Commit messages: {{style the repo uses, for example Conventional Commits}}.
- {{Signed commits are required here; do not bypass signing or hooks. Keep this line only when
  the repo signs commits.}}

## Security rules

- Secrets: no credential, token, key, certificate or connection string in code, config,
  tests, fixtures, logs, commit messages, tickets or prompts. Credentials come from
  {{the secret mechanism the repo uses}}; a new one is documented by name only in
  {{`.env.example`}}. If you find a real secret in the tree, stop and tell a person; do not
  repeat its value.
- Data: no customer data, personal data or controlled or non-public government data in a
  prompt to any model, a fixture, a ticket or test output. Use synthetic data with the same
  shape.
- Dependencies: commit and respect the lockfile ({{lockfile}}), pin container base images by
  digest and CI actions or includes by commit SHA. Before adding a dependency, check its
  license and maintenance, and say why in the review.
- Human review: anything that touches authentication, authorization, payments, personal data
  or secrets is named in the review description and merged by a person, never by Claude.
- Enforcement: this file is guidance. Blocks on secret leaks and destructive commands come
  from the `guardrails` plugin when it is installed.
- Going deeper: the `security` plugin covers threat models, secure code review, and secret
  and dependency scans; the `secure-build` plugin covers hardened Dockerfiles, image scans,
  signing and pipelines. Run `/plugin` to see what is installed.

## Ask before

- {{Repo-specific actions that need a person's go-ahead: deploys, migrations, paid services,
  production data, deleting data, public posts.}}

## Conventions

- {{Language, framework and version pins; the idioms this repo follows.}}
- {{Layout: where new modules, tests and assets go.}}
- {{Durable output: where research, designs and decisions go.}}
