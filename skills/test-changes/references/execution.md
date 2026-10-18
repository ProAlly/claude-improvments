# Running things (only after Phase 3 approval)

## Find the project's own way of running tests/the app first

Before falling back to generic defaults, check for the project's own
conventions, in order:
1. A project-specific skill or documented command for launching the app
   (the same thing the `run` skill checks for first) — reuse it rather
   than reinventing a launch sequence.
2. `package.json` scripts (`test`, `test:unit`, `dev`, `start`),
   `Makefile` targets, a `justfile`, or a documented command in
   `README.md`/`CONTRIBUTING.md`.
3. Stack-appropriate defaults only if none of the above exist: `pytest`/
   `go test ./...`/`cargo test`/`mvn test`/etc. for the ecosystem present
   in the repo.

## Running the existing test suite

- Scope it to the affected area first if the repo is large or clearly
  split into packages/modules (faster feedback, less noise); widen to
  the full suite if the change touches something shared, or if the repo
  is small enough that scoping doesn't save meaningful time.
- Pipe verbose runners through a filter for failures — keep only the
  summary line (N passed/failed, timing) in the conversation when
  everything passes; keep full output only for actual failures, and only
  the relevant failing sections, not the whole log.
- A failing test that was already failing before this change (check via
  `git stash` + rerun, or just checking if it's in an unrelated area) is
  a different fact than a regression this change caused — say which one
  it is, don't just report a fail count.

## Exercising real use cases at runtime

Match the tool to what the change actually is:
- **Web UI change** — start the dev server (via the project's own
  command or the `run` skill's approach), then drive it with the
  browser tools available in this environment; walk through the golden
  path and the edge cases enumerated in Phase 2a, not just load the page
  and screenshot it.
- **API/endpoint change** — start the server, then hit the changed
  endpoint directly (curl, an HTTP client, or whatever the project
  already uses for this) with real payloads for each enumerated use
  case, including the malformed/edge-case ones.
- **CLI change** — run the command directly with the enumerated inputs.
- **Library/internal-function change with no natural entry point** — a
  quick throwaway script or REPL invocation is fine to exercise it
  manually; delete it afterward, don't leave scratch scripts in the
  repo.

## Reporting results

For each use case actually exercised, note pass/fail plainly — this
feeds directly into the Phase 6 use-case coverage table. If something
fails at runtime that static analysis (Phase 2) didn't catch, add it to
the bug list before writing the final report; don't report it only here
and lose it from the ranked findings.
