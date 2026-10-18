# Review checklist

Hand these categories to every chunk subagent. The threshold is low —
minor issues count — but every finding still needs a concrete failure
scenario, not a vague concern. "This function is long" is not a finding;
"this 200-line function does auth, billing, and logging in one place,
so a bug in the logging branch can silently skip the billing write" is.

## 1. Clean code & readability
- Duplicated logic that should be one function/module (not just visually
  similar code — actual behavior duplication that will drift out of sync).
- Dead code: unreachable branches, unused exports, commented-out blocks
  left in place.
- God functions/classes doing multiple unrelated things.
- Misleading names (a function named `get*` that mutates state, a
  variable whose name no longer matches what it holds).
- Deep nesting that hides a branch's real condition (skip pure style
  preference here — a linter's job — flag it only when the nesting
  itself causes or hides a bug, e.g. an `if` whose `else` was clearly
  meant to pair with a different branch).

## 2. SOLID / OOP design
- **SRP**: a class/module with more than one reason to change, where
  that's already caused (or will obviously cause) unrelated changes to
  collide.
- **OCP**: a growing `switch`/`instanceof`/`if-elif` chain over a type
  that keeps getting new cases, where each new case requires editing
  existing code instead of adding to it.
- **LSP**: a subclass/override that narrows accepted inputs, widens
  thrown exceptions, or otherwise breaks a caller that only knows the
  base type's contract.
- **ISP**: an interface forcing implementers to define methods they
  don't use (stub/no-op implementations are the tell).
- **DIP**: high-level business logic directly constructing or importing
  concrete low-level details (a specific DB driver, a specific HTTP
  client) in a way that makes the logic untestable or the dependency
  unswappable, where an abstraction is the established pattern elsewhere
  in the codebase.

## 3. Architecture
- Layering violations: UI/controller code reaching into DB internals
  directly, business rules living in a route handler instead of a
  service layer the rest of the codebase uses.
- Circular module dependencies.
- Inconsistent patterns between modules that do the same kind of thing
  (one service wraps writes in a transaction, an equivalent one doesn't).
- Framework/library types leaking across a boundary that's supposed to
  be framework-agnostic (e.g. an HTTP request object passed into a
  domain-layer function).

## 4. Concurrency & race conditions
- Check-then-act races: checking a condition (exists? has balance?) and
  acting on it in a separate step without a lock, allowing two
  concurrent callers to both pass the check.
- Shared mutable state (module-level variable, in-memory cache, static
  field) read/written by multiple requests/threads/async tasks without
  synchronization.
- Non-atomic increment/update operations (`x = x + 1` instead of an
  atomic DB increment or a proper lock) under concurrent access.
- Fire-and-forget async calls where the caller needs the result or the
  error (a promise/task started but never awaited or attached to).
- Event handlers or listeners that can fire twice (double-registration,
  missing idempotency) and cause a double side effect (double charge,
  double email).
- Async operations awaited/sequenced in the wrong order, so a later step
  reads state a concurrent earlier step hasn't finished writing yet.

## 5. Database & transactions
- Multi-step writes (e.g. debit one row, credit another) not wrapped in
  a single transaction — a crash between steps leaves inconsistent data.
- Transactions left open across a slow external call (network request,
  external API) — holds locks far longer than necessary and risks
  timeouts leaving things half-committed.
- Missing rollback on an error path inside a transaction block.
- Missing unique constraint or row lock where the code assumes
  "check-then-insert" is safe under concurrency (see race conditions
  above — this is the DB-specific version of it).
- **N+1 queries**: a loop that issues one query per iteration instead of
  a single batched/joined query — flag every instance, this is one of
  the most common and most fixable issues in this category.
- Unbounded result sets or missing pagination on a query that can grow
  without limit.
- Connection/pool leaks: a connection or cursor acquired but not
  released on an error path.
- ORM lazy-loading traps: accessing a lazy relation inside a loop,
  triggering the N+1 above without it being obvious from the code.

## 6. Error handling & exceptions
- Empty or log-only catch blocks where the caller's contract implies the
  error should propagate or be handled, not swallowed.
- Overly broad catch clauses (`catch (Exception e)` / bare `except:`)
  that hide bugs unrelated to what the try block was guarding against.
- Unhandled promise rejections — a `.then()` with no `.catch`, an async
  function called without `await` and without error handling by the
  caller.
- Resources (files, sockets, locks, transactions) not released on the
  error path — missing `finally`/`using`/`defer`/context-manager
  equivalent.
- Re-thrown errors that lose the original stack trace or cause, making
  the eventual failure unaddressable in production.
- Uncaught exceptions inside callbacks, event listeners, or
  timers/intervals — these often bypass a surrounding try/catch entirely
  and crash or silently die depending on the runtime.
- Missing input validation at a trust boundary (public API handler,
  message-queue consumer) that lets malformed input reach code that
  assumes it's already valid and crashes or corrupts state.

## 7. Other correctness bugs (any severity, still worth flagging)
- Off-by-one errors, inverted boolean conditions, wrong comparison
  operator.
- Null/undefined/None dereference on a value that's actually optional.
- Mutating a shared or input object when the caller doesn't expect
  mutation (aliasing bugs).
- Floating-point equality comparisons where an epsilon or decimal type
  is needed (money is the classic case).
- Timezone/locale assumptions baked into date math.
- Resource/memory leaks: listeners registered but never removed, timers
  never cleared, growing caches with no eviction.
- Anything security-adjacent noticed in passing (e.g. an obvious
  injection point, a secret logged in plaintext) — flag it, but note
  that a dedicated `/security-review` pass covers this ground more
  thoroughly if the user wants depth there.
