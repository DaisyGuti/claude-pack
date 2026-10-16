---
description: "Should-trigger: sequential awaits are a data-fetching waterfall."
tags: [trigger]
max_turns: 12
allowed_tools: [Skill, Read, Glob, Grep]
---

This Next.js server component feels slow. Can you speed it up?

```tsx
export default async function Page({ params }) {
  const user = await getUser(params.id);
  const posts = await getPosts(params.id);
  const comments = await getComments(params.id);
  return <Profile user={user} posts={posts} comments={comments} />;
}
```
