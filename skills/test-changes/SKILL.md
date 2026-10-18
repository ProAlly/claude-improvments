---
name: test-changes
description: Properly test the changes on the current branch — everything committed since it diverged from base PLUS whatever's still uncommitted. Enumerates the real use cases the change is supposed to serve (happy path, edge cases, error paths), checks whether they're actually covered by tests, writes the tests that are missing, and separately hunts the diff for broken logic/bugs and over-engineering (unnecessary abstraction, speculative generality, complexity beyond what the task needed). Starts with static analysis, then asks before running anything (the test suite, a dev server, a real use-case exercise). Use this whenever the user asks to "test my changes", "test this properly", "did I miss any use cases", "check this diff for bugs and over-engineering", or wants confidence a change actually works before it ships — not for a plain diff-correctness pass (use code-review for that) or a whole-repo audit (use full-codebase-review for that).
user-invocable: true
---

# Test the Changes

The failure mode this skill is built around: code that *looks* done —
compiles, passes the tests that already existed, reads cleanly — but
either doesn't actually handle the use case it was built for, or handles
it with three times the machinery the task needed. Both are real defects.
This skill's job is to catch both, on exactly the changes at hand, not
the whole repo.

Three things happen here, always in this order:
1. Figure out what actually changed.
2. Reason about it statically — use cases, bugs, over-engineering.
3. Ask before doing anything that executes code.

## Phase 1 — Resolve the diff

The scope is fixed: **everything committed on this branch since it
diverged from its base, plus whatever's still uncommitted.** Not "ask
each time" — always compute it this way unless there's no sensible base
to diff against. See
[references/diff-scope.md](references/diff-scope.md) for the exact
commands (base-branch detection, merge-base diff, catching untracked
new files that plain `git diff` won't show).

List the changed files and, for each one, what changed — new function,
modified behavior, new endpoint, new component, config change, etc. This
list is what Phases 2 and 3 work from; don't skip straight to reading
diffs without this inventory, it's what keeps the use-case enumeration
grounded in what's actually there instead of what you assume is there.

## Phase 2 — Static analysis (always runs)

Three passes over the same diff, each looking for something different.
Don't merge them into one vague "review" — they catch different things
and deserve separate attention.

### 2a. Use-case coverage
For every changed behavior, work out what it's actually supposed to do —
from the code itself, commit messages, any linked issue/ticket, or by
asking the user if the intent genuinely isn't recoverable from context.
Then enumerate the use cases: the happy path, the edge cases (empty
input, boundary values, concurrent calls, the second time this runs not
just the first), and the error paths (what's supposed to happen when the
precondition isn't met). Check each one against the actual test files —
not "is there a test file" but "does an existing test actually exercise
this specific case." See
[references/use-case-enumeration.md](references/use-case-enumeration.md)
for how to do this without either rubber-stamping thin coverage or
demanding exhaustive tests for trivial cases.

### 2b. Broken logic / bugs
Read the diff (and enough surrounding code to know the calling context)
for actual correctness bugs — not style, logic. See
[references/bug-checklist.md](references/bug-checklist.md) for the
categories: race conditions, DB/transaction issues, N+1 queries, swallowed
exceptions, unhandled promise rejections, off-by-one, null derefs, and
so on. Every finding needs a concrete failure scenario (specific input/
state → specific wrong output or crash) — a vague "this looks risky"
isn't a finding yet.

### 2c. Over-engineering
Check whether the change is doing more than the task needed — new
abstractions with one caller, config/flags for a need nobody asked for,
a new interface where a plain function would do, re-implementing
something the codebase already gets from a library it already depends
on. See [references/overengineering-checklist.md](references/overengineering-checklist.md).
Report these, don't rewrite them — simplifying architecture is a
deliberate decision the user should make, not something to do silently
inside a testing pass. Point them at the `simplify` skill if they want
it actually fixed.

## Phase 3 — Ask before executing anything

Static analysis alone can't tell you whether the code actually runs
correctly — only whether it looks like it should. After Phase 2, decide
whether running things would resolve a real open question (a test that
should exist and pass, a use case that's only verifiable by actually
calling the changed code, an existing suite that might have broken).
If there's nothing execution would add — the change is trivial, or
existing tests already demonstrably cover it — say so and skip straight
to Phase 5.

Otherwise, ask the user (AskUserQuestion if available, otherwise ask
plainly in text) what they want run — options roughly like:
- Run the existing test suite (scoped to the affected area, or whole
  suite if the repo is small)
- Also exercise the actual use cases at runtime (start the dev server /
  CLI / whatever the project needs, and hit the changed paths for real —
  a browser flow for UI changes, an HTTP call for an endpoint, a CLI
  invocation for a command)
- Skip execution, static analysis is enough

Don't run anything before this answer comes back. See
[references/execution.md](references/execution.md) for how to actually
run each kind of project (finds the project's own test/run commands
first, falls back to stack-appropriate defaults) and how to read the
results without dumping a wall of passing-test noise into the
conversation.

## Phase 4 — If approved, run it

Follow whatever the user picked in Phase 3. Read failures for what they
actually mean, not just pass/fail counts — a failing test that was
already failing before this change is a different situation than one
this change broke. Feed anything discovered here back into Phase 2's
bug list rather than treating it as a separate thing.

## Phase 5 — Write the missing tests

For every real use-case gap found in 2a (confirmed still missing after
Phase 4, if that ran), write an actual test for it — following the
project's existing test framework and conventions, not a new one. A test
for a bug found in 2b/Phase 4 should fail against the current code and
demonstrate the bug (that's the point — it's evidence, and it's the
regression test once the bug gets fixed later). A test for a plain
missing use case should pass, proving the behavior already works
correctly, just wasn't covered.

This skill **writes tests, it does not fix bugs or refactor
over-engineered code** — those are separate decisions for the user to
make deliberately. Report bugs and over-engineering; only ever add test
files.

## Phase 6 — Report

Close with, in this order:
1. **Use-case coverage** — a short table: use case → covered by existing
   test / newly added test / still missing and why (e.g. needs
   infrastructure this skill doesn't have access to).
2. **Bugs and over-engineering found** — call `ReportFindings` with these
   (category one of the bug-checklist categories, or `over-engineering`),
   ranked real-correctness-bugs-first.
3. **What ran and what it showed** — if Phase 4 ran, the test suite
   result and anything exercised manually, briefly (pass/fail counts,
   not a full log dump — keep the full output only for actual failures).
4. **New test files added** — list them so the user can review before
   committing.

## Reference files

- [references/diff-scope.md](references/diff-scope.md) — base-branch
  detection and the exact diff command for "committed + uncommitted"
- [references/use-case-enumeration.md](references/use-case-enumeration.md) —
  how to enumerate use cases and judge real coverage vs. thin coverage
- [references/bug-checklist.md](references/bug-checklist.md) — the
  correctness-bug categories to check the diff against
- [references/overengineering-checklist.md](references/overengineering-checklist.md) —
  what counts as over-engineering vs. reasonable design
- [references/execution.md](references/execution.md) — how to find and
  run a project's tests/dev server, and how to report results concisely
