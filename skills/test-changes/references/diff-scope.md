# Resolving the diff scope

The rule: **everything committed on this branch since it diverged from
base, plus whatever's still uncommitted (staged and unstaged).** One
diff, one review — don't treat committed and uncommitted as separate
passes.

## 1. Find the base branch

Try, in order, until one works:

```bash
git symbolic-ref refs/remotes/origin/HEAD --short   # e.g. origin/main
```

If that's not set (common on a fresh clone or local-only repo), check
for the usual candidates in order, using whichever exists:
`main`, `master`, `develop`, `trunk`. If more than one exists and it's
not obvious which is the real base, ask the user rather than guessing —
diffing against the wrong base silently changes what gets reviewed.

If the current branch *is* the base branch (working directly on main,
no feature branch), there's no branch history to include — fall back to
just the working tree: `git diff HEAD` (plus untracked files, below).
Say so, don't silently pretend there's a merge-base.

## 2. Compute the diff

```bash
BASE_REF=$(git merge-base <base-branch> HEAD)
git diff "$BASE_REF"
```

`git diff <commit>` compares the working tree (including staged and
unstaged changes) against that commit — this single command already
covers "committed on this branch" + "uncommitted right now" in one diff.
Don't use three-dot (`git diff base...HEAD`) for this — that only shows
committed history and drops uncommitted work.

## 3. Catch new untracked files

Plain `git diff` never shows untracked files (new files not yet
`git add`ed). Find them separately and treat them as fully new:

```bash
git status --porcelain | grep '^??' | cut -c4-
```

Read each one in full — there's no "diff" for a brand-new file, the
whole thing is the change.

## 4. Build the file inventory

Combine the diffed files and the untracked files into one list. For each,
note: new file vs. modified, and roughly what changed (new function,
modified behavior, config, test file). This is the list Phase 2 of the
skill works from.
