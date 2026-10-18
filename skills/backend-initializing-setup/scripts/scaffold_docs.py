#!/usr/bin/env python3
"""Create the docs/ skeleton and an initial spec.rp.md for a new backend project.

Never overwrites an existing spec.rp.md - that file is meant to be locked
once the developer confirms it (see SKILL.md Phase 3). docs/ files are
created only if missing, so re-running this is always safe.
"""
import argparse
from pathlib import Path

SPEC_TEMPLATE = """# Project Specification

> Status: DRAFT - awaiting developer confirmation
> Confirmed: <fill in date + how confirmed once approved>

## 1. Overview

One or two paragraphs: what this backend does and why it exists.

## 2. Goals

## 3. Non-Goals

## 4. Target Users / Clients

## 5. Tech Stack

- Language / runtime:
- Framework:
- Database:
- Other key infra (cache, queue, storage, etc.):

## 6. Data Model

## 7. API Surface (high level)

## 8. Auth & Authorization

## 9. Non-Functional Requirements

## 10. External Integrations

## 11. Open Questions

Must be empty before confirmation.
"""

DOCS_FILES = {
    "decisions.md": "# Decisions\n\nADR-lite log of choices made after the spec was locked.\n",
    "prompts.md": "# Prompts\n\nLog of significant instructions/requests given during the session.\n",
    "bugs.md": "# Bugs\n\nMinor bugs noticed in passing, with status: open | fixed | deferred.\n",
    "notes.md": "# Notes\n\nFree-form working notes.\n",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", default=".", help="Project root to scaffold into (default: current directory)"
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    spec_path = root / "spec.rp.md"
    if spec_path.exists():
        print(f"skip  {spec_path} (already exists - spec.rp.md is never overwritten)")
    else:
        spec_path.write_text(SPEC_TEMPLATE, encoding="utf-8")
        print(f"create {spec_path}")

    docs_dir = root / "docs"
    docs_dir.mkdir(exist_ok=True)
    for name, content in DOCS_FILES.items():
        path = docs_dir / name
        if path.exists():
            print(f"skip  {path} (already exists)")
        else:
            path.write_text(content, encoding="utf-8")
            print(f"create {path}")


if __name__ == "__main__":
    main()
