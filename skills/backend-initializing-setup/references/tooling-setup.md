# Linting and pre-commit hooks

Every scaffold gets a linter and a pre-commit hook wired in during Phase 5,
before the first feature is written — not added later once bad habits have
already been committed a dozen times.

## Node / TypeScript stacks (the default expectation)

```bash
npm install --save-dev eslint husky
npx eslint --init          # pick the config that matches the framework (Express/NestJS/etc.)
npx husky init             # creates .husky/ and wires the prepare script
```

Add a `pre-commit` hook (`.husky/pre-commit`) that runs lint (and ideally
the test suite, or at least the fast unit-test layer) before allowing a
commit:

```bash
#!/usr/bin/env sh
npx eslint . && npm test
```

Pair with `lint-staged` if the developer wants linting scoped to staged
files only on larger repos — worth asking about rather than assuming, since
it changes hook speed and behavior.

## Other stacks

ESLint and Husky are Node-specific tools. The *principle* — a linter plus a
pre-commit hook, always — carries over to every stack; the concrete tools
don't. Use the ecosystem-native equivalent instead of forcing Node tooling
onto a non-Node project:

- **Python** — `ruff` (or `flake8` + `black`) for linting/formatting, the
  `pre-commit` framework (`pre-commit-config.yaml`) for the git hook.
- **Go** — `golangci-lint`, invoked from a pre-commit hook via the
  `pre-commit` framework or a plain `.git/hooks/pre-commit` script.
- **Java / Kotlin** — Checkstyle or Spotless, wired into a Gradle/Maven
  pre-commit task or the `pre-commit` framework.
- **Ruby** — RuboCop, via `overcommit` or the `pre-commit` framework.

If the stack is something else entirely, or it's unclear which tool is
idiomatic for it, ask the developer rather than picking one silently — this
is exactly the kind of small, in-the-weeds ambiguity Phase 6 says to raise
instead of guessing at.
