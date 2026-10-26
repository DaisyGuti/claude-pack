---
description: >-
  Should trigger and turn a prompt that names large documents into a chain that runs from one
  paste, without opening them, guessing what they hold, or leaving a public source unfetched
tags: [trigger, rewrite, inputs]
max_turns: 12
timeout_seconds: 420
allowed_tools: [Read, Glob, Grep, Skill, WebFetch]
---
Can you optimize this prompt before I run it? It keeps failing.

I want to scrutinize and analyze this plan and give fixes with sources: https://wiki.example.com/prepare-phase-prd. The PR is here: https://github.com/example-org/example-app/pull/42. Our product plans are in docs/plans/README.md. We need to follow the process in docs/standards/process-instruction.pdf and the control catalog in docs/standards/control-catalog.pdf, and import the controls in docs/standards/controls-workbook.xls. Impact levels have to follow FIPS 199. Pay close attention to section 3. First give me the edits with sources, then once I approve we'll add them as comments on the page.
