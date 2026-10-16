# Sources to fetch during an audit

Fetch each page the audit leans on, with WebFetch, on the day of the audit, and record the URL
and the date in the report. Add `.md` to a platform.claude.com URL to get raw markdown. If a
page cannot be fetched, the report says which fact is unchecked. Nothing below is a substitute
for reading the page.

Google's pages and Anthropic's now call Vertex AI "Agent Platform" in places. Search for both
names when a page seems missing.

## Contents

- Model lifecycle (deprecation and retirement)
- Prices
- Platform behavior (regions, features, retention)
- Authorization status
- Writing the deprecations file for the inventory script

## Model lifecycle (deprecation and retirement)

| Provider and route | Page |
|---|---|
| Anthropic, Claude API (also Claude Platform on AWS and Microsoft Foundry) | https://platform.claude.com/docs/en/about-claude/model-deprecations |
| Claude on Google Cloud | The partner-models page for Claude, which sets its own dates: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/claude |
| Claude on Amazon Bedrock | https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle.html |
| Google Gemini on Google Cloud | https://cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions and https://cloud.google.com/vertex-ai/generative-ai/docs/deprecations |
| OpenAI | https://platform.openai.com/docs/deprecations |
| Anything else (LangChain, LlamaIndex, LiteLLM wrappers) | The wrapper only forwards a model id. Audit the provider the id belongs to. |

Partner platforms set their own retirement dates, so a model's date on the Claude API page can
differ from the date on Google Cloud or Bedrock. Use the page for the route the code calls.

## Prices

- Claude API list prices: https://platform.claude.com/docs/en/about-claude/pricing
- Google Cloud partner-model prices: https://cloud.google.com/vertex-ai/generative-ai/pricing
- Amazon Bedrock prices: https://aws.amazon.com/bedrock/pricing/
- OpenAI and Gemini prices: the provider's own pricing page; record the URL used.

The pricing page lists regional and multi-region endpoint premiums, batch discounts, cache-read
and cache-write rates, and long-prompt surcharges. Read the rows for the models the code uses.

## Platform behavior (regions, features, retention)

- Models overview, with the model id for each platform and default effort:
  https://platform.claude.com/docs/en/models/overview
- Migration guide, for parameters a newer model rejects:
  https://platform.claude.com/docs/en/about-claude/models/migration-guide
- Claude on Google Cloud, covering model ids, endpoint types, unsupported features and activity
  logging: https://platform.claude.com/docs/en/build-with-claude/claude-on-vertex-ai
- Claude on Amazon Bedrock: https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock
- Data residency on the Claude API: https://platform.claude.com/docs/en/manage-claude/data-residency
- Google Cloud data governance for generative AI:
  https://cloud.google.com/vertex-ai/generative-ai/docs/data-governance
- Google Cloud model locations: https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations

## Authorization status

An authorization belongs to a specific service, inside a specific boundary, at a specific
level, as of a date. Record all four for each route the code uses, and quote the page. Do not
infer one from a vendor blog post or from a model name.

| Question | Where to look |
|---|---|
| Is the cloud service in a FedRAMP authorization, and at which level | FedRAMP Marketplace, https://marketplace.fedramp.gov (search the provider; open the product's page and read its service scope) |
| Which Google Cloud services are covered | https://cloud.google.com/security/compliance/fedramp |
| DoD impact levels for Google Cloud | https://cloud.google.com/security/compliance/disa |
| Which products can run inside an Assured Workloads control package | https://cloud.google.com/assured-workloads/docs/supported-products |
| Which AWS services are in scope | https://aws.amazon.com/compliance/services-in-scope/FedRAMP/ |
| Anthropic's own compliance documents | https://trust.anthropic.com |
| Any other provider | The provider's trust or compliance page; record the URL used |

Anthropic and cloud vendors have published announcements that name a model on a platform at a
FedRAMP or DoD level. Treat an announcement as a lead. Then confirm on the FedRAMP Marketplace
or the cloud vendor's service-scope page that the exact service, model family and region the
code calls fall inside the authorization, and note any model or feature the page excludes.
Check the model's release status (preview, limited availability or generally available) against what the page lists.

When a route has no confirmed authorization, write "no authorization evidence found for this
service, model and region on <date>" and list what the compliance owner should ask the vendor.
The audit never states that a system is compliant, authorized or ready for an authorization
decision. A person with the authority decides.

## Writing the deprecations file for the inventory script

After reading the lifecycle pages, write a small JSON file in a temporary folder and pass it to
the script with `--deprecations`:

```json
{
  "as_of": "<today's date>",
  "models": {
    "<model id as the provider lists it>": {
      "status": "deprecated",
      "retires": "<date from the page>",
      "replacement": "<model id the page recommends>",
      "source": "<URL of the page>"
    }
  }
}
```

List every model on those pages that is deprecated, retired or has a retirement date, using the
spelling the page uses. The script also matches the Vertex `@date` form and the Bedrock
`anthropic.` and region prefixes against these keys.
