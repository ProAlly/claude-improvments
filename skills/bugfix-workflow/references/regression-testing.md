# Writing a regression test that actually proves the fix

## A test that only ever passes proves nothing

Writing the test after the fix and watching it pass is not sufficient
evidence — it might be passing because the fix works, or because the test
doesn't actually exercise the buggy path at all. Verify it the other way
round wherever practical:

1. Write the test so it encodes the bug report's expected-vs-actual
   behavior.
2. Check that it fails against the pre-fix code. If a fix is already
   applied, this can mean temporarily reverting it (e.g. `git stash` the
   fix, or comment out the change) and confirming the test goes red.
3. Re-apply the fix and confirm the test goes green.

If reverting isn't practical in the environment, at minimum trace through
by hand that the test's assertion would genuinely fail under the old
behavior — don't skip this check just because it's inconvenient.

## Name it for the behavior, not the ticket

A test named after what it verifies (`rejects overlapping bookings for the
same room`) stays meaningful long after the bug report that prompted it is
forgotten. A test named after a ticket number or "regression test 1" loses
that context immediately.

## Put it where the existing suite already expects it

Match the project's existing test organization and framework rather than
introducing a new one for this fix. If the codebase tests services and
repositories separately, the regression test belongs at whichever layer
the bug actually lived in.

## Run the whole suite, not just the new test

The new test proves the bug is fixed. The rest of the suite is what proves
the fix didn't break something else nearby — both checks matter, and
skipping the second one because "it's just a small fix" is exactly how
small fixes cause new incidents.

## Lint and hooks are part of "tested," not optional polish

If the project has a linter or pre-commit hook (ESLint/Husky or an
ecosystem equivalent) configured, run it before considering the fix
finished — a fix that fails the project's own quality gate isn't done yet.
