---
name: web-design-guidelines
description: Reviews UI source code against Vercel's Web Interface Guidelines, fetched fresh at review time - accessibility attributes, focus states, forms, animation, typography, images, performance, navigation and URL state, touch, dark mode, i18n, hydration safety and common anti-patterns. Use when asked to review, audit or lint the code of a component, page or stylesheet for UI quality, "check my UI against best practices", "review this form", or "audit this markup", even if the user does not name the guidelines. Reads files and reports findings as file:line. Not for judging a screenshot or a running page (use ux-review), not for a WCAG conformance audit of a live site (use the accessibility plugin), and not for choosing a visual direction (use frontend-design).
argument-hint: "<file-or-glob>"
allowed-tools: Read Grep Glob WebFetch(domain:raw.githubusercontent.com)
license: MIT
metadata:
  author: vercel
  upstream: https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines
---

# Web Interface Guidelines

Review the files the user names against Vercel's Web Interface Guidelines. This skill
bundles no rules. The rules change upstream, so a copy here would go stale. Fetch them
every time.

## Steps

1. Fetch the current guidelines with WebFetch from
   `https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md`.
   The file holds every rule and the output format to use.
2. If the fetch fails, stop and say so. Do not review from memory, because a review that
   quotes rules it did not read presents recall as a check.
3. Read the files the user named. When the argument is a glob, expand it with Glob. When
   no files were named, ask which files or folder to review.
4. Check every file against every rule in the fetched guidelines.
5. Report in the format the fetched file specifies (terse `file:line` findings). Open with
   the file paths reviewed so the reader sees what was and was not covered.

## Where this skill stops

| The ask | Use |
|---|---|
| Source code of components, pages or styles | This skill |
| A screenshot, mockup, or a judgment of usability and visual craft | `ux-review` |
| A running page: scan, keyboard and screen-reader pass, WCAG audit, ACR | the `accessibility` plugin |
| A site built on the U.S. Web Design System | `uswds`, then this skill for the rest |
| Picking a visual direction for new UI | `frontend-design` |

The guidelines overlap `ux-review` and the accessibility skills on focus-visible,
reduced motion and `transition: all`. They are the only source in this plugin for forms,
URL state, i18n and hydration-safety checks.
