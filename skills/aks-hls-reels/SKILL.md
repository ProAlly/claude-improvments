---
name: aks-hls-reels
description: Reusable architecture and implementation recipe for short-video "Reels" with HLS adaptive streaming — async upload, ffprobe validation, BullMQ + ffmpeg transcoding to 480p/720p/1080p m3u8 renditions, S3/local storage with CDN URLs, publish-after-ready, a ranked short video feed, watch-progress beacons, and hls.js/AVPlayer/ExoPlayer playback. Use when the user mentions HLS, reels, m3u8, ffmpeg, video transcoding, adaptive bitrate streaming, short video feed, TikTok/Instagram-style vertical video, video upload pipelines, or wants to add/port/debug/review a reels or video-processing feature in any project (derived from the Buzz backend).
user-invocable: true
---

# aks-hls-reels — HLS reels pipeline (Buzz-derived)

Reference design for uploading short videos, transcoding them to adaptive HLS in a
background worker, publishing only when ready, and serving a ranked feed.
Source: Buzz backend (NestJS + MongoDB + BullMQ + Redis). Stack-agnostic in idea;
adapt names to the target project. Do NOT trust any "REELS_ARCHITECTURE.md" in the
source repo (outdated) — this skill reflects the current code.

## Before applying
1. Read the target project's own conventions first (env access, date handling, storage abstraction, queue setup).
2. **Ask the user which Known gaps (below) to fix or include** rather than silently copying or silently fixing them.
3. State the **single-host assumption** (below) and confirm it fits their deployment.

## Pipeline

```
Client --multipart POST /app/posts (isReel=true, 1 video)-->  API
  API: sniff mime (file-type) -> stage to os.tmpdir()/buzz_staging/<id>
       -> ffprobe duration (<= MAX 30s, admin "reelLimits" flag)  [BEFORE any post exists]
       -> create post: unpublished, videoStatus=PENDING, pendingPublish (deferPublish)
       -> enqueue BullMQ queue `video-processing`, job `process-reel`,
          jobId `reel-<postId>`, attempts 3, exponential backoff 30s
       -> respond { postId, status: 'PENDING' }
Client polls GET /app/posts/:id until READY / FAILED

Worker (process-reel):  PENDING -> PROCESSING -> READY | FAILED   (idempotent)
  re-probe (backstop) -> for 480p,720p,1080p: ffmpeg -> <res>.m3u8 + <res>_%03d.ts
  -> write master.m3u8 -> thumb.jpg -> upload all files (concurrency 4)
  -> finalizeReel (hlsPlaylistUrl, thumbnailUrl, durationSeconds, READY)
  -> outbox event REEL_READY -> publishPending exactly once -> clean staging
  terminal failure -> mark FAILED + failure code + dead-letter + notify owner

Feed: GET /app/reels/feed (opaque cursor; ranking SCORING(reelScore) | RECENCY)
Watch: POST /app/reels/:id/mark-progress -> Redis accumulator (hash + `reel:progress:dirty` ZSET)
       eager flush to DB when accumulated watch > 60s, on completion, or forceFlush;
       else idle-sweep flush; view credit (24h lock) claimed at flush, only if watch >= 3s or completed
```

Key invariants:
- Validate (type, duration) BEFORE creating the post; reject bad input synchronously.
- Post is invisible (`pendingPublish`, `videoStatus` not READY) until the worker finishes; feed queries filter `videoStatus: { $nin: [PENDING, PROCESSING, FAILED] }` and `pendingPublish` absent.
- Job id `reel-<postId>` dedupes enqueue; state machine + `finalizeReel` guard make retries safe; publish side-effects fire once.
- Upload `master.m3u8` URL is what clients get; all segments are immutable per postId.

## Data model (post document)
`isReel`, `videoStatus` (PENDING|PROCESSING|READY|FAILED; indexed), `pendingPublish` (deferred publish payload), `hlsPlaylistUrl` (master), `thumbnailUrl`, `durationSeconds` (min 0), `reelScore` (number, default 0), failure reason/code field set together with status, `isHidden`.
Indexes: `{videoStatus, isHidden, createdAt:-1}` (recency) and `{videoStatus, isHidden, reelScore:-1, createdAt:-1}` (scoring).

