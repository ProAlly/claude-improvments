# Over-engineering checklist

The question for every piece of this checklist is the same: **did the
task actually need this, or did the change add it "just in case" /
"to be clean" / "because that's the pattern"?** Report what you find —
this skill doesn't rewrite architecture, it flags it so the user can
decide, and points at the `simplify` skill if they want it acted on.

## Unnecessary abstraction
- A new interface, abstract base class, or factory with exactly one
  concrete implementation and no stated plan for a second.
- A new configuration option, flag, or strategy pattern built for a
  variation nobody asked for yet.
- Dependency injection wired up for something that will only ever have
  one real implementation in this codebase.

## Speculative generality
- A function generalized to handle inputs/cases the current callers
  never produce, "in case it's needed later."
- A new field, parameter, or config value added for a hypothetical
  future requirement rather than the one at hand.
- Extra layers of indirection (a wrapper around a wrapper) that don't
  currently do anything the inner layer doesn't already do.

## Complexity beyond the task
- Three new classes where a function would do the same job with less
  ceremony.
- A new state machine, event bus, or plugin system introduced for a
  single, simple use case.
- Re-implementing something a library the project already depends on
  already provides (a hand-rolled deep-clone, debounce, retry-with-
  backoff, etc. next to an existing dependency that already has one).
- New error types/hierarchies for errors that are all actually handled
  the same way by every caller.

## Scope creep
- Changes to files or behavior unrelated to what the task asked for,
  bundled into the same diff "while I was in there."
- Renames, reformatting, or refactors mixed into a change that didn't
  need them to accomplish its actual goal.

## What's NOT over-engineering
Don't flag design that matches an existing, established pattern already
used consistently elsewhere in this codebase for the same kind of thing
— consistency with what's already there is a reason *for* a pattern, not
against it. Also don't flag genuine complexity that the problem itself
requires (a real state machine for a genuinely stateful process, real
validation logic for genuinely complex business rules). Over-engineering
is complexity the *task* didn't need, not complexity you personally
would have written more simply.
