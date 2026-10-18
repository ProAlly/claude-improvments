# Transactions and in-memory caching

## Why a helper instead of inline `session.withTransaction`

Mongoose transactions work through a `ClientSession` that has to be
threaded through every operation in the transaction and passed to
`withTransaction` for automatic commit/retry/abort handling. Writing that
boilerplate in every service that touches more than one document is both
repetitive and exactly the kind of place a copy-pasted mistake silently
breaks atomicity. Centralize it once:

```ts
// unit-of-work.service.ts
@Injectable()
export class UnitOfWork {
  constructor(@InjectConnection() private readonly connection: Connection) {}

  async run<T>(work: (session: ClientSession) => Promise<T>): Promise<T> {
    const session = await this.connection.startSession();
    try {
      return await session.withTransaction(() => work(session));
    } finally {
      await session.endSession();
    }
  }
}
```

Usage in a service that must keep two collections consistent:

```ts
async transferCredits(fromId: string, toId: string, amount: number) {
  return this.unitOfWork.run(async (session) => {
    await this.accountsRepo.decrement(fromId, amount, session);
    await this.accountsRepo.increment(toId, amount, session);
    await this.ledgerRepo.recordTransfer(fromId, toId, amount, session);
  });
}
```

Every repository method that participates in a transaction accepts an
optional `session` parameter and passes it through to the Mongoose call
(`.exec({ session })` / `create([data], { session })` / etc.) — a method
that silently ignores a passed-in session is a correctness bug, since it
means that write isn't actually part of the atomic group.

## When a transaction is actually needed

Not every write needs one — a single document, single-collection update is
already atomic in MongoDB without wrapping it in a session. Reach for
`UnitOfWork.run` specifically when an operation must keep **more than one
document (or more than one collection) consistent** — the transfer example
above, creating an order alongside its line items, or any "all of this
happens or none of it does" requirement. Wrapping single-document writes
in a transaction anyway just adds overhead and complexity without buying
correctness — that's the over-engineering side of ACID compliance to avoid.

## Testing transactional code without a real replica set

`mongodb-memory-server` can spin up an ephemeral single-node replica set
for tests, so the transaction path gets exercised for real instead of
mocked away:

```ts
const mongod = await MongoMemoryReplSet.create({ replSet: { count: 1 } });
```

A regression test for transactional code should assert the rollback
behavior specifically — that if the second write in a `UnitOfWork.run`
block throws, the first write's effect is not visible afterward. That's
the actual guarantee ACID compliance is buying, and it's the part a naive
test (which only checks the happy path) would miss entirely.

## In-memory cache: cache-aside, with explicit invalidation

```ts
// app.module.ts
CacheModule.register({ isGlobal: true, ttl: 60_000 }); // default in-memory store
```

```ts
@Injectable()
export class ProductsService {
  constructor(
    @Inject(PRODUCTS_REPOSITORY) private readonly repo: ProductsRepository,
    @Inject(CACHE_MANAGER) private readonly cache: Cache,
  ) {}

  async findById(id: string): Promise<Product> {
    const key = `product:${id}`;
    const cached = await this.cache.get<Product>(key);
    if (cached) return cached;

    const product = await this.repo.findById(id);
    await this.cache.set(key, product, 60_000);
    return product;
  }

  async update(id: string, data: UpdateProductData): Promise<Product> {
    const updated = await this.repo.update(id, data);
    await this.cache.del(`product:${id}`); // invalidate, don't try to patch the cached value in place
    return updated;
  }
}
```

Invalidate on write rather than trying to update the cached value in
place — patching a cache entry to match a write is an easy place for it to
drift out of sync with the database, whereas deleting the key just means
the next read pays one cache miss.

## The limitation to keep visible, not paper over

This cache lives in the memory of a single Node process:

- It's empty again after every restart or deploy.
- If the service ever runs as more than one instance (horizontal scaling,
  multiple containers), each instance has its own independent cache — a
  write on one instance does not invalidate the cached copy on another.

This is fine, and often exactly what's wanted, for a single-instance
deployment or for caching data where a few seconds of staleness across
instances doesn't matter. It stops being fine the moment the project needs
strict cross-instance cache consistency — at that point the natural
upgrade is swapping the in-memory store for a shared one (e.g. Redis)
behind the same `CACHE_MANAGER` interface, which is exactly why this
pattern is written against that interface rather than a bespoke `Map`.
Flag this tradeoff to the developer during Phase 1/5 rather than let it be
discovered as a bug later.
