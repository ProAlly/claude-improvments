---
name: bugfix-workflow
description: Guided workflow for fixing a bug, hotfix, or regression in an existing codebase — reproduce and trace the real root cause, ask before guessing, make the smallest possible change, add a regression test that actually proves the fix, and hand back a manual verification checklist. Use this whenever the developer reports something broken, pastes an error/stack trace, says "this used to work", asks for a hotfix or urgent fix, describes a regression after a recent change, or wants a bug fixed with minimal risk to the rest of the codebase. Works on any stack — backend, frontend, scripts, infra code.
user-invocable: true
---

# Bugfix / Hotfix Workflow

A bugfix has a different failure mode than new feature work: the risk isn't
"did I build the wrong thing," it's "did I touch more than I needed to, and
did I actually fix the cause or just hide the symptom." This skill is built
around minimizing both risks — find the real cause, change as little as
possible, and prove the fix with a test that would have caught the original
bug.

## Asking the developer questions

Whenever a question in this workflow has a reasonably enumerable set of
answers, ask it as an interactive multiple-choice prompt (the
AskUserQuestion tool, if your environment provides one) instead of an
open-ended question — picking from 2-4 clear options is faster and less
error-prone than typing back a paragraph of context. Keep the wording
plain and short, skip unexplained jargon, and always leave room for
"something else" (a free-text/"Other" option). If no interactive-question
tool is available, present the same options as a short lettered list in
your reply instead.

This matters more here than in most workflows because of the next
section: many of this skill's questions can be pre-answered by prior art,
which turns "what do you think is going on?" into "here's what fixed this
before — same thing this time?", a much easier question to answer with a
quick pick than to answer from scratch.

## Phase 1 — Intake

Before asking the developer anything, spend a minute checking for prior
art: search `git log`/`git blame` on the affected files or area for past
commits that fixed something similar, and check any project memory or
knowledge base available — an issues/known-issues file, `docs/decisions.md`
and `docs/bugs.md` if this project uses the `backend-initializing-setup`
skill's conventions, or notes from earlier sessions. See
[references/prior-art-search.md](references/prior-art-search.md) for where
to look and how to fold a finding into a question instead of asking blind.

Then get a clear picture of the bug:

- What's the expected behavior vs. what actually happens?
- How can it be reproduced — exact steps, inputs, environment?
- Is there an error message, stack trace, or log output? If so, read it
  before asking further questions — it often answers things you'd
  otherwise have to ask about.
- Where was it noticed (local/staging/production) and how urgent is it?
- Is there a specific recent change (a commit, PR, or deploy) suspected of
  introducing it?

If prior art surfaced a plausible answer to one of these, lead with it as
the recommended option rather than asking blind — but still ask; a past
fix is a strong hint, not a confirmed answer. For anything prior art
didn't cover, don't invent reproduction steps or assume the cause from the
symptom alone — ask for whatever is missing. A fix built on a guessed-at
repro is a guess, no matter how confident the code looks afterward.

### Keep the search cheap

Prior-art search and root-cause tracing are open-ended by nature, which
makes them the easiest place in this workflow to accidentally pull far more
into context than the bug actually needs. A few habits keep it bounded
without losing the value of the search:

- Scope `git log`/`git blame` to the affected file or directory (as above),
  and to a reasonable depth (`-n 20`, or a date range if the area is old)
  rather than the whole repo's history. Read commit *messages* first
  (`--oneline`); only pull a full commit's diff when a message looks like a
  real match and the diff itself is needed to confirm it.
- If the affected area is large or unfamiliar (a subsystem you'd otherwise
  need to read many files to understand), delegate that exploration to a
  subagent and ask it to return the specific finding — the suspect
  function, the relevant precedent commit, the broken invariant — rather
  than reading every candidate file directly into this conversation.

## Phase 2 — Reproduce and find the root cause

- Reproduce the failure yourself first — ideally as a failing test, or at
  minimum by running the affected path — before touching any fix code. If
  it can't be reproduced with the information given, say so and ask for
  more (exact input, environment detail, timing) rather than fixing a
  hypothesis.
- Trace the failure to where the underlying assumption actually broke, not
  just where it became visible. See
  [references/root-cause-checklist.md](references/root-cause-checklist.md)
  for how to tell "where it broke" from "why it's wrong," and how prior
  history and existing test coverage inform that.
