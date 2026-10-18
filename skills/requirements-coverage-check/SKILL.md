---
name: requirements-coverage-check
description: End-of-session (or anytime) audit that checks whether anything from the agreed requirements got missed, then asks the developer directly and interactively whether each gap was an oversight by the agent or a deliberate scope decision by the developer. Use whenever the developer asks "did we miss anything", "check if everything's covered", "did you do everything I asked", "audit this against the spec", or wants a sanity check before wrapping up work on a feature, bugfix, or project. Works with or without a spec.rp.md — uses the locked spec plus docs/decisions.md when the project was set up with backend-initializing-setup (or its NestJS/Next.js variants), and falls back to the conversation's stated requirements otherwise.
user-invocable: true
---

# Requirements Coverage Check

The point of this skill is to make sure a gap between "what was asked for"
and "what got built" surfaces on purpose, instead of being discovered
later by whoever relies on the missing piece. It doesn't assume a gap is a
mistake — plenty of things get deliberately descoped mid-session — it just
makes sure every gap gets a deliberate answer instead of staying silent.

## Asking the developer questions

This entire skill is a series of questions, so get the format right: ask
each one as an interactive multiple-choice prompt (the AskUserQuestion
tool, if your environment provides one) rather than open text — a
developer picking "yes, that was intentional" is faster and less ambiguous
than typing an explanation from scratch. Keep the wording plain and
short, and always include a way to say "something else" (a free-text/
"Other" option) since a gap's real answer sometimes doesn't fit either
box. If no interactive-question tool is available, present the same
options as a short lettered list instead. Most tools cap how many
questions fit in one prompt (commonly four) — batch gaps into rounds of
that size rather than dumping a huge list into one message.

## Phase 1 — Build the requirement baseline

Gather what was actually agreed to, from whichever sources exist:

- **`spec.rp.md`**, if this project has one (see `backend-initializing-setup`
  and its stack-specific variants) — the primary source of truth for
  goals, data model, and API surface. It's locked, so nothing here
  changes it; it's only being read.
- **`docs/decisions.md`**, if present — anything decided after the spec
  was locked is a requirement too, just one that lives outside the frozen
  file.
- **The conversation itself**, always — explicit asks the developer made
  during this session, whether or not this project uses the spec/docs
  convention at all. If there's no `spec.rp.md`, this is the whole
  baseline.

Build a plain list of discrete, checkable items from all of this — each
one should be concrete enough that "was this done?" has a real answer
(e.g. "users can reset their password via email" rather than "auth
works").

## Phase 2 — See what actually happened

For the same session or timeframe, gather the evidence:

- Code changes: `git log`/`git diff` for the commits made this session (or
  since the spec was confirmed, if auditing a longer stretch), and which
  files/areas they touched.
- Tests added or updated, and whether they cover the checkable items from
  Phase 1 or just incidental behavior.
- Docs kept current: Swagger/OpenAPI annotations, `docs/bugs.md` entries
  opened or closed.
- Anything explicitly reported as skipped or deferred during the session
  already (e.g. a bug logged in `docs/bugs.md` as "deferred," or something
  the developer was told about but the conversation moved on from).

### Keep this phase cheap

This is the one place the audit can quietly burn a huge amount of context —
a full `git diff` or a long `spec.rp.md` dwarfs the handful of facts Phase 3
actually needs, and none of that raw material needs to sit in the
conversation once you've pulled those facts out of it. Two habits keep it
lean:

- Start from summaries, not full text. `git log --oneline` and
  `git diff --stat` tell you the shape and size of what changed before you
  ever open a full diff; only read the full diff for a file when the
  stat-level view leaves a specific checklist item genuinely unclear.
- When there's more to cross-reference than a file or two — a long
  `spec.rp.md`, a diff spanning many files, a whole test suite — delegate
  that reading to a subagent (e.g. an Explore/general-purpose agent) rather
  than pulling it all into this conversation. Ask it to return the Phase 3
  buckets directly (confirmed-done / already-deferred / unclear, each with
  one-line evidence), not the raw sources. The orchestrating conversation
  should end up holding the checklist, not everything it was built from. If
  no subagent is available in this environment, lean harder on stat-level
  commands and targeted greps instead of reading full files.

## Phase 3 — Cross-reference and flag candidate gaps

For each item from Phase 1, look for matching evidence in Phase 2. Sort
into three buckets:

- **Clearly done** — don't ask about these; listing them as confirmed in
  the final report is enough.
- **Clearly and explicitly deferred already** — the session already
  surfaced this as skipped (e.g. logged in `docs/bugs.md`, or the
  developer said "skip that for now" earlier in the conversation). Don't
  re-ask something already answered; just carry it into the report as a
  known, already-acknowledged gap.
- **Unclear or no evidence found** — these are the actual candidate gaps
  to ask about. Don't guess at this stage which of "missed" or
  "intentional" a gap is — that's exactly what Phase 4 is for.

If Phase 3 produces zero candidate gaps, say so and skip straight to the
Phase 6 report — there's no need to manufacture a question when the audit
comes back clean.

## Phase 4 — Ask about each candidate gap

For every unclear item, ask the developer directly which of these it is —
see [references/gap-question-patterns.md](references/gap-question-patterns.md)
for phrasing guidance and a template. The core options are always some
version of:

- **Done** — the evidence search missed it; it's actually covered (good to
  know the audit had a blind spot, but no action needed).
- **Intentionally skipped** — a deliberate scope decision, on purpose.
- **Missed** — this should have happened and didn't; needs doing.
- Something else — free text, for anything that doesn't fit cleanly (e.g.
  partially done, or done differently than planned).

Name the specific item in the question rather than asking generically —
"was the password-reset email flow built?" not "did we cover requirement
#4?". A developer who has to go look up what #4 was defeats the purpose of
asking quickly.

## Phase 5 — Resolve each answer

- **Done** — note it as confirmed in the report; no further action.
- **Intentionally skipped** — log it in `docs/decisions.md` (or
  `docs/notes.md` if the project has no decisions log) as an explicit
  non-goal, if it isn't already recorded somewhere. This is what stops the
  same gap from getting re-flagged as a mystery next time this audit runs.
  Never edit `spec.rp.md` itself to reflect this — the spec's lock rule
  from `backend-initializing-setup` still applies here; if the developer's
  answer implies the spec itself should change, that needs their explicit
  go-ahead to amend it, same as any other time.
- **Missed** — implement it, following whatever this project's normal
  development-loop rules are (minimal, tested, docs kept current — see
  `backend-initializing-setup`/`bugfix-workflow` for the specifics). Don't
  silently batch a large missed item into a huge change; treat it as its
  own piece of work with the same discipline as anything else.
- **Something else** — read what the developer wrote and handle it on its
  own terms; don't force it into one of the three buckets above if it
  genuinely doesn't fit.

## Phase 6 — Report

Close with a short coverage summary: confirmed-done items, already-known
gaps, and the resolution of anything asked about in Phase 4 (fixed now /
logged as intentional / still open and why). See
[references/coverage-checklist-format.md](references/coverage-checklist-format.md)
for the shape. Keep it scannable — this is a checklist, not a narrative.

## Reference files

- [references/gap-question-patterns.md](references/gap-question-patterns.md) —
  how to phrase the missed-vs-intentional question well, with examples
- [references/coverage-checklist-format.md](references/coverage-checklist-format.md) —
  the shape of the final report