## API
- `POST /app/posts` — multipart, `isReel=true`, one video → `{postId, status:'PENDING'}`.
- `GET /app/posts/:id` — poll status/URLs.
- `GET /app/reels/feed?cursor=` — opaque cursor; ranking mode SCORING or RECENCY.
- `POST /app/reels/:id/mark-progress` — watch beacon `{watchTimeMs (delta since last beacon, not cumulative), completed, forceFlush, beaconId?}`.
  - Redis hash `reel:progress:<postId>:<userId>` (HINCRBY) with ~10 min safety TTL (not the normal flush path); every beacon ZADDs `postId:userId` into `reel:progress:dirty` (score = last beacon time).
  - Flush eagerly when accumulated watchTimeMs > 60s, `completed`, or `forceFlush`; otherwise an idle reconciliation sweep (BullMQ processor) flushes dirty members with no beacon for IDLE_MS, so killed/backgrounded clients are still counted.
  - Unique-view credit: 24h lock `reel:view:<postId>:<userId>` (SET NX) claimed AT FLUSH time, only if flushed watch >= 3s or completed (a too-short visit does not burn the view).
  - Two-phase flush: (1) atomic Lua reads accumulator + conditionally claims the lock, deletes nothing; (2) after the DB bulk write succeeds, Lua clears accumulator + dirty entry. DB failure -> lock claim rolled back, next sweep retries.
  - Idempotent beacons: `beaconId` guarded by `SET NX EX 45` (`reel:progress:dedup:...`); duplicates are no-ops (client may resend on timeout).
- Failure codes: `REEL_TOO_LONG`, `INVALID_VIDEO_FORMAT`, `REEL_PROCESSING_FAILED`, `REEL_PUBLISH_FAILED`, `MEDIA_PIPELINE_UNAVAILABLE`.

## ffmpeg template (run once per rendition; H in 480|720|1080)
```
ffmpeg -i <input> \
  -vf scale=-2:H \
  -c:v libx264 -profile:v high -level:v 4.0 -pix_fmt yuv420p \
  -preset fast -crf 24 -g 120 -sc_threshold 0 \
  -force_key_frames "expr:gte(t,n_forced*4)" \
  -c:a aac -ac 2 -b:a 128k -ar 44100 \
  -f hls -hls_time 4 -hls_playlist_type vod -hls_list_size 0 \
  -hls_flags independent_segments \
  -hls_segment_filename <workDir>/<res>_%03d.ts \
  -max_muxing_queue_size 1024 -threads 1 \
  <workDir>/<res>.m3u8
```
Renditions: 480p (BANDWIDTH 800000, 854x480), 720p (2800000, 1280x720), 1080p (5000000, 1920x1080).
Master playlist:
```
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-INDEPENDENT-SEGMENTS
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=854x480,CODECS="avc1.640028,mp4a.40.2"
480p.m3u8
... (720p, 1080p)
```
Thumbnail: one frame at `min(1s, floor(duration/2))` (fallback 0.5s), `size ?x720`, `thumb.jpg`.
Node wrapper used: `fluent-ffmpeg` (`outputOptions`, `.screenshots`); `ffprobe` for duration. **ffmpeg/ffprobe must be installed in the runtime image.**

## Storage
- Driver selected by `STORAGE_DRIVER` = `local` | `s3`. Public URL base differs: `local` -> `STORAGE_LOCAL_PUBLIC_BASE_URL/<key>` (files under `STORAGE_LOCAL_PATH`); `s3` -> `CDN_BASE_URL/<key>` (bucket `AWS_BUCKET`).
- Keys: `app/{userId}/reels/{postId}_hls/{master.m3u8,<res>.m3u8,<res>_NNN.ts,thumb.jpg}`.
- Content types: `.m3u8` application/vnd.apple.mpegurl, `.ts` video/MP2T, `.jpg` image/jpeg.
- S3 `Cache-Control: public,max-age=31536000,immutable` (safe: keys are per-post, never overwritten).
- Upload files in bounded parallel batches of 4.
- CORS on the CDN/bucket must allow GET from the web origins (hls.js uses XHR/fetch).

## Env var names
`STORAGE_DRIVER`, `STORAGE_LOCAL_PATH`, `STORAGE_LOCAL_PUBLIC_BASE_URL` (local driver), `CDN_BASE_URL`, `AWS_BUCKET` (s3 driver), plus the project's existing S3 (region/credentials), Redis, and Mongo/DB settings; read via the project's env helper (Buzz: `getEnvByKey`). Never hard-code or commit values.

