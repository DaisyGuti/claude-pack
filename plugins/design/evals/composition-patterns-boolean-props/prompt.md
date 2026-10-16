---
description: "Should-trigger: boolean prop proliferation is the core composition problem."
tags: [trigger]
max_turns: 12
allowed_tools: [Skill, Read, Glob, Grep]
---

Our Button component has grown isLoading, isPrimary, isLarge, hasLeftIcon, hasRightIcon and isRounded props, and every new design adds another. How should I restructure it so it stops growing?

```tsx
function Button({ isLoading, isPrimary, isLarge, hasLeftIcon, hasRightIcon, isRounded, children }: Props) {
  /* 90 lines of conditional class names */
}
```
