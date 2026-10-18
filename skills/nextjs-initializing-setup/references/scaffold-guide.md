# Scaffolding the Next.js + MongoDB backend

## Base project

```bash
npx create-next-app@latest <project-name> --typescript --eslint --app --no-src-dir
```

Use the App Router (`--app`) so the API lives in `app/api/**/route.ts`
Route Handlers — the modern convention, and the one this skill's Swagger
and testing setup assumes. If the developer specifically wants the Pages
Router's `pages/api/*.ts` instead, the same layering and transaction/cache
patterns still apply; just confirm that choice explicitly rather than
defaulting past it.

## Core dependencies

```bash
npm install mongoose zod next-swagger-doc swagger-ui-react
npm install --save-dev husky jest ts-jest @types/jest mongodb-memory-server node-mocks-http
```

`zod` fills the role `class-validator` plays in a Nest project — parsing
and validating request bodies/params in each Route Handler.

## Layering without a DI container

Next.js has no framework-level dependency injection, so the same
controller/service/repository separation has to be kept by convention:

```
app/api/<resource>/route.ts   → thin handler: parse, call service, respond
lib/services/<resource>.ts    → business logic, orchestration
lib/repositories/<resource>.ts→ the only place that imports Mongoose models
lib/db/connect.ts             → the cached Mongoose connection (below)
lib/db/unit-of-work.ts        → the transaction helper
lib/cache/memory-cache.ts     → the in-memory TTL cache singleton
```

Keep services decoupled from the concrete repository by accepting it as a
parameter (or constructing it once in a small composition point) rather
than importing and calling it directly inside the service body — that's
what keeps a service testable with a fake repository instead of a real
database, the same benefit Nest gets from its DI container:

```ts
// lib/services/products.ts
export function createProductsService(repo: ProductsRepository) {
  return {
    async findById(id: string) {
      return repo.findById(id);
    },
  };
}
```

```ts
// app/api/products/[id]/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { createProductsService } from '@/lib/services/products';
import { mongooseProductsRepository } from '@/lib/repositories/products';

const service = createProductsService(mongooseProductsRepository);

export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  const product = await service.findById(params.id);
  if (!product) return NextResponse.json({ error: 'Not found' }, { status: 404 });
  return NextResponse.json(product);
}
```

Don't build this indirection for a trivial single-collection route with no
real logic — introduce the interface/parameter seam where a service
actually has business rules worth testing in isolation, or where it
participates in a transaction. Applying it everywhere uniformly is
over-engineering for routes that are genuinely just "fetch this document."

## The serverless-safe MongoDB connection

The single most common Next.js + Mongoose mistake: calling
`mongoose.connect()` directly in a route handler reconnects on every
request in development (hot reload) and can exhaust connections in
serverless production. Cache the connection on the global object instead:

```ts
// lib/db/connect.ts
import mongoose from 'mongoose';

const uri = process.env.MONGODB_URI;
if (!uri) throw new Error('MONGODB_URI is not set');

let cached = (global as any)._mongoose;
if (!cached) {
  cached = (global as any)._mongoose = { conn: null, promise: null };
}

export async function dbConnect() {
  if (cached.conn) return cached.conn;
  if (!cached.promise) {
    cached.promise = mongoose.connect(uri).then((m) => m);
  }
  cached.conn = await cached.promise;
  return cached.conn;
}
```

Every repository calls `await dbConnect()` before touching a model. Fail
fast on a missing `MONGODB_URI` at import time, as above, rather than
letting the first request surface a confusing runtime error.

## Transactions and cache

See [references/mongodb-transactions-and-cache.md](references/mongodb-transactions-and-cache.md)
for the unit-of-work helper (a plain async function here, not an
injectable) and the in-memory cache singleton, including the serverless
caveat that matters more here than in a long-running Nest server.

## Swagger

See [references/swagger-openapi.md](references/swagger-openapi.md).

## Local development database

Transactions require a replica set — a plain standalone `mongod` rejects
them at runtime rather than silently skipping the atomicity guarantee.
Either run a single-node replica set locally (`mongod --replSet rs0`, then
`rs.initiate()` via `mongosh`) or point local development at a free-tier
MongoDB Atlas cluster, which already is one. Record whichever the
developer picks in `docs/decisions.md`.
