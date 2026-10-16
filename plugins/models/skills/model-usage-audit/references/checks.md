# Checks for each call path

Run these against every call path, after reading the code behind the inventory hits. A call path
is one place in the product where a model is called, together with what feeds it and what is
done with the answer. Each check gives what to look for, why it matters, and the usual fix.
Cite `file:line` for every finding. A hit from the inventory script is a lead until the code
confirms it.

## Contents

- Severity scale
- 1. Model ids
- 2. Request parameters
- 3. Limits, timeouts, retries, streaming
- 4. Prompt caching and batching
- 5. Responses, refusals and errors
- 6. Data sent to the model
- 7. Where the data goes
- 8. Secrets
- 9. Evals
- 10. Cost per call path
- 11. Resilience and observability

## Severity scale

| Level | Meaning |
|---|---|
| Critical | Broken or exposed now: a live key in a tracked file, a retired model id on a production path |
| High | Will break or leak soon, or a gap on a user-facing path: a model retiring within about 90 days, no timeout on a request a user waits on, sensitive data sent to a route with no authorization evidence |
| Medium | Money or reliability left on the table: no prompt caching on a large repeated prefix, floating alias in production, missing eval |
| Low | Hygiene: scattered model ids, missing request-id logging |

The 90-day window is a working default for planning a migration. Adjust it if the team's
release cycle is longer.

## 1. Model ids

- **Retired or deprecated.** The inventory lists a lifecycle fact for each id found in the
  provider's page. Retired: Critical on a live path. Deprecated with a date: High inside the
  window, Medium outside it. Give the replacement the provider names, and note that the
  replacement can have different parameters (check section 2).
- **Floating or preview ids in production.** A `-latest` alias moves without a code change. A
  preview or experimental id can change or disappear on short notice and is often excluded from
  agreements and authorizations. Pin to a specific id and record why.
- **Wrong id form for the platform.** The same model is spelled differently per platform: the
  bare id on the Claude API and Google Cloud for current models, an `@date` suffix for older
  ones on Google Cloud, and an `anthropic.` prefix (plus a region prefix on cross-region
  profiles) on Bedrock. Compare the id in code with the platform's table in the models
  overview.
- **Ids scattered through the code.** More than one place that names a model makes upgrades
  and audits slow. Fix: one config entry per role ("summarizer", "reviewer") that code
  references.
- **Tier does not match the work.** A top-tier model on extraction, classification or routing.
  Use the `model-recommender` skill on the path; report it as Medium with a rough cost figure.
- **Gateways and wrappers.** If the code calls a model through LiteLLM, LangChain, LlamaIndex
  or an internal gateway, the id in the code may be mapped to a different model elsewhere.
  Find the mapping file or ask where it lives, and say what is unchecked.

## 2. Request parameters

Newer models reject some parameters that older ones accepted, and a code path often survives
only because it still targets an older model. For each model id in use, and for the model the
team plans to move to, fetch that model's migration page from the models overview and compare:

- Sampling parameters (`temperature`, `top_p`, `top_k`) that return an error on newer models.
- Manual thinking budgets (`budget_tokens`) and `thinking` settings the model rejects.
- A prefilled assistant message at the end of `messages`.
- Forced tool choice (`tool_choice` of type `any` or `tool`).
- Parameters moved under `output_config` (effort, structured output format).
- Tool versions (web search, web fetch, code execution, computer use) that changed.

Report the parameter, the line, the models it fails on, and the fix. Mark it High if the path
targets one of those models today.

## 3. Limits, timeouts, retries, streaming

- **`max_tokens`.** Too low truncates the answer and the stop reason says `max_tokens`. With
  thinking on, thinking tokens count against the limit. Check that the code handles the
  truncation case, and that the limit fits the longest expected answer.
- **Timeouts.** Confirm the SDK's default in its README and compare with the path. A request a
  user is waiting on needs a timeout that matches the product, and long outputs need streaming
  so the connection does not sit idle until a proxy cuts it.
- **Retries.** The Anthropic SDKs retry connection errors, 408, 409, 429 and 5xx a small number
  of times by default. Custom retry loops wrapped around an SDK call multiply attempts; a
  worst case is attempts times attempts, each waiting the full timeout. Look for backoff with
  jitter and for respect of a `retry-after` header on 429.
- **Streaming.** Required in practice for very large `max_tokens`. Check that the stream's end
  state (stop reason, final usage) is read and not dropped.
- **Concurrency and rate limits.** A batch job that fans out without a cap meets 429s. Look for a
  concurrency limit and for a queue.
- **Side effects.** A retry after a timeout can repeat a tool action that already ran. Check that
  tool actions are idempotent or guarded.

## 4. Prompt caching and batching

- **Caching.** Large static prefixes (system prompt, tool definitions, reference documents)
  that repeat across calls are the case for prompt caching. The minimum cacheable prefix
  depends on the model; read it from the prompt-caching page. Check `cache_control` or the
  provider's equivalent, then check that a cache read is actually reported in the usage fields
  the code logs. A zero cache-read count across repeated calls points to something that changes
  the prefix each time, such as a timestamp or request id in the system prompt, unsorted JSON,
  or a tool list that varies.
