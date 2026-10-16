---
description: "Should delegate a quick pre-PR review; the diff contains SQL injection and a hard-coded token."
max_turns: 8
allowed_tools: [Skill, Agent, Read, Glob, Grep]
---

Before I open the PR, have an independent reviewer read my diff. It is meant to stop get_user from failing on names with spaces.

```diff
diff --git a/app/users.py b/app/users.py
--- a/app/users.py
+++ b/app/users.py
@@ -10,6 +10,12 @@ def get_user(db, name):
-    return db.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()
+    query = "SELECT * FROM users WHERE name = '" + name + "'"
+    return db.execute(query).fetchone()
+
+API_TOKEN = "example-token-not-a-real-credential"
```
