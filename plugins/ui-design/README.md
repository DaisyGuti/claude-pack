# ui-design

A UI/UX agent and the design skills a team building a government web product uses.

| Piece | What it does |
|---|---|
| `ui-ux` agent | Renders a page in a real browser, looks at the screenshots, reviews it and makes the fixes. Delegate to it after a UI change or when asked whether something looks right. |
| `ux-review` | Judges an existing design (screenshot, mockup, flow, component) for usability, accessibility and visual craft. Includes a scored critique protocol. |
| `uswds` | Builds or reviews a UI with the U.S. Web Design System: fetches the current version, component pages and federal website standards when it runs, and checks templates for class names the stylesheet does not define. |
| `web-design-guidelines` | Reviews UI source code against Vercel's Web Interface Guidelines, fetched fresh each time. |
| `composition-patterns` | Vercel's React composition rules (compound components, state in providers, explicit variants). |
| `react-best-practices` | Vercel's React and Next.js performance rules, ranked by impact. |
| `react-native-skills` | Vercel's React Native and Expo rules: list performance, animation, navigation, UI patterns, state and monorepo setup. |

## Install these alongside

Official, for building new UI with a distinctive look (`frontend-design` is not repackaged here):

```sh
claude plugin install frontend-design@claude-plugins-official
```

Typography rules for generated UI text (curly quotes, dashes, spacing). The upstream ships its own
Claude Code marketplace, so it is installed from there instead of being copied here:

```sh
claude plugin marketplace add bencium/bencium-marketplace
claude plugin install typography@bencium-marketplace
```

For a product built on USWDS, the design system sets the type scale and the brand, so skip the
same author's `bencium-innovative-ux-designer` (it invents a new visual identity).

Accessibility testing of a running page lives in the `accessibility` plugin of this marketplace,
which names the AccessLint install.

## Third-party material

| Skill | Upstream | License | Notice |
|---|---|---|---|
| `web-design-guidelines`, `composition-patterns`, `react-best-practices`, `react-native-skills` | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) at 063bee9 | MIT | `LICENSE.txt` in each skill folder |
| `ux-review` (parts of two reference files) | [phazurlabs/sumi](https://github.com/phazurlabs/sumi) | Apache-2.0 | `skills/ux-review/LICENSE.txt` |
