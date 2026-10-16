---
name: uswds
description: Builds or reviews a web UI with the U.S. Web Design System (USWDS) - install and compile, components copied from the official docs, design tokens, utility classes, the layout grid, page templates, USWDS's accessibility guidance, and the federal website requirements it supports (21st Century IDEA Act, OMB M-23-22, the federal website standards). Fetches the current USWDS version, component pages and website-standard statuses when it runs, and checks templates for class names the compiled stylesheet does not define. Use when a project or request mentions USWDS, the U.S. Web Design System, usa- classes, designsystem.digital.gov, a federal or .gov website, the government banner, Section 508 for a web UI, or "make this look like a federal site", even if the user does not name USWDS. Use this instead of frontend-design when the design system is prescribed; it states facts and gaps and never declares a site compliant.
argument-hint: "[build|review|upgrade] [paths or description]"
allowed-tools: Read Grep Glob Bash(${CLAUDE_SKILL_DIR}/scripts/uswds_check.py *) WebFetch(domain:designsystem.digital.gov) WebFetch(domain:standards.digital.gov)
---

# USWDS

USWDS prescribes the look, the markup and much of the accessibility behavior of a federal
web UI, so the job is to follow it exactly where it speaks and to say so where it does not.
Component markup, versions and the federal website standards change between releases, so
fetch them every run. Do not write USWDS markup, class names or rules from memory.

## Start here

1. Work out the task: **build** (new page or component), **review** (existing templates or
   a diff) or **upgrade** (version change). Say which one you assumed.
2. Find out where the project stands. Run the version check from the project root:

   ```sh
   ${CLAUDE_SKILL_DIR}/scripts/uswds_check.py version --project .
   ```

   It prints the installed `@uswds/uswds` version, the latest on npm, and whether
   `package.json` pins an exact version. Exit 1 means not installed or behind, and exit 2
   means the registry or a file could not be read. Report that and continue with the
   version the project has.
3. Fetch what the task needs from `https://designsystem.digital.gov/`:
   - the component list: `/components/overview/`, then the component's own page
     `/components/<name>/`;
   - for install and compile questions: `/documentation/getting-started/developers/phase-one-install/`
     and `.../phase-two-compile/`;
   - tokens `/design-tokens/`, utilities `/utilities/`, grid `/utilities/layout-grid/`.
4. When the task touches a federal requirement, fetch `https://standards.digital.gov/standards/`
   and read each standard's status there.

## Build

1. Take each component's HTML from its page under "Component code" and change content only.
   The class names, attributes and element order carry the accessibility behavior.
2. Style with tokens and utilities. Add project CSS only where USWDS has no class, and keep
   it in the project's Sass entry point after the USWDS forward.
3. Load the stylesheet and the initializer in `<head>` and the library at the end of `<body>`.
   Components with JavaScript (accordion, banner, header, modal, and others) need them.
4. Pin the version with `npm install @uswds/uswds --save-exact`.
5. Check your own work: run the two script checks below on what you wrote. State what they
   found and what they cannot see.

Read `${CLAUDE_SKILL_DIR}/references/building-with-uswds.md` for install, compile, tokens,
utilities and the grid.

## Review

Follow `${CLAUDE_SKILL_DIR}/references/review-checklist.md`. The deterministic part is two
commands; run both over the templates in scope:

```sh
${CLAUDE_SKILL_DIR}/scripts/uswds_check.py classes \
  --css node_modules/@uswds/uswds/dist/css/uswds.css <template folders or files>
${CLAUDE_SKILL_DIR}/scripts/uswds_check.py page <base layout or page files>
```

- `classes` lists `usa-` class names the stylesheet does not define (typos, classes removed
  by an upgrade). Point `--css` at the project's own compiled CSS when it has one. Add
  `--prefix REGEX` to check utility classes too. A class that only JavaScript adds will be
  reported as well, so confirm each hit before calling it a defect.
- `page` reports, for each full HTML document, whether `lang`, a title, the viewport meta, a
  meta description, the skip link, the government banner and the USWDS scripts are present.

Everything else in the checklist is a comparison with the fetched component page. Report
findings with `file:line`, the rule, where USWDS documents it, and the change.

## Upgrade

Read `https://github.com/uswds/uswds/releases` for each version between the installed one
and the target, and the "latest updates" table on each component the project uses. For a
major version change, fetch `https://designsystem.digital.gov/documentation/migration/`
first. After the change, re-run `classes` over the templates.

## Federal requirements

Read `${CLAUDE_SKILL_DIR}/references/federal-requirements.md` before saying that a rule
applies. It holds the 21st Century IDEA Act section 3 and OMB M-23-22 as read from the
primary sources, how the federal website standards are published, and what to say about
Section 508. Rules for reporting:

- The Act and the memo bind executive agencies. For a company's product, the contract and
  the agency decide what applies. Ask which case it is, and state what you assumed.
- Name the source and the date for every federal claim, and report each website standard
  with the status you fetched.
- Report facts and gaps ("the template has no banner element; the standard's status is
  pending"). Never write that a site "is compliant", "meets Section 508" or "satisfies the
  IDEA Act". A person with the authority decides that.

## Accessibility boundary

USWDS tests its own components and states that building with them "does not guarantee an
accessible service". The product still needs its own testing. This skill checks markup
against USWDS's documented rules. It does not run a screen reader, a keyboard pass or a
zoom test. For those, and for a conformance report, point to the `accessibility` plugin:
its `section-508-report` skill turns audit evidence into a report that states what is and
is not evidenced. USWDS's component test status can be cited there as supporting context
only.

## Where this skill stops

| The ask | Use |
|---|---|
| USWDS markup, tokens, install, version, federal website facts | This skill |
| A custom or distinctive visual direction with no prescribed system | `frontend-design` |
| Judging a screenshot or the usability of a USWDS page | `ux-review` (load this skill too) |
| Source-level lint of UI code against general web guidelines | `web-design-guidelines` |
| A WCAG scan, keyboard pass or Section 508 report | the `accessibility` plugin |
