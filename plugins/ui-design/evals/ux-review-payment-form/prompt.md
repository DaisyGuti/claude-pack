---
description: "Should-trigger: an existing form is reviewed for usability and craft."
tags: [trigger]
max_turns: 12
allowed_tools: [Skill, Read, Glob, Grep]
---

Here is the HTML for the payment step of our permit application. Is it usable? Tell me what to fix before we ship it.

```html
<form class="pay">
  <h2>Pay your permit fee</h2>
  <input placeholder="Card number" style="color:#aaa">
  <input placeholder="Expiry">
  <p style="color:#bbb;font-size:11px">Fees are non-refundable once a permit is issued.</p>
  <button class="btn-primary">Submit</button>
  <button class="btn-primary">Continue</button>
  <button class="icon-only"><svg><use href="#trash"/></svg></button>
</form>
```
