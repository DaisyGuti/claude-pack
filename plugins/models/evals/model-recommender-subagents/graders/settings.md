---
type: llm
---
PASS if the reply tells the user to set a smaller model (Haiku or Sonnet class) and a low or medium effort on those agents, naming the agent file's `model` and `effort` frontmatter fields or the per-invocation model parameter, explains that an unset agent model inherits the session's model, and gives a small test to confirm quality holds.
FAIL if it only says "use a cheaper model" with no way to apply it, or never mentions how a subagent's model is chosen.
