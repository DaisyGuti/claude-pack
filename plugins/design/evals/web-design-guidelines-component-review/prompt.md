---
description: "Should-trigger: source code of a component is reviewed against the fetched guidelines."
tags: [trigger]
max_turns: 12
allowed_tools: [Skill, Read, Glob, Grep]
---

Review this component's code against web interface best practices and give me findings by file and line.

```jsx
// Row.jsx
export function Row({ item, onOpen }) {
  return (
    <div className="row" onClick={() => onOpen(item.id)} style={{ outline: "none", transition: "all 0.3s" }}>
      <img src={item.thumb} />
      <input type="text" placeholder="Rename" />
      <button onClick={() => remove(item.id)}><TrashIcon /></button>
    </div>
  );
}
```
