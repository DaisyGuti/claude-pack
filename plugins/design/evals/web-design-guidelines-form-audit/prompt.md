---
description: "Should-trigger: a request to audit markup for web interface issues."
tags: [trigger]
max_turns: 12
allowed_tools: [Skill, Read, Glob, Grep]
---

Audit this markup for UI quality issues: forms, focus, keyboard handling, anything a linter for web interfaces would flag.

```html
<div class="search" onclick="go()">
  <input name="q" placeholder="Search">
  <span class="btn" onclick="go()">Go</span>
</div>
<a href="#" onclick="openMenu()">Menu</a>
```