## Client playback
Web (hls.js ^1.7, lazy-loaded; Safari/iOS plays m3u8 natively so skip hls.js there):
```ts
const video = ref.current!;
if (video.canPlayType('application/vnd.apple.mpegurl')) {
  video.src = src;                       // Safari / iOS native
} else {
  const { default: Hls } = await import('hls.js');
  if (Hls.isSupported()) {
    const hls = new Hls();
    hls.on(Hls.Events.ERROR, (_e, d) => { if (d.fatal) /* show fallback */ ; });
    hls.loadSource(src); hls.attachMedia(video);
    // cleanup: hls.destroy()
  }
}
// <video muted playsInline loop poster={thumbnailUrl} />
```
Native: iOS `AVPlayer(url: masterURL)`; Android `ExoPlayer` with `MediaItem.fromUri(master)` (HlsMediaSource is auto-selected for .m3u8).
Feed UX: prefetch the NEXT item's master playlist (and poster), pause/destroy off-screen players, send mark-progress beacons while visible.

## Ops checklist
- ffmpeg + ffprobe present in image; verify `ffmpeg -version` in health check/boot.
- Worker concurrency sized to CPU (`-threads 1` per rendition; transcode is sequential per job); disk space for tmpdir: BOTH `os.tmpdir()/buzz_staging/<id>` (raw upload) and per-attempt `os.tmpdir()/reel_work/<postId>` (renditions + thumb), size for source + all 3 renditions per concurrent job; cleanup on success AND failure.
- Redis available (BullMQ + progress accumulators); alert on queue depth, failed/dead-letter jobs, PENDING posts older than N minutes.
- Pipeline unavailable (Redis/queue down) → respond with `MEDIA_PIPELINE_UNAVAILABLE` and do not leave orphan posts.
- Storage + CDN CORS and content types verified; `STORAGE_DRIVER=local` only for dev.
- Admin `reelLimits` flag documented; MAX duration 30s.
- Idempotency test: re-run a job; publish side-effects fire once.

## Assumption to state: single host
API and worker share the local filesystem (staging `os.tmpdir()/buzz_staging/<id>`; the worker's own `reel_work/<postId>` is worker-local and fine). If API and worker run on different hosts/containers, staging must move to shared storage (S3 raw upload key) — otherwise the worker cannot find the input.

## Known gaps (Buzz) — ASK the user which to include/fix; do not copy blindly
1. Legacy `POST /app/reels/upload` sends `rawVideoKey` but the worker reads `rawPath` → broken, never triggers publish side-effects. Don't port it; use the `/app/posts` path.
2. Soft-deleting a reel does NOT delete HLS objects (only account deletion does). Recommend `deleteByPrefix('app/{userId}/reels/{postId}_hls')` on delete.
3. No signed URLs (public, 1-year immutable cache). If content is private, use signed URLs/cookies (CloudFront) and shorter caching.
4. No source-resolution check: small sources are upscaled. Recommend skipping renditions taller than the source height (always keep at least the lowest).
5. Retry logs a harmless illegal PROCESSING→PROCESSING transition (cosmetic; allow it as a no-op).
6. Upload size: `/app/posts` uses `DynamicFileInterceptor`: 50 MB cap while admin `reelLimits` is on; when off, `video/*` is unlimited and fully buffered in memory (multer memory storage) -> OOM risk with concurrent large uploads (accepted by the Buzz product owner). Elsewhere: set an explicit `fileSize` limit and/or disk storage, and check the proxy body limit.
7. Vertical video vs master playlist: `scale=-2:H` fixes the HEIGHT, so a 9:16 source yields e.g. 270x480 / 405x720 / 608x1080 while the master hard-codes 854x480 / 1280x720 / 1920x1080 (wrong RESOLUTION). Recommend computing RESOLUTION from the actual rendition output (ffprobe the produced playlist/segment).
8. No bitrate cap: CRF 24 without `-maxrate`/`-bufsize`, so the advertised BANDWIDTH is not an upper bound as HLS expects. Recommend `-maxrate`/`-bufsize` per rendition (and BANDWIDTH >= peak).
