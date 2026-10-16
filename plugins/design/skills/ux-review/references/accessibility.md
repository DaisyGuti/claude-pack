# Accessibility review

The checklists below (what a screenshot can show, color, keyboard, names and structure,
forms, size and reflow, motion, code review, grading) were written for this skill from
WCAG 2.2 and the W3C ARIA documents. Three sections are adapted from
phazurlabs/sumi (Apache-2.0, https://github.com/phazurlabs/sumi) and carry its license:
"Contrast beyond WCAG ratios (APCA)", "Cognitive and neurodiversity accommodations" and
"Testing methodology". They were modified; see [../LICENSE.txt](../LICENSE.txt).

## Contents

- [What a screenshot can and cannot show](#what-a-screenshot-can-and-cannot-show)
- [Color and contrast](#color-and-contrast)
- [Keyboard and focus](#keyboard-and-focus)
- [Names, roles, structure](#names-roles-structure)
- [Forms and errors](#forms-and-errors)
- [Size, reflow and text spacing](#size-reflow-and-text-spacing)
- [Motion, time and media](#motion-time-and-media)
- [Reviewing implementation code](#reviewing-implementation-code)
- [Grading findings](#grading-findings)
- [Contrast beyond WCAG ratios (APCA)](#contrast-beyond-wcag-ratios-apca)
- [Cognitive and neurodiversity accommodations](#cognitive-and-neurodiversity-accommodations)
- [Testing methodology](#testing-methodology)
- [Live and automated testing: when a page is running](#live-and-automated-testing-when-a-page-is-running)
- [Output shape](#output-shape)

Use this list when reviewing a design (screenshot, mockup, prototype) or UI code for accessibility. Each check names the WCAG criterion that backs it, so a finding can cite a number and a level. Work through the sections in order, skip checks that do not apply to what you were given, and keep every claim tied to evidence you actually have.

Criteria cited are from WCAG 2.2 (W3C Recommendation).

## What a screenshot can and cannot show

Judgeable from a static image:
- Contrast risk for text and for control borders and icons (estimate, then measure with sampled pixel values).
- Text size, line length and line spacing.
- Target size and the gap between neighboring targets.
- Layout, grouping, visual hierarchy, and what the eye reads first.
- Meaning carried by color alone (1.4.1), such as a red border as the only error signal.
- A focus ring, only if the capture shows one.
- A plausible reading order, inferred from layout.

Needs the live page or the code:
- Keyboard order, traps, and shortcuts (2.1.1, 2.1.2, 2.4.3).
- Accessible names, roles, and states (4.1.2), and what a screen reader announces.
- Focus management when dialogs, menus, and route changes open or close.
- Live regions and status messages (4.1.3).
- Motion, timing, autoplay, and media captions.
- Behavior at 200% text size, 400% zoom, and with changed text spacing.

Rule: label anything inferred from a picture as "unverified" and name the check that would settle it, for example "unverified: tab order, settle with a keyboard pass". A guess never goes into the report as a finding.

## Color and contrast

- Text needs 4.5:1 against its background (1.4.3, AA). Large-scale text needs 3:1. WCAG defines large-scale text as 18 point (24 CSS px), or 14 point bold (about 18.7 CSS px bold), or larger.
- Icons, input borders, checkbox and radio outlines, chart marks, and other graphics needed to understand the interface need 3:1 against adjacent colors (1.4.11, AA). Disabled and inactive components are exempt.
- Never let color be the only signal (1.4.1, A). A required field, an error, a selected tab, or a chart series needs a second cue: text, an icon, a pattern, or an underline.
- Links inside body text need a cue beyond hue, such as an underline, or 3:1 contrast against the surrounding text plus a non-color cue on hover and focus.
- Text on a gradient or photo: measure at the worst spot behind the text. Fix with a solid or semi-opaque scrim behind the text, or move the text to a calmer region.
- Check every state: hover, focus, active, visited, selected, disabled-but-readable, error, placeholder, and dark mode. Placeholder text is still text and needs 4.5:1.
- Tooltips and popovers shown on hover or focus must be dismissible without moving the pointer, hoverable, and persistent until dismissed (1.4.13, AA).
- Enhanced contrast is 7:1 for text, 4.5:1 for large text (1.4.6, AAA). Mention it as a goal for body copy; do not report its absence as a failure.
- Quick ratio: convert each sRGB channel to 0..1, linearize (c/12.92 if c <= 0.04045, else ((c+0.055)/1.055)^2.4), then L = 0.2126 R + 0.7152 G + 0.0722 B. Ratio = (L_lighter + 0.05) / (L_darker + 0.05). Browser devtools show the same number in the color picker.

## Keyboard and focus

- Every function works from the keyboard with no timing requirement (2.1.1, A). Hover-only menus, drag-only reordering, and click-only custom controls fail here.
- Focus can always leave a component with standard keys (2.1.2, A). Modal traps are fine only when Escape or a close button exits them.
- Tab order follows the visual and logical order (2.4.3, A). Watch for positive tabindex, CSS reordering (`order`, `flex-direction: row-reverse`, grid placement) that separates visual from DOM order, and off-screen content that still takes focus.
- Every focusable element shows where focus is (2.4.7, AA). Removing the default outline needs a visible replacement that has 3:1 contrast against its surroundings.
- Focus is never entirely hidden by sticky headers, cookie banners, or chat widgets (2.4.11, AA, new in 2.2). Scroll-padding on the scroller is the usual fix.
- Stretch goal: a focus indicator at least 2 CSS px thick with 3:1 contrast (2.4.13, AAA).
- A skip link, or equivalent landmarks and headings, lets users bypass repeated navigation (2.4.1, A). The skip link is visible when focused.
- Changing a control's value (select, radio, checkbox) does not submit a form or move focus on its own (3.2.1, A, On Focus; 3.2.2, A, On Input).
- Dialogs: on open, focus moves inside; Tab and Shift+Tab stay inside a modal; Escape closes; on close, focus returns to the control that opened it (pattern from the ARIA Authoring Practices modal dialog page).

## Names, roles, structure

- Every meaningful image has alt text that serves the same purpose as the image (1.1.1, A). Informative: describe the content or function. Decorative: `alt=""`. Complex (chart, diagram): short alt plus a longer text description or data table nearby.
- Icon-only buttons and links carry an accessible name (`aria-label`, visually hidden text, or an `<svg>` with `<title>` and a reference to it). 4.1.2 (A).
- When a control shows a text label, its accessible name contains that same text (2.5.3 Label in Name, A). Voice-control users say what they see.
- Link text makes sense with its context (2.4.4, A). Avoid a page full of "Read more" with nothing to tell them apart.
- Headings follow the outline of the page, with one `h1` and no skipped levels used for styling (1.3.1, A). Headings and labels describe their topic (2.4.6, AA).
- The page has a unique, descriptive `<title>` (2.4.2, A).
- Landmarks mark the regions: `header`, `nav`, `main`, `footer`, with a label when there are two of the same kind.
- Lists are `ul`/`ol`; tables with data use `th` with `scope`, and a `caption` when helpful; layout does not use tables (1.3.1, A).
- Reading order in the DOM matches meaning (1.3.2, A).
- Buttons act (submit, open, toggle); links navigate. A `<a href="#">` that runs a script is a button wearing the wrong tag.
- Custom controls expose name, role, and value, and update state attributes when state changes (4.1.2, A).
- 4.1.1 Parsing was removed in WCAG 2.2 and is no longer checked. Do not cite it. Duplicate ids still matter when a `for`, `aria-labelledby`, or `aria-describedby` reference depends on them.

## Forms and errors

- Every input has a visible, programmatically associated label (3.3.2, A; 1.3.1, A). A placeholder alone disappears on typing and cannot serve as the label.
- Common personal fields use the right `autocomplete` token (`name`, `email`, `tel`, `street-address`, `current-password`, `one-time-code`) (1.3.5, AA).
- Errors are identified in text, name the field, and say what is wrong (3.3.1, A). The message is tied to the field with `aria-describedby`, and `aria-invalid="true"` is set on it.
- Where the fix is known, the message suggests it, for example "Enter a date as DD/MM/YYYY" (3.3.3, AA).
- Submissions that move money, create legal commitments, or delete data can be reversed, are checked, or ask for confirmation (3.3.4, AA).
- A multi-step flow does not ask again for something the user already entered, and prefills or offers it for selection (3.3.7, A, new in 2.2). Exceptions: essential re-entry and security (password confirmation).
- Login does not depend on a cognitive test such as remembering a password with no way to paste or use a password manager, transcribing characters, or solving a puzzle (3.3.8, AA, new in 2.2). Allowed: paste enabled, password manager support, object recognition, a copied code.
- A repeated help mechanism (contact link, chat, phone, self-help) sits in the same relative place on each page (3.2.6, A, new in 2.2).
- Status messages that appear without moving focus (saved, 3 results found, form error summary) are announced through a live region or `role="status"` / `role="alert"` (4.1.3, A).

## Size, reflow and text spacing

- Pointer targets are at least 24x24 CSS px, or have enough spacing so a 24 px circle centered on each target does not hit another target (2.5.8, AA, new in 2.2). Exceptions: inline links in text, browser-controlled controls, and cases where the size is essential.
- Goal: 44x44 CSS px for primary touch controls (2.5.5, AAA). Report shortfalls against 44 px as Low or Medium suggestions, and shortfalls against 24 px as failures.
- Text can be resized to 200% with no loss of content or function (1.4.4, AA). Fixed-height containers and `overflow: hidden` clip text first.
- Content reflows at a 320 CSS px wide viewport (equal to 400% zoom on a 1280 px window) with no two-dimensional scrolling, except for things like data tables, maps, and code (1.4.10, AA).
- Text still works when the user sets line height 1.5, paragraph spacing 2x font size, letter spacing 0.12em, and word spacing 0.16em (1.4.12, AA). Test by applying those values in a user stylesheet or bookmarklet.
- The layout does not lock to portrait or landscape unless the task needs it (1.3.4, AA).
- Any multi-finger or path gesture (pinch, swipe, draw) has a single-tap alternative (2.5.1, A). Any drag has a click or tap alternative, such as arrow buttons or "move to" menus (2.5.7, AA, new in 2.2).
- A press does not fire its action on pointer-down unless undoable; prefer firing on release (2.5.2, A).

## Motion, time and media

- Time limits (session timeouts, auto-advancing steps) can be turned off, adjusted, or extended with at least 20 seconds of warning (2.2.1, A), with exceptions for real-time and essential limits.
- Motion that starts by itself, lasts longer than 5 seconds, and sits beside other content has a pause, stop, or hide control (2.2.2, A). Carousels are the usual offender.
- Audio that plays by itself for more than 3 seconds has a pause or volume control (1.4.2, A). Treat autoplay with sound as a defect, and autoplay video as muted, with controls.
- Nothing flashes more than three times in one second (2.3.1, A).
- Prerecorded video with speech has captions (1.2.2, A), an audio description or full text alternative (1.2.3, A), and audio description for the visuals (1.2.5, AA). Audio-only content has a transcript (1.2.1, A). Live captions: 1.2.4 (AA).
- `prefers-reduced-motion: reduce` is honored, with a gentler version that keeps the meaning, for example a fade of 150 ms in place of a slide and parallax, so state changes stay noticeable. A removed cue hides information. Related AAA criterion: 2.3.3 Animation from Interactions.

## Reviewing implementation code

Read the markup with these searches in mind: `onClick` on `div`/`span`, `role=`, `aria-`, `tabindex`, `outline`, `<img`, `<input`, `<html`.

- Native first. The W3C "Using ARIA" note states the first rule: if a native HTML element or attribute already has the semantics and behavior required, use it instead of adding a role to something else. A role is a promise of keyboard behavior (ARIA Authoring Practices, "Read Me First"), and the author has to build that behavior.
- Other Using ARIA rules: do not change native semantics unless there is no alternative; all interactive ARIA controls work with the keyboard; never put `role="presentation"` or `aria-hidden="true"` on a focusable element.
- Required attributes per role: `role="checkbox"` needs `aria-checked`; `role="tab"` needs `aria-selected` and sits in a `tablist` with `aria-controls` linking to the panel; `role="combobox"` needs `aria-expanded`.
- `aria-labelledby`, `aria-describedby`, and `aria-controls` point to ids that exist exactly once in the document.
- `tabindex` is `0` or `-1`. Any value above 0 reorders the page and is a defect.
- `outline: none` or `outline: 0` appears only beside a `:focus-visible` replacement.
- `<html lang="en">` is present and correct (3.1.1, A). Passages in another language carry their own `lang` (3.1.2, AA).
- Custom widgets (menu, tabs, combobox, listbox, dialog) follow the keyboard pattern on the matching ARIA Authoring Practices page: arrow keys inside, Tab to leave, Escape to close.
- Dynamic updates (toasts, validation summaries, counts) go into a live region that exists in the DOM before its text changes.

Before and after:

```html
<!-- Before: click handler on a div, no name, no keyboard -->
<div class="btn" onclick="save()"><svg>...</svg></div>

<!-- After: native button with a name -->
<button type="button" class="btn" onclick="save()">
  <svg aria-hidden="true" focusable="false">...</svg>
  <span class="visually-hidden">Save draft</span>
</button>
```

```css
/* Before */
button:focus { outline: none; }

/* After */
button:focus-visible { outline: 3px solid #1a56db; outline-offset: 2px; }
```

```html
<!-- Before: placeholder as label, error not tied to the field -->
<input placeholder="Email">
<span class="err">Invalid</span>

<!-- After -->
<label for="email">Email</label>
<input id="email" type="email" autocomplete="email"
       aria-invalid="true" aria-describedby="email-err">
<p id="email-err">Enter an email address like name@example.com.</p>
```

```css
/* Sticky header hides focused fields (2.4.11) */
html { scroll-padding-top: 5rem; } /* header height plus a little air */
```

```html
<!-- Status message announced without moving focus (4.1.3) -->
<div role="status" id="save-status"></div>
<script>document.getElementById('save-status').textContent = 'Draft saved';</script>
```

## Grading findings

Severity is about what a person loses.
- **Blocker:** a task cannot be completed by some group of users. Examples: a control unreachable by keyboard, a modal with a keyboard trap, a form error nobody can perceive, a login that needs a puzzle.
- **High:** the task is possible with great effort or likely to cause errors. Examples: body text at 2.5:1, no visible focus, icon buttons without names, error text not linked to its field.
- **Medium:** friction or confusion that a determined user gets past. Examples: skipped heading levels, 24 px targets with tight spacing, vague link text.
- **Low:** polish and AAA goals. Examples: 44 px target goal missed, 7:1 contrast not reached on large text.

Word each recommendation so someone can apply it without more thinking. Give the real value and the real markup.
- Good: "Body text `#8a8f98` on `#ffffff` measures 3.2:1 (1.4.3, AA). Change to `#5b616b` (6.2:1)."
- Good: "Replace `<div onclick>` on the Save control with `<button type=\"button\">` and add the visible text 'Save draft'."
- Weak: "Improve contrast." "Make it more accessible." "Add ARIA."

Each finding carries: where it is, the criterion with level, what was observed or measured, the fix, and whether it is verified or inferred.

## Contrast beyond WCAG ratios (APCA)

WCAG 2.2 ratios (4.5:1, 3:1) remain the conformance test, and every pass or fail claim
cites one. APCA (the Accessible Perceptual Contrast Algorithm) is a candidate method
under discussion for WCAG 3 and lies outside WCAG 2.2. When forward compatibility matters, report its
Lc value beside the ratio for each flagged pair:

| Use | Lc target |
|---|---|
| Body text | 75 or more |
| Large or bold text | 60 or more |
| UI components and non-text | 45 or more |
| Any visible element, absolute floor | 30 or more |

These are rules of thumb; APCA's own lookup tables vary the
target with font size and weight.

When a pair fails, give the corrected color as an exact hex value and say which ratio it
reaches. If the page uses oklch, adjust the lightness channel; if it uses a utility
class scale, map to the nearest compliant step. Also check that status and error
states, links, required fields and chart series carry a cue beyond hue, and flag
red/green pairings used for success and error, since protanopia, deuteranopia and
tritanopia each collapse some pairs.

## Cognitive and neurodiversity accommodations

- **ADHD**: no auto-playing media that can't be paused; no infinite scroll without a
  progress indicator; a confirmation step on important actions to catch an impulsive
  click; task progress saved automatically rather than lost to distraction.
- **Dyslexia**: body text 16px or larger, line-height 1.5 or more, paragraph width 80
  characters or fewer (45-75 ideal), left-aligned rather than justified (justified text
  produces uneven word spacing that's harder to track), letter-spacing 0.12em and
  word-spacing 0.16em honored when a user requests it (1.4.12 AA).
- **Autism**: predictable navigation and interaction patterns; no ambiguous or
  metaphorical UI copy; a clear statement of consequence before an action runs ("this
  sends the email to 5 people").
- **Age-related**: touch targets 44px or larger; text that can be enlarged without
  breaking layout; a clear visual line between interactive and non-interactive elements.
- **Across all of the above**: respect `prefers-reduced-motion` with an actual reduced
  experience rather than a broken one; support `forced-colors` and
  `prefers-contrast: more`; keep behavior and labeling consistent rather than novel for
  its own sake.

## Testing methodology

Automated tools (axe-core, Lighthouse, WAVE, an ESLint `jsx-a11y` gate in CI) find only
part of the real issues. Published estimates range from roughly 30% of issues to a
majority of defects by volume, depending on how they are counted; the AccessLint
methodology (see "Live and automated testing") keeps the two measures apart. The rest
needs a person: keyboard-only navigation through the whole flow, a real screen reader
pass (VoiceOver, NVDA, or TalkBack), 200% and 400% zoom, and a color-blindness
simulation. Where it's feasible, include at least one
disabled participant in usability testing rather than simulating the disability.
Simulation and lived experience find different things, and a fair rate for the
participant's time is part of doing this right.

## Live and automated testing: when a page is running

Everything above is a review from a screenshot or a code read: real, useful, and
bounded by what a static look can prove. When a live page or a running dev server is
reachable, the AccessLint plugin (MIT) goes further. It is a separate install; the
`accessibility` plugin in this marketplace names the commands. Its skills are:

- `accesslint:accessibility-scan`: an automated rule-engine scan of the live DOM.
- `accesslint:accessibility-inspect`: a hands-on keyboard and accessibility-tree pass
  through what a static engine can't decide.
- `accesslint:accessibility-audit`: a whole-site WCAG-EM conformance audit.
- `accesslint:accessibility-fix`: mechanical remediation with a baseline and verify loop.
- `accesslint:accessibility-diff`: a regression diff against uncommitted changes or a
  branch.

Reach for `accesslint:accessibility-scan` first for "is this page accessible"; use
`accesslint:accessibility-audit` only when the ask is a whole-site or whole-product
assessment. When the plugin is not installed, say what a live pass would add and keep the
finding labelled unverified.

**The evidence-basis grading those skills use is worth adopting on any review, live
tool or not.** It is sharper than "likely issue, needs verification". Tag each finding
with two things kept separate:

- **Evidence basis**: what you can actually support. **●** verified (deterministic and
  reproducible: cite the selector, the interaction, the observed fact). **◐** flagged
  (you have evidence, but the call needs a person: attach the evidence and your
  opinion, don't decide it yourself). **○** human-required (needs assistive technology
  or lived experience: name what's needed and hand it off without emulating it). When
  unsure between two grades, use the lower one.
- **Severity**: user impact, independent of evidence basis. Critical (blocks a core
  task, no workaround) / Serious (major barrier, task still possible) / Moderate
  (friction, task still completes) / Minor (polish).

A finding can be serious and ●, or serious and ◐, and those mean different things to a
reader. Collapsing them into the single Blocker/High/Medium/Low scale in "Grading
findings" loses the signal of whether you can act on it without a human re-checking.
Use the two-axis grading when a claim needs to say precisely how sure it is; the plain
scale is fine for a fast pass where that precision isn't the point. One discipline to
carry over whichever scale is in play: **a criterion nobody checked is "not exercised"
and reported as undetermined. It is never silently read as a pass.**

## Output shape

Lead with one line saying how close the page is to WCAG 2.2 AA and the single change
that matters most. Then the findings, worst first, grouped by the severity levels in
"Grading findings":

```markdown
**Where it stands:** <one sentence> Most important fix: <one change>.

**Blocker**
1. <Where> | <criterion and level> | <what was observed or measured> | <the fix, with real values or markup> | verified or inferred

**High** / **Medium** / **Low**
1. ...

**Not checked**
- <each check this review could not run from what it was given (keyboard order, screen reader output, focus behavior from a still image), so it reads as undetermined>
```

Leave out a severity heading with nothing under it. Keep "Not checked" whenever any
part of the checklist went unexercised.
