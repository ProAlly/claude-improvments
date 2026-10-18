# Bug checklist for the diff

Scoped to the changed code (plus enough surrounding context to know how
it's called) — not a whole-repo sweep. Every finding needs a concrete
failure scenario: specific input/state → specific wrong output, crash,
or corruption. "This could theoretically be an issue" is a hunch, not a
finding — leave it out or say it's a hunch explicitly.

## Concurrency & race conditions
- Check-then-act races: checking a condition then acting on it in a
  separate step, with no lock, so two concurrent callers can both pass
  the check.
- Shared mutable state (module-level variable, cache, singleton) touched
  by the new/changed code without synchronization.
- Fire-and-forget async work where the caller needs the result or the
  error but the change doesn't await or handle it.
- New event handlers/listeners that can fire twice (double-registration,
  no idempotency check) causing a duplicated side effect.

## Database & transactions
- A new or modified multi-step write not wrapped in a transaction.
- Missing rollback on an error path inside a transaction the change
  touches.
- **N+1 queries**: a loop added or modified to issue one query per
  iteration instead of a batched/joined query.
- A new query with no pagination/limit on a result set that can grow
  without bound.
- A connection/cursor/lock acquired in the new code without a guaranteed
  release on the error path.

## Error handling & exceptions
- Empty or log-only catch blocks introduced around the change.
- A new or widened catch clause that's broader than what the try block
  is actually guarding against.
- A new `.then()` with no `.catch`, or an async call made without await
  and without the caller handling its rejection.
- A resource opened in the new code without a `finally`/`using`/`defer`
  equivalent on the error path.
- Missing input validation at a trust boundary the change introduces or
  touches (new public endpoint, new message-queue consumer, new CLI
  flag) that lets malformed input reach code assuming it's already
  valid.

## Other correctness bugs
- Off-by-one, inverted boolean logic, wrong comparison operator in the
  new/changed lines.
- Null/undefined/None dereference on a value the change treats as
  always-present but that's actually optional.
- Mutating a shared or input object the caller didn't expect to be
  mutated (aliasing bugs) — especially likely in a change that takes an
  existing object and "just tweaks" it in place.
- A new date/time calculation with a timezone or locale assumption baked
  in.
- A new listener, timer, or interval that's registered but never
  cleaned up (leak), especially in UI/component code with a mount/unmount
  lifecycle.

## Regressions in what the change touches
- Does the change alter a function/endpoint/component that other,
  unchanged code calls? If so, check those callers against the new
  behavior — a change that's internally consistent can still break a
  caller that relied on the old contract (old return shape, old error
  behavior, old ordering guarantee).
