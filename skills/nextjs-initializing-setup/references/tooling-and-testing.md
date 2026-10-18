# Linting, hooks, and the Jest/TDD loop (Next.js)

## ESLint + Husky

`create-next-app` already sets up ESLint (`next lint` / a flat config) —
don't reconfigure it from scratch, just check it fits the project. Husky
isn't included by default:

```bash
npm install --save-dev husky
npx husky init
```

`.husky/pre-commit`:

```bash
#!/usr/bin/env sh
npm run lint && npm test
```

## Jest setup

Use `next/jest` so the config picks up Next's own transforms (TypeScript,
env vars) without hand-rolling a `ts-jest` setup:

```js
// jest.config.js
const nextJest = require('next/jest')();
module.exports = nextJest({ dir: './' })({
  testEnvironment: 'node', // API/route-handler tests don't need a DOM
  moduleNameMapper: { '^@/(.*)$': '<rootDir>/$1' },
});
```

## The TDD loop

Same discipline as any project using this skill family — write the test
alongside or before the implementation, not after:

- **Unit tests for services** — call the plain functions in
  `lib/services/*.ts` directly, passing in a fake repository object that
  implements the same shape the real Mongoose repository does. Because
  services take their repository as a parameter (see
  [references/scaffold-guide.md](references/scaffold-guide.md)) rather
  than importing it, this needs no database and runs fast.
- **Integration tests for repositories** — run against a real MongoDB via
  `mongodb-memory-server` rather than mocking Mongoose; a mocked model
  doesn't prove a query is actually correct.
- **Route Handler tests** — import the exported `GET`/`POST`/etc. function
  directly from the route file and call it with a constructed `Request`
  (or `node-mocks-http`'s helpers adapted to the Fetch API shape App
  Router handlers expect), rather than spinning up a real HTTP server.
  This catches request-parsing and response-shaping bugs without the
  overhead of an end-to-end test.
- **Transaction tests** — as covered in
  [references/mongodb-transactions-and-cache.md](references/mongodb-transactions-and-cache.md),
  use `MongoMemoryReplSet` (not the single-node `MongoMemoryServer`), and
  specifically assert the rollback path.

Keep the test pyramid shape: many fast unit tests around services, fewer
integration tests around repositories, fewer still full route-handler
tests. If every test needs a real database, that's a sign a service still
has a hard dependency on the concrete repository instead of the interface
shape.
