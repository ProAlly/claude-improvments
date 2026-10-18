# Inventory and chunking

## Building the file list

Prefer, in order:

1. **Git repo:** `git ls-files` for tracked files, plus
   `git ls-files --others --exclude-standard` to catch untracked-but-not-
   ignored files (new work in progress). This gets `.gitignore` exclusion
   for free — no need to hand-filter `node_modules`, `dist`, `.venv`, etc.
2. **No git:** `Glob` with an explicit exclusion pass. Exclude directories
   named `node_modules`, `dist`, `build`, `out`, `target`, `vendor`,
   `.venv`, `venv`, `__pycache__`, `.next`, `.nuxt`, `coverage`, and any
   `*.min.js`, lockfiles (`package-lock.json`, `yarn.lock`, `Cargo.lock`,
   `poetry.lock`, etc.), and binary/image/font assets.

## What stays in scope vs. out

**In scope** (read these — bugs live here):
- All hand-written application source in every language present.
- Database migrations and schema files — transaction/constraint bugs
  live here.
- Infra-as-code (Terraform, k8s manifests, Dockerfiles) if present —
  architectural and correctness issues apply there too, just ask the
  user if they want that included when it's a large fraction of the repo.
- Config files that encode logic (not just static key/value settings) —
  e.g. a routing table, a feature-flag rules file.

**Out of scope** (skip — no signal, wastes chunk budget):
- Anything generated (protobuf/GraphQL codegen, ORM-generated migration
  snapshots that mirror a schema file already in scope, bundled/minified
  output).
- Vendored third-party code living in the repo (`vendor/`, `third_party/`).
- Pure data files (fixtures, seed data) unless the user specifically asks
  about data integrity in them.
- Test files can stay in scope if the repo is small enough to afford it,
  but on a large repo, deprioritize them below production source — a bug
  in a test is lower-severity than the same bug in the thing it's
  testing. Use judgment; don't spend a whole chunk's budget on tests
  while production code goes unreviewed.

## Sizing and grouping chunks

- Group by **top-level package or directory**, not by an arbitrary line
  count — a subagent reviewing `src/billing/` needs to see the whole
  billing module's files together to catch cross-file issues (e.g. a
  transaction opened in one file and committed in another).
- Rule of thumb per chunk: **~40-60 files or ~3,000-4,000 total lines**,
  whichever comes first. This comfortably fits a subagent's context with
  room to actually reason about what it read, not just skim it.
- If one directory is bigger than that, split it by subdirectory rather
  than by an arbitrary file cutoff — keep a file with its closely related
  siblings (a controller with the service/repository it calls, if all
  three are small) instead of splitting a cohesive unit in half.
- If the whole repo is small (under ~50 files total), one chunk is fine —
  don't manufacture parallelism where it doesn't help.
- Report the final chunk count and per-chunk file count to the user
  before spawning, as the one-line scope summary Phase 1 asks for.
