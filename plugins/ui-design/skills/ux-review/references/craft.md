# Visual craft rules

Use this file to answer one question about a UI: why does it look generic, templated, or machine-made, and what exactly changes that? It covers pixel, token, and CSS-property decisions. Flow, wording, and usability belong to other review passes. A reviewer applies it to a stylesheet, component code, or a screenshot. When building new UI, apply the rules silently and produce the considered version first.

Each rule has a symptom (what the reviewer sees), the reason it reads as default, and a fix with real values. Values are starting points that suit most interfaces; adjust to the product's existing tokens when it has them.

## Contents

- [Color and surfaces](#color-and-surfaces)
- [Type](#type)
- [Space and layout](#space-and-layout)
- [Elevation and borders](#elevation-and-borders)
- [Component states](#component-states)
- [Motion](#motion)
- [Content realism](#content-realism)
- [Judging from a screenshot](#judging-from-a-screenshot)
- [Exceptions](#exceptions)
- [Reporting](#reporting)

## Color and surfaces

**1. A saturated blue-to-purple gradient, or any gradient on a plain surface.**
- Why it reads as default: it is the first thing every template and generator reaches for, and it carries no brand information.
- Fix: a flat surface with one accent used sparingly. Page `#fafaf9`, card `#ffffff`, text `#1c1917`, accent one hue only, for example `#0f766e`. If a gradient stays, keep both stops within 15 degrees of hue and 10% of lightness.

**2. Pure black text on pure white, or gray that is a flat `#888`.**
- Why: unadjusted extremes are what appears when nobody picked a value.
- Fix: text `#1c1917` on `#fafaf9`; secondary text `#57534e`; tertiary `#78716c` (still 4.5:1 on white). Tint grays toward the brand hue by 2 to 4% saturation so they sit with the accent.

**3. Palette with no role structure: five bright colors of equal weight.**
- Why: nothing says which color means action, which means status, which is chrome.
- Fix: one neutral ramp (9 steps), one accent, and three status colors (success `#15803d`, warning `#b45309`, danger `#b91c1c`) used only for status. Buttons use the accent only.

**4. Dark mode made by inverting.**
- Why: pure inverse gives `#000` backgrounds with glaring `#fff` text and unchanged shadows.
- Fix: background `#0c0a09`, raised surface `#1c1917`, text `#e7e5e4`. Lighter surface means higher elevation. Lower accent saturation by about 10 to 15%.

## Type

**5. One weight and one size for everything, with hierarchy made only from size.**
- Why: size alone flattens quickly; considered interfaces also vary weight, color, and spacing.
- Fix: a scale of 12, 14, 16, 20, 24, 32, 44 px. Body 16 px at weight 400; labels 14 px at 500; headings 600 or 700 with `letter-spacing: -0.02em` above 28 px. Body line height 1.5 to 1.6, headings 1.1 to 1.25.

**6. System default font stack on a page that otherwise has a point of view, or three or more families.**
- Why: type is the largest part of most interfaces, and the default stack carries no identity.
- Fix: one family with a real weight range, or one text face plus one display face. Add `font-optical-sizing: auto`, and `font-variant-numeric: tabular-nums` for tables, prices, and counters so digits align.

**7. Long lines and wide centered paragraphs.**
- Fix: `max-width: 65ch` for reading text; left-align multi-line text. Center alignment is for one to three lines.

**8. Uppercase micro-labels everywhere.**
- Fix: reserve uppercase for one tier (section eyebrows), at 12 px, `letter-spacing: 0.06em`, weight 600. Sentence case elsewhere.

## Space and layout

**9. Padding and gaps that are arbitrary numbers (13px, 22px, 37px).**
- Why: inconsistent spacing is the loudest sign no system exists.
- Fix: a 4 px base with steps 4, 8, 12, 16, 24, 32, 48, 64, 96. Inside a component use 8 to 16; between components 24 to 32; between page sections 64 to 96.

**10. Everything the same distance apart.**
- Why: uniform spacing hides grouping.
- Fix: related items closer than unrelated ones. A label sits 4 to 6 px above its field, fields 16 px apart, form groups 32 px apart. The gap around a group is at least double the gap inside it.

**11. Three equal cards in a row, each with an icon on top, a heading, and two lines of text.**
- Why: this is the stock features layout.
- Fix: break the symmetry. Make one item larger (`grid-template-columns: 2fr 1fr 1fr`), or turn the list into a two-column row layout with text beside the visual, or use a table when the content is comparative.

**12. Content centered at a fixed 1200 px with nothing to anchor it.**
- Fix: pick a grid (12 columns, 24 px gutters) and align headings, images, and text edges to it. Let one element break the container edge on purpose.

## Elevation and borders

**13. Heavy `box-shadow: 0 4px 12px rgba(0,0,0,0.3)` on every card.**
- Fix: layered, low-opacity shadows: `0 1px 2px rgba(28,25,23,.06), 0 4px 12px rgba(28,25,23,.06)`. Use shadow on one level of the hierarchy (raised or floating) and a 1 px border `#e7e5e4` on the rest.

**14. Border radius that varies by accident, or 16 px+ radius on everything.**
- Fix: pick two values, for example 6 px for controls and 12 px for cards, and nest correctly: inner radius = outer radius minus the padding between them. Pills (`9999px`) only for tags and toggles.

**15. Gray 1 px borders around everything and also dividers between every row.**
- Fix: choose one of border, background tint, or space to separate each pair of regions. A background step of `#f5f5f4` separates sections with no line at all.

## Component states

**16. Buttons with one state.**
- Why: a static button feels dead; many generated UIs ship only the resting look.
- Fix: define every state. Hover: darken by 6 to 8% lightness. Active: darken a further 4% and `transform: translateY(1px)`. Focus: `outline: 2px solid #0f766e; outline-offset: 2px` on `:focus-visible`. Disabled: `opacity: .5; cursor: not-allowed`, with the label still readable.

**17. Primary styling on every button.**
- Fix: one primary (filled accent) per view. Secondary has a 1 px border and transparent fill; tertiary is text only. Touch targets at least 40 px tall, with 12 to 20 px horizontal padding.

**18. Inputs that look like plain boxes with no focus change.**
- Fix: height 40 px, padding `0 12px`, 1 px border `#d6d3d1`, radius matching buttons. On focus change border to the accent and add `box-shadow: 0 0 0 3px rgba(15,118,110,.2)`. Error: border `#b91c1c` and a text message below.

**19. Empty, loading, and error views left blank.**
- Fix: skeleton blocks (`background: #e7e5e4`, slow 1.4 s shimmer) for loading; for empty, a one-line explanation and one action; for error, the cause and a retry.

## Motion

**20. Everything animates at `transition: all 0.3s ease`, or nothing moves.**
- Why: `all` animates layout properties and the same curve everywhere feels mechanical.
- Fix: transition only `opacity`, `transform`, `background-color`, `border-color`, `box-shadow`. Durations: 100 to 150 ms for hover and press, 200 to 250 ms for menus and dialogs, up to 400 ms for large panels. Use `cubic-bezier(.2, 0, 0, 1)` for entrances and `cubic-bezier(.4, 0, 1, 1)` for exits. Wrap non-essential motion in `@media (prefers-reduced-motion: no-preference)`.

## Content realism

**21. Placeholder content: "Lorem ipsum", "John Doe", "Feature One", round numbers like 1,000 and 50%.**
- Why: invented neutral content makes every screen look like a template.
- Fix: write real labels, plausible names, uneven numbers (1,284; 47.3%), and realistic lengths including a long name that wraps. Use a real photo or an illustration in one consistent style; avoid stock-icon sets mixed from several families (match stroke width, 1.5 px or 2 px, throughout).

## Judging from a screenshot

From an image you can judge: palette and role structure (1 to 4), type hierarchy and line length (5, 7, 8), spacing rhythm and grouping (9, 10), card symmetry (11), shadow and radius weight (13 to 15), empty or placeholder content (21).

Mark these "verify in code": exact hex and px values, spacing on a 4 px grid, font family and optical sizing (6), hover, active, focus, and disabled states (16, 18), skeleton and error views (19), transition properties and durations (20), dark-mode behavior (4), nested radius (14). A still image shows one state of one viewport.

## Exceptions

- A gradient is fine when it is the brand (a logo gradient, a data-viz ramp) or serves a hero image as a legibility scrim.
- A three-card row is correct when the three items are truly parallel and equal, such as pricing tiers.
- System fonts suit dense tools and internal software where speed and native feel matter most.
- Heavy shadows and uppercase labels suit some brands. Check them against the product's stated style before flagging.
- Where a design system already defines tokens, its values win over the numbers above.

## Reporting

- Start with a one-line verdict: how templated the UI reads and the main reason.
- List only the rules that are violated, each as: rule number, where it shows, the fix with values.
- Give at most three priority fixes, ordered by how much of the screen they change.
- Skip rules that pass. A short list is the correct result for a UI that is already considered.
