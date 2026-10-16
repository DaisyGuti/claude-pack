# Third-party notices

Most of this pack is original. A skill that includes or adapts another project's work
carries that project's license text in its own folder, and this file lists it.

| Skill or agent | Upstream | License | Notice file |
| --- | --- | --- | --- |
| [`core:eng`](plugins/core/skills/eng) (the review prompt behind the `reviewer` agent) | [openai/openai-cookbook](https://github.com/openai/openai-cookbook) | MIT | [`plugins/core/skills/eng/LICENSE.txt`](plugins/core/skills/eng/LICENSE.txt) |
| [`ui-design:web-design-guidelines`](plugins/ui-design/skills/web-design-guidelines) | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) at `063bee9` | MIT | [`LICENSE.txt`](plugins/ui-design/skills/web-design-guidelines/LICENSE.txt) |
| [`ui-design:composition-patterns`](plugins/ui-design/skills/composition-patterns) | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) at `063bee9` | MIT | [`LICENSE.txt`](plugins/ui-design/skills/composition-patterns/LICENSE.txt) |
| [`ui-design:react-best-practices`](plugins/ui-design/skills/react-best-practices) | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) at `063bee9` | MIT | [`LICENSE.txt`](plugins/ui-design/skills/react-best-practices/LICENSE.txt) |
| [`ui-design:react-native-skills`](plugins/ui-design/skills/react-native-skills) | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) at `063bee9` | MIT | [`LICENSE.txt`](plugins/ui-design/skills/react-native-skills/LICENSE.txt) |
| [`ui-design:ux-review`](plugins/ui-design/skills/ux-review) (two reference files, partly) | [phazurlabs/sumi](https://github.com/phazurlabs/sumi) | Apache-2.0 | [`LICENSE.txt`](plugins/ui-design/skills/ux-review/LICENSE.txt) |

## Notes

- **openai/openai-cookbook.** The `reviewer` agent
  ([`plugins/core/agents/reviewer.md`](plugins/core/agents/reviewer.md)) adapts the review
  prompt and the findings shape from the cookbook's code-review example. The text was
  rewritten for Claude Code; the notice file sits in the `eng` skill folder and names the
  agent it covers.
- **vercel-labs/agent-skills.** Four skills come from this repository at commit `063bee9`.
  The repository has no LICENSE file; its README states "License: MIT", and each skill
  declares `license: MIT` in its own header. Each `LICENSE.txt` reuses the copyright line of
  the sibling repository [vercel-labs/web-interface-guidelines](https://github.com/vercel-labs/web-interface-guidelines),
  which carries a LICENSE file. `web-design-guidelines` bundles no rules: it fetches the
  current guidelines when it runs.
- **phazurlabs/sumi.** In `ux-review`, `references/critique-protocol.md` and three sections
  of `references/accessibility.md` are adapted from sumi's commands and skills. The files
  were modified; the rest of the skill was written for this pack.
- **CIS Google Cloud Platform Foundation Benchmark IDs, via Prowler.** The recommendation
  IDs and titles in
  [`plugins/secure-build/skills/gcp-review/references/cis-gcp-map.json`](plugins/secure-build/skills/gcp-review/references/cis-gcp-map.json)
  were taken from the compliance listing `prowler/compliance/gcp/cis_5.0_gcp.json` in
  [prowler-cloud/prowler](https://github.com/prowler-cloud/prowler) (Apache-2.0), read on
  2026-10-16. The CIS document itself was not read. Every report from the skill tells the
  reader to confirm each ID against the benchmark edition their team holds.
- **ITI VPAT 2.5Rev wording.** `accessibility:section-508-report` bundles the template's
  own wording and criterion rows in
  [`plugins/accessibility/skills/section-508-report/data/vpat-text.json`](plugins/accessibility/skills/section-508-report/data/vpat-text.json)
  so a report follows the template. ITI's reuse terms were not checked when this pack was
  assembled. Confirm them before sharing the pack outside the team.

## Recommended plugins from other authors

These are installed from their own marketplaces and are not copied into this repository.
The README lists the commands.

| Plugin | Author | Why it is not copied |
| --- | --- | --- |
| AccessLint (WCAG 2.2 scan, inspect, audit, fix, diff) | [accesslint/skills](https://github.com/accesslint/skills) | Ships its own Claude Code marketplace |
| Typography | [bencium/bencium-marketplace](https://github.com/bencium/bencium-marketplace) | Ships its own Claude Code marketplace |
| Official Anthropic plugins (`code-review`, `claude-security` and others) | [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) | Maintained by Anthropic |
