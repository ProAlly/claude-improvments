# Buzz scoring formulas (verified at discovery time)

Helpers
- `clamp01(x)` = min(1, max(0, x))
- `logSat(n, c)` = clamp01(log10(1+n) / log10(1+c))  (log saturation at cap c)
- `sat(n, c)` in taste match = saturating count at cap c

## Post

**reachScore** = (likes*1 + comments*2 + 1) * 0.5^(ageHours/72)
- Dislikes, shares, saves, views NOT included.
- Decay applied only when recomputed (idle posts never decay).
- Index: `{tenantId, reachScore:-1, createdAt:-1}`

**contentQualityScore** = 100 * (0.30 media + 0.20 dishName + 0.20 placeLink + 0.15 description + 0.15 reportSafety)
- reportSafety = 1 - 0.5*openReports (clamped)

**reviewQualityScore** = 100 * (0.25 rating + 0.25 text + 0.20 media + 0.15 reviewerTrust/100 + 0.15 originality)
- text ramps linearly from 10 to 80 characters

**restaurantContentScore** = 0.25 freshness + 0.25 contentQ + 0.20 saveShare + 0.20 reviewQ + 0.10 visual

**reelScore** (delta-based, accumulates): += completionCount*100 + watchTimeMs*0.1 + viewCount*0.5
- Index: `{videoStatus:1, isHidden:1, reelScore:-1, createdAt:-1}`
- Suspect scale, see SKILL.md section 3. `updateReelScore` has no callers; real writes are in posts.repository.ts (~511-563).

## Place

**rankScore** = 100 * (0.35 clamp01(avgRating/5) + 0.25 logSat(reviews,500) + 0.25 logSat(visits,5000) + 0.15 logSat(followers,2000))
- Weights tenant-overridable via `scoring_weights` row `place_rank`, 60s Redis-backed cache (`CacheService.wrap`).
- Stored with `scoreBreakdown`.

## Dish (menu_items)

**popularityScore** = 100 * (0.7 clamp01(avgRating/5) + 0.3 logSat(ratingCount,200))

## User trust

**trustScore** = clamp(round(100 * (0.2 profileCompleteness + 0.2 verified + 0.2 activityNormality + 0.2 reviewQuality + 0.2 reportSafety) - penalties), 0, 100). Default 50.

Penalties: multipleReports 30, fakeLookingProfile 10, others 15-20.
Inputs (scoring.repository.ts `getUserTrustSignals`): reportSafety = max(0, 100 - 20*openUserReports); multipleReports = reportCount >= 2; fakeLookingProfile = profileCompleteness <= 25 (4 fields: avatar, bio, city, fullName) AND not verified, which also sets activityNormality to 30 (else 100).
User `invitationQualityScore` is separate: InvitationQualityScorer, `recomputeInvitationQuality`.
Abuse flags tooManyRatings / copiedComments / excessiveLikes / suspiciousInvitation are hardcoded false.

Bands: >=80 FULL, >=60 NORMAL, >=40 LIMITED, >=20 RESTRICTED, else HIDDEN.
Gating threshold: 40 (`global_config.trustThreshold`).

## Friends feed (FeedRankingScorer)

Weights: taste 0.25, social 0.20, engagement 0.20, contentQ 0.15, freshness 0.10, location 0.05, trust 0.05.
(taste hardcoded 0, dislikes 0, relationship fixed to 'followedFriend' by callers today.)

Freshness steps by post age: <=24h 100, <=72h 80, <=168h 60, <=336h 40, <=720h 20, else 10.

## Discovery (DiscoveryScorer)

Weights: taste 0.30, velocity 0.25, contentQ 0.20, sameCity 0.10, trust 0.10, freshness 0.05.

Velocity points: save +5, share +5, comment +3, like +1, dislike -2, report -10.
velocityScore (0-100) = min(100, 20 * max(0, sum) / max(1, ageHours)).
Publisher trust < 40 => discovery score 0.

## Taste match (modules/discovery/taste-match.scorer.ts)

Weights: sharedRestaurants 0.25 (sat 6), sharedCuisines 0.25 (sat 4), similarRatings 0.20, sharedSaved 0.15 (sat 6), sameCity 0.10, mutualFriends 0.05 (sat 8).
Multiplied by trust multiplier: trust >=80 1.0, >=60 0.85, >=40 0.6, else 0.

## Vendor leaderboard (on demand, not stored)

score = 1*visits + 4*reviews + 0.5*(likes + comments) + 3*follows

## Event routing (queues/event-fanout.processor.ts)

| Event | Recompute |
| --- | --- |
| POST_CREATED / POST_HIDDEN / POST_UPDATED | post + place |
| LIKED / UNLIKED / DISLIKED / COMMENT_ADDED | post |
| VISIT_CREATED | place + user trust |
| PLACE_FOLLOWED etc. | place |
| USER_INVITE_USED | user trust |
| REEL_READY | post |
| POST_VIEWED | none |

Handlers write absolute values (idempotent retries). BullMQ concurrency base 4, scaled by CPU cores (`concurrencyFor`); failures go to `failed_jobs`.

## Other indexes / fields
- `places.rankScore` + `scoreBreakdown`, `menu_items.popularityScore`, `users.trustScore`
- Dedup: unique indexes on likes / bookmarks / follows; per-event fanout ids.
