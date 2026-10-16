---
description: "Should-trigger: bundle size and import style."
tags: [trigger]
max_turns: 12
allowed_tools: [Skill, Read, Glob, Grep]
---

Our React bundle is huge. I import icons like `import { Camera } from "lucide-react"` and utilities like `import { debounce } from "lodash"` all over the app. What should I change?
