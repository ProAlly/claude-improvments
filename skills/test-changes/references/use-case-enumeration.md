# Enumerating use cases and judging coverage

## Finding the intended behavior

Before you can check coverage, you need to know what the change is
*for* — not just what it does mechanically. Pull this from, in order of
reliability:
1. The code itself — a well-named function/endpoint/component usually
   states its own intent.
2. Commit messages on this branch.
3. A linked issue/ticket if one's referenced.
4. Existing tests for the same area, which often encode intent even
   when comments don't.
5. Asking the user — only when the above genuinely don't answer it, not
   as a first resort.

## Enumerating use cases

For each changed behavior, list out, concretely:
- **The happy path** — the case the change was obviously built for.
- **Edge cases** — empty/null/zero input, the boundary values (first
  item, last item, exactly-at-limit), the second call not just the
  first (does calling it twice behave right?), concurrent callers if
  the code is reachable concurrently.
- **Error paths** — what's supposed to happen when a precondition isn't
  met (bad input, a dependency unavailable, a resource missing). "Should
  it throw, return null, log and continue?" — check what the surrounding
  code already does for similar cases and hold this change to the same
  standard.

Keep this proportional to the change. A one-line config tweak doesn't
need the same use-case tree as a new payment-processing function — use
judgment on how much the change's own risk warrants.

## Judging real coverage, not just presence

A test file existing for the changed function is not the same as the
use case being covered. For each use case on your list, actually find
the test (or tests) that exercise it and check:
- Does it actually assert on the behavior in question, or just that the
  function didn't throw?
- Does it use realistic-enough inputs to actually hit the edge case (a
  test called `test_empty_input` that passes `["a"]` isn't testing empty
  input)?
- If it's an error-path test, does it assert on the *specific* error/
  behavior, not just "something happened"?

Mark each use case as: **covered** (a real test exercises it correctly),
**thin** (a test exists but doesn't actually verify the behavior — treat
as a gap), or **missing** (no test touches it at all).

## What NOT to flag

Don't manufacture use cases that aren't real — inputs the calling code
structurally can never produce, environments the project doesn't support,
hypothetical future requirements nobody asked for. That's scope creep in
the other direction, and it's exactly the kind of thing Phase 2c (over-
engineering) exists to push back on when it shows up in the *code*; don't
let it creep into the test list either.
