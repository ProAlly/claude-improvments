# Finding the root cause, not the symptom

## Reproduce before theorizing

If it can't be reproduced — locally, in a test, or by tracing the exact
input through the code by hand — a fix at this point is a guess dressed up
as a diagnosis. Ask for whatever's missing (exact input, environment,
timing, a specific record/ID that triggers it) rather than proceeding on a
hunch.

## Read the actual error, not the paraphrase of it

Bug reports often describe the symptom the reporter noticed, which may be
several steps removed from where things actually went wrong. A stack trace
or log line is ground truth in a way a description isn't — read it before
asking questions that it might already answer.

## Trace backward until the assumption actually breaks

"Where it breaks" (a null-pointer exception at line X) and "why it's
wrong" (an upstream call three layers up returns an unchecked null on a
valid but unusual input) are different things. Keep tracing the call chain
backward past the crash site until you find the point where an invariant
was actually violated — that point, not the crash site, is where the fix
belongs.

## Use history as context, not as a verdict

Checking blame/log for the affected lines answers a useful question — was
this always subtly wrong, or did a specific recent change introduce it?
That changes the framing (a regression to revert/adjust vs. a latent bug
that finally got triggered) but doesn't replace tracing the code yourself
to confirm the actual mechanism.

## Check what the existing tests do and don't cover

If tests exist around the affected path, did they simply not cover this
case, or were they asserting the wrong thing? Either answer shapes what
the regression test in Phase 5 needs to do differently from what's already
there.

## Note the same pattern elsewhere — don't chase it now

If the root cause is a class of mistake (e.g. an unchecked optional field,
a missing transaction boundary), it's worth noticing if that same pattern
shows up elsewhere in the codebase. Write it down for the Phase 6 report.
Fixing those other occurrences now — however tempting — is scope creep
beyond the bug that was actually reported.
