# Transactions and in-memory caching (Next.js)

## Unit-of-work helper (plain function version)

Without a DI container, the same transaction-boilerplate problem from any
Mongoose project is solved with a plain async helper instead of an
injectable service:

```ts
// lib/db/unit-of-work.ts
import { ClientSession } from 'mongoose';
import { dbConnect } from './connect';

export async function runInTransaction<T>(
  work: (session: ClientSession) => Promise<T>,
): Promise<T> {
  const connection = (await dbConnect()).connection;
  const session = await connection.startSession();
  try {
    return await session.withTransaction(() => work(session));
  } finally {
    await session.endSession();
  }
}
```

Usage in a service that must keep two collections consistent:

```ts
async function transferCredits(fromId: string, toId: string, amount: number) {
  return runInTransaction(async (session) => {
    await accountsRepo.decrement(fromId, amount, session);
    await accountsRepo.increment(toId, amount, session);
    await ledgerRepo.recordTransfer(fromId, toId, amount, session);
  });
}
```

Every repository function that can participate in a transaction accepts an
optional `session` parameter and passes it through to the Mongoose call —
silently dropping it there is a correctness bug, since that write would no
longer actually be part of the atomic group.

## When a transaction is actually needed

A single-document, single-collection write is already atomic in MongoDB
without a session. Reach for `runInTransaction` specifically when an
operation must keep more than one document or collection consistent — the
transfer example above, or "create this order and its line items
together." Wrapping every write in a transaction "just in case" adds
overhead without buying correctness, and is the over-engineering side of
ACID compliance to avoid.

## Testing transactional code

`mongodb-memory-server`'s `MongoMemoryReplSet` spins up an ephemeral
single-node replica set so the real transaction path runs in tests instead
of being mocked away:

```ts
const mongod = await MongoMemoryReplSet.create({ replSet: { count: 1 } });
```

A regression test for `runInTransaction` usage should specifically assert
the rollback path — that if the second write throws, the first write's
effect isn't visible afterward. That's the actual guarantee being bought,
and a happy-path-only test wouldn't catch a broken rollback.

## In-memory cache: cache-aside, with explicit invalidation

```ts
// lib/cache/memory-cache.ts
type Entry<T> = { value: T; expiresAt: number };
const store = new Map<string, Entry<unknown>>();

export function cacheGet<T>(key: string): T | undefined {
  const entry = store.get(key);
  if (!entry) return undefined;
  if (Date.now() > entry.expiresAt) {
    store.delete(key);
    return undefined;
  }
  return entry.value as T;
}

export function cacheSet<T>(key: string, value: T, ttlMs: number) {
  store.set(key, { value, expiresAt: Date.now() + ttlMs });
}

export function cacheDelete(key: string) {
  store.delete(key);
}
```

```ts
// lib/services/products.ts
async function findById(id: string) {
  const key = `product:${id}`;
  const cached = cacheGet<Product>(key);
  if (cached) return cached;

  const product = await repo.findById(id);
  cacheSet(key, product, 60_000);
  return product;
}

async function update(id: string, data: UpdateProductData) {
  const updated = await repo.update(id, data);
  cacheDelete(`product:${id}`); // invalidate, don't try to patch the cached value in place
  return updated;
}
```

Invalidate on write rather than patching the cached value — deleting the
key just costs the next reader one cache miss, whereas patching in place
is an easy way for the cache to drift from the database.

## The limitation that matters more here than in a long-running server

This cache is a plain `Map` living in one Node process's memory:

- It's empty again after every restart, redeploy, or hot reload.
- On a **serverless** deployment target (Vercel functions, AWS Lambda,
  etc.), each invocation may run in a fresh or recycled instance with no
  guarantee the same process handles the next request — so this cache can
  behave more like "sometimes helps within a warm instance" than "reliably
  caches," which is a materially different guarantee than the same code
  gives on a long-running Node server.
- If the service runs as more than one instance for any reason, each has
  its own independent cache — a write on one doesn't invalidate another's
  copy.

This is a legitimate default for a single long-running Node process or for
data where cross-instance staleness for a few seconds is harmless. Flag it
explicitly against whatever deployment target came out of Phase 1 — if
the target is serverless and the project needs reliable cross-request
caching, that's a real tradeoff for the developer to decide on knowingly
(the natural upgrade path is a shared store like Redis behind the same
`cacheGet`/`cacheSet`/`cacheDelete` interface), not something to silently
work around by picking a different cache implementation unasked.
