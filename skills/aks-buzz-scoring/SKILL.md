---
name: aks-buzz-scoring
description: Scoring and ranking architecture of the Buzz backend (NestJS + MongoDB + BullMQ), reusable for any review/feed/leaderboard app. Use when working on or designing scoring, ranking, rank score, reach score, trending, popularity, leaderboard, feed algorithm, friends feed, discovery feed, taste match, trust score, content quality, review quality, reel score, event-driven score recompute, or "how does Buzz rank posts/places/dishes". Covers the event -> queue -> absolute recompute -> indexed field -> feed sort pattern, all formulas and weights, known suspect formulas, and dead code not to copy.
user-invocable: true
---

# aks-buzz-scoring - Buzz ranking architecture

Source of truth: `Buzz\buzz-backend\src\modules\scoring\*` (scoring.service.ts,
scoring.constants.ts, quality.scorers.ts, user-trust.scorer.ts,
feed-ranking.scorer.ts, discovery.scorer.ts, restaurant-page.scorer.ts,
scoring.processors.ts), `queues\event-fanout.processor.ts`,
`modules\discovery\taste-match.scorer.ts`, `modules\posts\posts.repository.ts`
(reelScore), `modules\analytics\analytics.constants.ts`.
This skill was written from a verified discovery pass; re-check the file
before relying on an exact number, since code may have moved.

All formulas, weights and bands: `references/formulas.md`.

## What is scored

| Entity | Field | Meaning |
| --- | --- | --- |
| Post | reachScore, contentQualityScore, reviewQualityScore, restaurantContentScore, reelScore | feed reach, quality, reel engagement |
| Place | rankScore (+ scoreBreakdown) | restaurant ranking |
| Dish (menu_items) | popularityScore | dish ranking |
| User | trustScore (0-100, default 50) | gating + feed/discovery multiplier |
| User | invitationQualityScore | invite quality (InvitationQualityScorer, `recomputeInvitationQuality`, run on USER_INVITE_USED) |
| Vendor leaderboard | computed on demand, not stored | visits/reviews/engagement/follows |

## 1. Applying the pattern in a new project

event -> queue -> absolute recompute -> indexed field -> feed sort

1. **Event**: emit a domain event on every action that changes a score input
   (created, liked, commented, visited, followed, hidden...). Give each
   event a stable fanout id so duplicates dedupe.
2. **Routing table** (one place): event type -> which entities to recompute
   (e.g. LIKED -> post; VISIT_CREATED -> place + user trust;
   POST_VIEWED -> none). Keep it declarative; unknown events are no-ops.
3. **Queue** (BullMQ): one processor per entity type, low concurrency (Buzz: base 4, scaled with CPU cores via `concurrencyFor` in `queues/bullmq.constants.ts`; env override `BULLMQ_CONCURRENCY_<QUEUE>`),
   failures persisted to a `failed_jobs` collection for replay.
4. **Absolute recompute**: handler re-reads inputs and writes the full score
   value (`$set`), never `$inc` of a delta. This makes retries and duplicate
   deliveries idempotent. (Exception in Buzz: reelScore is delta-based, see
   known issues.)
5. **Store on the document** with a compound index that matches the feed
   query, e.g. `posts {tenantId, reachScore:-1, createdAt:-1}`. Keep a
   `scoreBreakdown` on places for debugging.
6. **Feed sort**: query by the indexed score, then optionally re-rank a
   candidate page in memory with a multi-signal scorer (taste, social,
   freshness, trust). Add a "newest" pool so idle/new content still surfaces.
7. **Tunable weights**: store weights in a DB row (Buzz: `scoring_weights`,
   key `place_rank`, 60s Redis-backed cache via `CacheService.wrap`) with code defaults as fallback.
8. **Dedup inputs** with unique indexes (likes, bookmarks, follows) so a
   replayed event cannot inflate counts.
9. **Trust gating**: low-trust publishers are suppressed in discovery
   (threshold 40, `global_config.trustThreshold`).

## 2. Formula reference

See `references/formulas.md` (reach, place rank, dish popularity, content /
review / restaurant-content quality, user trust and bands, friends-feed and
discovery weights, taste match, reelScore, vendor leaderboard).

## 3. Known issues / suspect (flag, do not silently fix)

- **reelScore scale looks unintended**: per delta it adds
  `completionCount*100 + watchTimeMs*0.1 + viewCount*0.5`. At 0.1 per
  millisecond, 10 s of watch time (1000 pts) equals 10 completions. Likely
  meant seconds or a smaller factor. Report to the user; do not change it
  without confirmation.
- **reachScore decays only at write time**: the 72h half-life is applied when
  the score is recomputed (on an event). An idle post never decays, so old
  posts with past engagement keep their reach. Compensated by a "newest"
  pool in the feed, not fixed in the score. A periodic decay job or
  query-time decay would fix it.
- reachScore ignores dislikes, shares, saves and views (only likes*1 +
  comments*2 + 1).

## 4. Dead or inactive code (do not copy)

- `TRUST_SCORING` constant: unused.
- `getFeedRankWeights` / `feed_weights`: unused.
- Seed rows `feed_post` and `trust_score` weights: never read.
- `updateReelScore`: no callers.
- `tasteSimilarityScore` is hardcoded 0 in the feed and discovery callers
  (`discovery.service.ts` ~497, ~528), so the taste weights of
  `FeedRankingScorer` / `DiscoveryScorer` are effectively dead. (`TasteMatchScorer.compute`
  itself IS used, in `discovery.service.ts` ~275 for "who to follow" suggestions.)
- Callers also hardcode `dislikes: 0` and `reports: 0` (`discovery.service.ts`
  ~504, ~534-535): the discovery velocity weights for dislike (-2) and report
  (-10) and the feed dislike weight (-20) are dead. The friends feed fixes
  `relationshipType: 'followedFriend'`.
- Trust abuse flags hardcoded false: `tooManyRatings`, `copiedComments`,
  `excessiveLikes`, `suspiciousInvitation`.
- `SCORING_FEED` queue handler: no-op.
- Feed ZSET cache: disabled.

Check with grep that these are still dead before reusing or deleting.

## 5. Test gaps

Specs exist for quality scorers and scoring.service (plus a mongo spec for
review-post rating). No dedicated specs for the feed-ranking, discovery,
restaurant-page or user-trust scorers. Add table-driven tests (boundary of
each band/step, zero inputs, trust<40 => discovery 0) before changing them.

## Working rules

- Treat numbers in `references/formulas.md` as a map; open the source for the
  exact current constants before quoting them to the user.
- When adapting to another app, copy the pipeline and the shape of the
  formulas, not the dead code in section 4.
