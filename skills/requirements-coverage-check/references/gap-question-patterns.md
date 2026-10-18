# Phrasing the missed-vs-intentional question

## Name the thing, don't reference its number

Bad: "Was requirement 4 completed?"
Good: "Was the password-reset email flow built?"

The developer shouldn't have to go look anything up to answer. If the
requirement came from a long spec, restate it in one short plain-language
line as part of the question.

## Give the real options, not a yes/no

A flat yes/no loses the information this skill exists to capture — *why*
it's a no. Structure it as a choice among the actual possibilities:

```
Was the password-reset email flow built?

( ) Yes, it's done
( ) No — I decided to leave that out for now (on purpose)
( ) No — that should have been built, please do it
( ) Something else / let me explain
```

If using an interactive multiple-choice tool, this maps directly to one
question with those four options (the tool may add its own "Other" input
automatically — don't duplicate it if so). If presenting as plain text
instead, a short lettered list in the same shape works fine.

## Batch related items, don't dump a wall of questions

If several candidate gaps belong to the same feature or area, it's fine to
ask about them as separate questions within the same round rather than one
at a time — most interactive-question tools support a handful of questions
per call (commonly up to four). If there are more candidate gaps than fit
in one round, do a second round rather than cramming them together or
skipping some silently.

## Lead with a recommendation if there's a reasonable one

If Phase 2/3's evidence search found a strong signal (e.g. a related test
exists but nothing exercises this exact case, or a similar feature was
explicitly discussed and dropped earlier in the conversation), it's fine
to phrase the option order to reflect that — putting the most likely
answer first — as long as the other options are still genuinely available
and not just decoration. Don't invent a recommendation with no basis;
"unclear either way" is a fine framing when that's the honest state.

## Keep the tone neutral

This is an audit of coverage, not of the developer or of the agent's own
performance. "Was this built?" invites a plain answer; "did I mess up and
forget this?" invites defensiveness or over-explanation. Neutral framing
gets a faster, more useful answer.