- If Phase 1's prior-art search turned up a past fix that looks like the
  same shape of bug, confirm it against the actual code rather than
  trusting it outright — code drifts, and a fix that was correct then may
  not fully apply now. Treat it as a strong lead to verify, not a
  shortcut past tracing the current code yourself.
- Anything else noticed along the way — a similar bug pattern elsewhere, an
  unrelated code smell, a missing test on an adjacent path — gets written
  down for Phase 6, not fixed now. Scope discipline starts here, before any
  code is written.

## Phase 3 — Confirm the approach, but only when it's actually in question

Most bugs have one obvious correct fix — for those, go straight to Phase 4
without ceremony. Stop and check with the developer first when:

- More than one plausible fix exists with real tradeoffs (fix at the
  source vs. guard downstream; a fix that changes a public API/response
  shape vs. one that doesn't).
- The root cause sits in a sensitive area — auth, payments, migrations, or
  anything touching money or hard-to-reverse state.
- The correct fix would be much larger than the bug seems to warrant, or
  the investigation reveals the "bug" is really a symptom of a bigger
  design issue.
- The report's idea of "correct behavior" and what the code is actually
  doing don't agree — that's a product question, not an engineering one.

Otherwise, asking is just friction — proceed.

## Phase 4 — Make the minimal fix

For every line changed, the test is: **does this line need to change to
fix the bug?** If not, it doesn't belong in this diff. See
[references/minimal-diff-principles.md](references/minimal-diff-principles.md)
for what this means in practice — no drive-by renames or reformatting, no
refactors bundled in, following the codebase's existing conventions rather
than introducing new ones for a single fix, and how to keep a data-layer
fix transactionally safe rather than trading one inconsistency for another.

Keep comments minimal, same as always: a short note on a genuinely
non-obvious fix (e.g. working around a library quirk) is fine; narrating
what the changed code does is not.

## Phase 5 — Test the fix

- Add or extend a test that reproduces the original bug — it must fail
  against the old code and pass against the fix. A test that passes
  without the fix applied proves nothing. See
  [references/regression-testing.md](references/regression-testing.md) for
  how to actually verify that (not just assume it).
- Run the full relevant test suite, not just the new test, to check the
  fix doesn't break something else nearby. "Relevant" scales with the
  codebase: for a small project, that's the whole suite; for a monorepo or
  a project with clearly separated packages/modules, start with the
  affected package's suite and widen only if the fix touches something
  shared. Either way, a passing run only needs its summary line kept in the
  conversation (N passed, timing) — pipe verbose runners through a filter
  for failures when the full log would otherwise dump hundreds of lines of
  passing-test noise into context for no benefit; keep the full output only
  when something actually failed and you need to see why.
- If the project has linting or pre-commit hooks (ESLint/Husky or an
  ecosystem equivalent), run them before calling the fix done.
- If something can't actually be run in this environment, say so plainly —
  don't report a test as passing without having run it.

## Phase 6 — Report back

Always close with:

1. **Root cause**, in plain terms — not just "fixed it," but what was
   actually wrong and why. Note if a similar past fix was found and reused
   (Phase 1/2), and where.
2. **What changed** — the files touched, confirming the diff stayed
   minimal and scoped to the bug.
3. **Anything else noticed but not fixed** — flagged explicitly rather than
   silently fixed or silently dropped. If the project has a `docs/bugs.md`
   (see the `backend-initializing-setup` skill's conventions, if this
   project uses it), log them there; otherwise list them in the response.
4. **A manual test checklist** — always include one, even when automated
   tests pass, since a human glancing at the actual behavior catches
   things a test suite doesn't. Use
   [references/manual-test-checklist.md](references/manual-test-checklist.md)
   for the shape.

## Reference files

- [references/prior-art-search.md](references/prior-art-search.md) — where
  to look for past fixes to similar bugs, and how to turn a finding into a
  recommended answer instead of a blind question
- [references/root-cause-checklist.md](references/root-cause-checklist.md) —
  how to reproduce, trace symptom to cause, and use history/tests as context
- [references/minimal-diff-principles.md](references/minimal-diff-principles.md) —
  what counts as in-scope vs. a drive-by change, and data-safety in fixes
- [references/regression-testing.md](references/regression-testing.md) —
  how to write a regression test and actually confirm it covers the bug
- [references/manual-test-checklist.md](references/manual-test-checklist.md) —
  template for the human-facing verification steps handed back at the end
