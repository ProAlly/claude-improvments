# Keeping a bugfix minimal

## The line-by-line test

For every changed line: does this need to change to fix the bug? If the
answer is "no, but it's better this way" — that's a separate change,
proposed separately, not folded into this diff. A minimal diff is easier
to review, easier to reason about, and easier to revert cleanly if it turns
out to be wrong.

Concretely, this rules out, unless the bug is actually about one of these:

- Renaming variables, functions, or files for clarity
- Reformatting or reordering unrelated code
- Upgrading dependencies
- Restructuring layers or extracting new abstractions
- "While I'm in here" cleanups of adjacent logic

## Fix within the existing shape of the code

Follow the conventions already established in the surrounding code —
naming, error-handling style, how layers talk to each other (routing vs.
business logic vs. data access, if that separation already exists). A
one-off fix is not the place to introduce a new pattern the rest of the
codebase doesn't use; consistency matters more here than which pattern is
technically nicer.

## Data-safety in the fix itself

If the bug or its fix touches persisted data:

- Any multi-step correction (updating more than one row/table, or
  correcting derived data alongside its source) belongs inside a single
  transaction — a bugfix that introduces a new partial-write path is a
  worse bug than the one it replaces.
- If the bug already corrupted existing data before the fix, that's a
  separate, bigger decision than the code fix: ask the developer whether a
  backfill/remediation of already-bad records is wanted, rather than
  assuming the code fix alone is sufficient or silently adding a data
  migration nobody asked for.

## Contract changes get flagged, not shipped quietly

If the fix changes what an API returns, what an endpoint accepts, or any
other behavior other consumers might depend on, say so explicitly rather
than letting it slide through as an implementation detail. Whether that's
acceptable is the developer's call, not something to decide unilaterally
mid-fix.

## Comments stay minimal

Same policy as everywhere else: a short comment explaining a genuinely
non-obvious fix (e.g. a workaround forced by a library's behavior) earns
its place. A comment narrating what the corrected code does does not — if
that feels necessary, the code itself should be clearer instead.