- **Batching.** Work that can wait is a candidate for the provider's batch interface at a
  discount. Check availability on the platform the code uses; some platforms do not offer it.
- **Features the platform lacks.** Code that uses a feature the platform does not support (for
  example a file upload API or a batch interface on a platform that omits it) fails at run
  time. Compare against the platform's "features not supported" list.

## 5. Responses, refusals and errors

- The code reads the stop reason before using the content: `max_tokens`, `refusal`,
  `pause_turn` and tool-use stops each need a branch.
- A refusal on a model with safety classifiers needs a defined outcome (message the user, retry
  on a fallback model, log with category). Some platforms need the client-side fallback
  pattern.
- Output that downstream code parses is validated: structured outputs or a schema, with a
  retry-once path. Parsing free text with a regex is a Medium finding.
- Errors are caught by type (rate limit, connection, bad request, authentication). One broad
  catch hides the difference between a retryable and a permanent failure.
- The request id from the response is logged with errors, which the provider asks for in
  support cases.
- An answer that drives a consequential action (access, money, a record change) has a human or
  deterministic check in between.

## 6. Data sent to the model

Read the code that builds each prompt, and list the fields that enter it.

- **Minimum necessary.** Does the prompt carry whole records when a few fields would do?
- **Sensitive classes.** Personal data (names, emails, government ids, health, financial),
  credentials, and any data class the team's agreements restrict (for example controlled
  unclassified information). The inventory's word hints are leads only; the code decides.
- **Redaction before send.** Is there a step that removes or tokenizes sensitive fields? Is it
  tested?
- **Logging.** Do logs, traces or analytics store the full prompt or response? A third-party
  tracing or observability service that receives prompts is another recipient to list under
  section 7. Provider documentation can recommend keeping activity logs for misuse
  investigation; whether to keep full prompts is a decision for the data owner, so list both
  sides in the finding.
- **Stores.** Prompts or answers cached, embedded or saved: where, how long, who can read them.
- **Untrusted content.** Web pages, uploads, emails or tickets placed into a prompt that also
  controls tools. The risk is an instruction hidden in that content. Check that tools run with
  least privilege and that write or send actions need approval.
- **Test and eval data.** Real records in fixtures or eval sets are a finding.

## 7. Where the data goes

For each route (provider, service, region, endpoint type) record:

| Item | Source |
|---|---|
| Provider and cloud service | Code and config |
| Region or endpoint type (global, multi-region, regional) | Code and config; the platform page explains what each guarantees |
| Retention and training use for API data | The provider's data governance page, fetched today |
| Authorization claimed, by whom, at what level, with a source and date | See sources-to-fetch.md |
| Authorization confirmed for this service, model and region | FedRAMP Marketplace or the cloud vendor's scope page, fetched today |

State only what a fetched page says, with its URL and the date. Where nothing was found, write
"no evidence found" and name what to ask the vendor. Never write that a route is compliant or
authorized; list evidence and gaps and leave the decision to the person who holds that
authority.

A global endpoint can route a request to any region the provider uses. A product with a
residency requirement needs a regional or multi-region endpoint, and the platform page lists
price premiums and model support for each.

## 8. Secrets

- Keys in source, config, notebooks, CI files or container images: Critical when the key looks
  live. The inventory shows kind and file:line and hides the value. Tell the owner to rotate
  the key; deleting it from the file leaves it in history.
- A tracked `.env` file.
- A key in client-side code (browser, mobile app): any user can read it. Route calls through a
  server.
- On Google Cloud, application default credentials or a service account with a narrow role
  avoid long-lived keys. On AWS, an IAM role does the same.
- One shared key for every service and environment. Separate keys allow separate limits and
  revocation.
- Keys written to logs, error messages or traces.

## 9. Evals

- Is there a test set for each call path, with expected behavior and a pass check?
- Does it run before a prompt change, a model change or a migration off a retiring model?
- Does it contain realistic hard cases, including refusals and malformed input?
- Is the data safe to store (no real personal or controlled data)?
- Mocked-model unit tests check plumbing and say nothing about answer quality; note which kind
  exists.
- For building one, the `claude-api` skill has a `build-eval` subcommand.

## 10. Cost per call path

Estimate per path, and show the arithmetic:

1. Input tokens per call, split into the cached static prefix and the varying part. Measure
   with the provider's token-counting endpoint or the usage fields in logs; a character count
   is a rough fallback and the ratio differs by model.
2. Output tokens per call, including thinking tokens, which are billed as output.
3. Calls per day from logs, traffic data, or the user's estimate (label it as an estimate).
4. Price per million tokens for the model and route, from the fetched page, including cache
   read and write rates and any endpoint premium.
5. Cost per call and per month: `(uncached input x input price + cached input x cache-read
   price + cache writes x write price + output x output price) x calls`.

Rank paths by monthly cost, then list the cheapest changes first: caching, a smaller model on
mechanical paths, batching, a lower max output.

## 11. Resilience and observability

- What happens to the user when the provider is down or slow: queue, fallback model, degraded
  mode, or an error page.
- A model retirement date turns into a calendar item with an owner.
- Per-path metrics: calls, tokens, latency, error rate, refusal rate, cost, with the model id as
  a label so a model change shows up.
- Alerts on spend and on error spikes.
