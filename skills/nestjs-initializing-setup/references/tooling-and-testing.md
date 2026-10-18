# Linting, hooks, and the Jest/TDD loop

## ESLint + Husky

`nest new` already sets up ESLint and Prettier — don't reconfigure them
from scratch, just verify the config matches the project's needs. Husky
isn't included by default and needs adding:

```bash
npm install --save-dev husky
npx husky init
```

Wire `.husky/pre-commit` to run lint and the fast test layer before
allowing a commit:

```bash
#!/usr/bin/env sh
npm run lint && npm test
```

## The TDD loop with Jest

Nest ships Jest configured for both unit tests (`*.spec.ts` next to the
file under test) and e2e tests (`test/*.e2e-spec.ts`). Default to the loop
described in the main workflow — write the test alongside or before the
implementation, not after:

- **Unit tests for services** — construct the service directly (via
  `@nestjs/testing`'s `Test.createTestingModule` or plain instantiation)
  with a fake/mock implementation of its repository interface. Because
  services depend on the repository *interface* (see
  [references/scaffold-guide.md](references/scaffold-guide.md)), this
  needs no database at all and runs fast enough to run on every save.
- **Integration tests for repositories** — run against a real MongoDB via
  `mongodb-memory-server` rather than mocking Mongoose itself; a mocked
  Mongoose model doesn't actually prove a query is correct.
- **e2e tests for controllers** — use Nest's `supertest` integration to
  hit real HTTP endpoints against a test module, catching wiring issues
  (DTO validation, guards, interceptors) unit tests skip over.
- **Transaction tests** — as covered in
  [references/mongodb-transactions-and-cache.md](references/mongodb-transactions-and-cache.md),
  use `MongoMemoryReplSet` (not the single-node `MongoMemoryServer`) since
  transactions need a replica set even in tests, and specifically assert
  the rollback path, not just the happy path.

Keep the test pyramid shape: many fast unit tests, fewer integration
tests, fewer still e2e tests. If every test in a module ends up being an
e2e test against a real database, that's a sign the service layer isn't
actually decoupled from the data layer yet.
