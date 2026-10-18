# SOLID, ACID, and TDD in a backend scaffold

These three ideas are the non-negotiable defaults for Phase 5 onward. They're
included here as concrete backend patterns, not abstract definitions —
apply the pattern, don't just recite the letter.

## SOLID, applied to a backend

The layering that matters most in practice is: **controllers/routes** (parse
the request, call a service, shape the response) → **services** (business
logic, orchestration) → **repositories/data access** (talk to the database).
Each layer should only know about the one below it through an interface or
abstract contract, not a concrete implementation:

- **Single Responsibility** — a controller doesn't contain business logic,
  and a service doesn't build SQL. If a function is doing two of
  "validate", "decide", and "persist", split it.
- **Open/Closed** — new behavior (a new payment provider, a new notification
  channel) should mean adding a new implementation of an existing interface,
  not editing a switch statement buried in a service.
- **Liskov Substitution** — if something is typed as a `Repository` or a
  `PaymentGateway` interface, any concrete implementation must be swappable
  without the caller changing behavior in surprising ways.
- **Interface Segregation** — don't force a consumer to depend on methods it
  doesn't use; a read-only reporting service shouldn't depend on a
  repository interface that also exposes writes.
- **Dependency Inversion** — services depend on repository/gateway
  *interfaces*, injected in, not on concrete database clients or SDKs
  constructed inline. This is also what makes TDD practical, since it's
  what tests mock against.

Don't over-apply this on day one — a single-endpoint prototype doesn't need
five layers of abstraction it will never grow into. The point is that the
seams exist where real variation is expected (data access, external
providers), not that everything gets wrapped in an interface reflexively.
That would be the over-engineering the main skill instructions warn against.

## ACID, applied to a backend

This mostly comes down to one habit: **any operation with more than one
write is a transaction, not a sequence of writes**.

- Wrap multi-step database changes (e.g. "debit one account, credit
  another", "create an order, then its line items") in a single database
  transaction so a failure partway through rolls back cleanly instead of
  leaving inconsistent rows behind.
- Never leave a code path where a partial write is committed silently — if
  step 2 of 3 fails, step 1 must not survive it.
- Track every schema change as a migration from the very first one. A
  scaffold with no migration history is a scaffold nobody can safely deploy
  a second time.
- Consider isolation-level implications for anything with concurrent
  writers (e.g. two requests decrementing the same inventory count) —
  reaching for row locking, `SELECT ... FOR UPDATE`, or an optimistic
  concurrency check is appropriate there, not a nice-to-have.
- Idempotency matters wherever retries are possible (webhooks, payment
  callbacks, queue consumers) — a retried operation should not double-apply
  its effect.

## TDD, applied to a backend

The default loop for every unit of work, from the first scaffolded endpoint
onward: **write a failing test that describes the behavior, make it pass,
then clean up** (red → green → refactor). "Alongside" is an acceptable
variant of "before" — what's not acceptable is treating tests as a thing
added after the feature is already considered done.

- Favor the test pyramid: many fast unit tests around services and business
  logic, fewer integration tests around the data layer and HTTP boundary,
  fewer still end-to-end tests. Don't invert this by writing only end-to-end
  tests because they're easier to reason about upfront — they're slow and
  brittle at scale.
- A test should describe behavior a reader would actually care about
  breaking (a real business rule, a real edge case), not restate the
  implementation line by line. Coverage percentage is a signal, not a goal
  — don't pad it with tests that assert nothing meaningful.
- The SOLID boundaries above are what make this tractable: a service tested
  against an interface can be tested with a fake/mock repository instead of
  a real database for the fast unit-test layer, while integration tests
  cover the real thing.
