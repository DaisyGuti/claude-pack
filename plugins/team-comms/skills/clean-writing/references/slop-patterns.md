# Slop patterns

What AI-flavored writing does, with a rewrite for each. Read it for the slop pass.

## Failure modes

- **Mannered prose:** flourishes and metaphors where plain words work.
- **Verbs given to objects:** "the row carries" becomes "the row says". "The complaint
  fixes" becomes "fixing the complaint resolves".
- **Padding:** a five-word answer inflated into a paragraph to feel complete.
- **Buried lede:** "Of the four findings, one is only half-right, and that's the half that
  matters." Write: "Important qualifier: X is only half right."
- **Magic adverbs and adjectives:** `genuinely`, `quietly`, `deeply`. Delete them.
- **Pompous verbs:** `serves`, `stands`, `marks`, `carries`, `pays down`. Use "is", "are",
  "has".
- **Coined phrases** used without explanation, or explained far from first use.
- **Teasers:** "My recommendation: option 3, unless one question is yes." Write "I
  recommend option 3, unless X."
- **Inflated reasons:** an obvious "because" chain ("We need to open the door to leave").
- **Citation chains** in place of the conclusion. Write "The fourth row was wrong."
- **Saying what is absent** in place of the limit. Write "This document assesses one of two
  deployments."
- **Negatives as flourishes:** `stored nowhere` becomes `not stored`.
- **Contrast for effect:** `not just X, it is Y` and `X, not Y`. Say what the thing is.
- **Redundancy:** one fact in the heading, the description and the table.
- **Back-end details** the reader cannot act on: "the database connection couldn't be
  loaded" becomes "An error occurred. Try again."
- **Ad-libbed copy:** prose that explains an obvious mechanism, synonym pairs ("ingest as
  well as read"), consequences that will not happen, obvious next steps. "Upload your files
  here to continue." is enough.
- **Vague attribution:** "studies show", "experts agree". Name the source or drop the claim.
- **Decorative triplets** and false ranges ("from X to Y" with no real limits).
- **Formatting habits:** bold as decoration, bold lead-ins on every bullet, emoji as
  structure, a heading over one or two sentences.
- **Chat leftovers:** "Great question", "I hope this helps", "Let me know". Delete them.
- **To-dos** that open with anything other than the need. Write "We need a statement from
  the enclave operator about what encrypts the database."

## Before and after

| Before | After |
| --- | --- |
| The credential rows rest on the built artifact rather than on reading the build script, because a guard that never fires looks identical to one that has nothing to catch. | The credential check reads the built artifact. It does not read the build script. |
| Two deployments exist and only one of them is assessed here | This document assesses one of two deployments. |
| A row whose control lives elsewhere names the system that supplies it | Each row names its control's system. |
| A figure can be compared with the same figure last month. That is what run_line being rows rather than one stored document buys. | Figures can be compared historically. |
| One thing worth knowing about the shape of what is left. | One final note: (or nothing) |
| The marking a build carries was read at render time and stored nowhere | We were not storing the marking a build had when it was run. |
| What a run proves here is bounded, and the bound is worth stating | What we can prove with the run is limited. |
| The cost is that nothing in the repository records the registered addresses; the README entry is what pays that down. | The registered addresses are in the README. |

## Word swaps

Delete a word that carries no fact. Otherwise swap it.

| Word | Write |
| --- | --- |
| `leverage`, `utilize`, `harness` | use |
| `in order to`, `prior to`, `in the event that`, `due to the fact that` | to, before, if, because |
| `it is worth noting that`, `it's important to`, `notably` | delete, then state the fact |
| `simply`, `just`, `easily`, `seamless`, `effortlessly` | delete |
| `robust`, `powerful`, `comprehensive`, `performant` | delete, or give the measured property |
| `enables you to`, `allows you to` | you can |
| `is designed to`, `aims to` | delete, then say what it does |
| `functionality` | function, feature |
| `facilitate`, `foster`, `empower`, `bolster` | help, support, let |
| `delve into`, `dive into` | read, examine |
| `streamline`, `enhance`, `elevate` | simplify, improve, increase |
| `crucial`, `pivotal`, `paramount`, `load-bearing` | important, or delete |
| `showcase`, `underscore`, `emphasize` | show |
| `cutting-edge`, `state-of-the-art`, `groundbreaking`, `innovative` | new, or delete |
| `game-changer`, `transformative`, `revolutionize` | delete, then say what changes |
| `landscape`, `realm`, `tapestry`, `synergy`, `testament` | area, or delete |
| `gracefully handles` | say what it does: "retries three times, then stops" |
| `out of the box`, `under the hood` | by default, internally |
| `furthermore`, `moreover`, `that being said` | also, but |
| `in conclusion`, `in summary`, `at the end of the day` | delete |
| `e.g.`, `i.e.`, `etc.` | for example, that is, name the items |
| `and/or` | "X, Y or both" |
