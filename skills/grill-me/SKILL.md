---
name: grill-me
description: Adversarially interrogate work that is already "done" — a feature, a fix, a design, a migration — hunting for what is wrong with it rather than confirming it is right. Use when the user says "grill me", "grill this", "poke holes", "red team this", "what did I miss", "challenge this", or asks for a hard/skeptical review of changes they or you just made.
user-invocable: true
---

# /grill-me — Adversarial review of finished work

The job is to **break the work, not to bless it**. Default review instincts
summarize and reassure; this skill exists because that failure mode is
invisible from the inside. Assume something here is wrong and go find it.

The hardest case is grilling your *own* work. You wrote it because you
believed it was right, so the belief and the code share the same blind
spots. Treat your own reasoning as the least reliable evidence in the room:
prefer what the code actually does, what the tests actually assert, and what
the data actually contains.

## Rules

1. **Verify, never recall.** Every claim gets checked against the file, the
   test output, or a query. "I made it idempotent" is a hypothesis until the
   code is read back. If you cannot verify a claim in this session, say so
   and mark it unverified rather than asserting it.
2. **A passing suite is not evidence of correctness.** It is evidence that
   the assertions that exist pass. Ask what the tests would *fail to catch*.
   Bugs live where no test looks.
3. **Attack the seams, not the center.** The happy path is what got written
   first and tested most. Failures cluster at boundaries: concurrency,
   partial failure, retries, rollback, empty and enormous inputs, zero and
   negative money, absent optional fields, legacy rows, clock skew,
   permissions, and every place two systems meet.
4. **Follow the state, not the code.** For anything touching money, records,
   or external side effects: what is written, in what order, what survives a
   crash between two writes, and what a second concurrent caller sees.
5. **Prosecute one finding at a time.** A finding is real when you can state
   the concrete inputs and the concrete wrong outcome. If you cannot, it is
   a suspicion — label it as one and move on. Do not pad the list.
6. **Say when it is fine.** A grilling that manufactures findings is as
   useless as one that finds nothing. If an area holds up under attack, say
   it holds up and say what you tried.

## Method

Work through these deliberately. Skip a lens only when it genuinely does not
apply, and say which ones you skipped.

- **Premise** — Does this solve the actual problem, or the problem as
  restated? Was the original diagnosis right? Could the fix be treating a
  symptom of something upstream?
- **Regression** — What worked before that might not now? Every changed
  default, widened filter, narrowed guard, and altered return type has
  callers. Enumerate them.
- **Concurrency** — Two callers, simultaneously. Which write wins? Can both
  pass the same check? Is anything non-transactional sitting between a check
  and its dependent action? Is any external, non-idempotent call reachable
  more than once?
- **Failure** — Kill the process between each pair of writes. What state is
  left, and can the system recover from it on its own?
- **Data** — What do *existing* rows look like? Schema defaults apply on
  read for absent fields, which silently converts "missing" into a real
  value. Does the migration cover every population, and is it idempotent and
  safe to re-run?
- **Boundaries** — Zero, negative, empty, null, absent, one-off-the-limit,
  and the largest plausible value. For money: rounding, currency precision,
  and float accumulation.
- **Contract** — Do the API, the types, the UI, and the docs still agree
  with the implementation? Is any comment now lying?
- **Reachability** — Can the new code path actually be reached in
  production, by a real user, with real data? Trace it end to end. Dead
  features pass tests happily.
- **Blast radius** — If this is wrong, what is the worst outcome, who
  notices, and how long until they do? Silent money loss ranks above a
  crash.

## Output

Lead with the answer, not the process.

- **Verdict** — one paragraph: does this hold up, and what is the single
  biggest risk?
- **Findings** — most severe first. Each one: what is wrong, where
  (`file:line`), the concrete failure (inputs → wrong outcome), and
  severity. Separate *confirmed* from *suspected*.
- **Held up** — what you attacked that survived, so the reader knows the
  coverage of the grilling.
- **Still unverified** — what you could not check here, and what it would
  take to check it.

Be blunt. Do not soften a real finding to be agreeable, and do not
apologize for the work under review — it is the work being judged, not the
author.
