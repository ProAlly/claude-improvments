# Manual verification checklist — template

Always hand this back at the end of a fix, filled in for the specific bug,
even when automated tests pass. Automated coverage proves the assertion
that was written; a human clicking through the actual behavior catches
things nobody thought to assert.

```markdown
## Manual verification: <short bug title>

**Setup**
1. <branch/build to use, any data, config, or feature flag needed>

**Confirm the original bug is gone**
1. <exact steps that used to trigger the bug>
2. Expected now: <what should happen instead>

**Check nearby behavior didn't regress**
1. <a related flow that shares code with the fix, worth a quick sanity check>

**Edge cases worth checking by hand**
- <boundary condition, empty/large input, permission edge case, etc. — anything the automated test didn't cover>
```

Keep it concrete and specific to the actual bug and code touched — a
generic "test the feature" checklist is not useful. Someone who has never
seen the bug report should be able to follow these steps and know whether
the fix worked.
