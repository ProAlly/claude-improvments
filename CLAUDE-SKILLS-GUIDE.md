# Claude Skills Guide (VGA `aks-` skills)

How to install and use the global skills in this folder. Skills live in `skills/`; the global `CLAUDE.md` rules are in `CLAUDE.md`.

## 1. Install (new machine)

Copy the folders into your global Claude skills directory and the rules file into `~/.claude`:

```bash
cp -r skills/aks-* ~/.claude/skills/
cp CLAUDE.md ~/.claude/CLAUDE.md   # only if you want the global rules too; back up the old one first
```

Windows global path: `C:\Users\<you>\.claude\skills`. Restart Claude Code (or open a new session) so the skills are listed.

## 2. How skills trigger

- **Automatic:** Claude loads a skill when your request matches its description (trigger words below).
- **Explicit:** type `/<skill-name>` (for example `/aks-fcm-webpush`) or say "use the aks-hls-reels skill".
- Skills are read-only guidance: they do not change code until you ask for the work.

## 3. The skills

| Skill | Use it for | Trigger words | Key rule it enforces |
|---|---|---|---|
| `aks-myfatoorah-deeplink` | MyFatoorah payments | MyFatoorah, KNET, checkout, payment callback | Always return the payer to the app by deeplink (Sanad pattern). Asks first whether a backend callback endpoint is wanted; no callback URLs unless you say yes. Status is re-verified server-side. |
| `aks-smsbox-built-url` | SMS through SMSBox | SMSBox, `sms_url`, Kuwait SMS | Backend builds the `Http_SendSMS` URL and returns it; dashboards and Flutter apps call it. Backend never calls SMSBox itself. |
| `aks-dreams-sms` | SMS through Dreams (dreams.sa) | Dreams SMS, `sendSmsOtp` | Server-side call with reply-code mapping and circuit breaker. No OTP bypasses. |
| `aks-nodemailer-smtp` | Sending email | Nodemailer, SMTP, OTP email | `secure` derived from port, pooling, always await/catch, escape HTML, no plaintext passwords. |
| `aks-hls-reels` | Short-video reels | HLS, reels, m3u8, ffmpeg | Current Buzz pipeline: upload, ffprobe, BullMQ + ffmpeg 480/720/1080, publish after ready. Lists known gaps to ask about. |
| `aks-buzz-scoring` | Ranking and scoring | scoring, ranking, leaderboard, trust score | Event-driven absolute recompute, all formulas, suspect and dead code listed separately. |
| `aks-fcm-webpush` | Push notifications | FCM, web push, VAPID, device token | Sanad model: service worker, token array with exclusive claim, prune only on token-level errors. |
| `aks-firebase-auth-tokens` | Social login and token lifecycle | Google/Apple login, `verifyIdToken`, custom token, revoke, logout all | Verify Firebase ID token, then issue your own JWT; rotation with reuse detection; full revocation matrix; 42-row no-gaps checklist. |

## 4. Example prompts

- "Add MyFatoorah checkout to the Vetrina backend." (the skill asks about the callback endpoint first)
- "Add OTP login by SMS using SMSBox for the new Flutter app; the dashboard will hit the built URL."
- "Wire Dreams SMS OTP into this NestJS backend."
- "Add an EmailService with Nodemailer for OTP and welcome emails."
- "Build the reels upload and HLS transcoding pipeline like Buzz."
- "Add a trending score for posts using the Buzz scoring pattern."
- "Add web push notifications to the admin dashboard."
- "Add Google and Apple sign-in with Firebase, plus logout-all and force-logout."

## 5. Things to know

- **Choose by provider:** SMSBox projects use `aks-smsbox-built-url`; Dreams projects use `aks-dreams-sms`. If unsure, Claude asks.
- **Labels in the skills:** `[VGA]` = existing practice, `[NEW]` = recommendation added by these skills, `[DOCS]` = checked against official docs, `[UNVERIFIED]` = check before relying on it.
- **Code samples are sketches:** never compiled or run. Placeholders (helpers, env values) are marked; no real credentials appear in any skill.
- **Skills document known bugs** in existing VGA projects (e.g. Sanad refresh-claim expiry, Fursatuk non-atomic rotation) so they are not copied into new work.
- **Related skills:** `aks-firebase-auth-tokens` links to `aks-fcm-webpush` (device-token cleanup on logout) and to the SMS skills (phone-OTP login).

## 6. Maintaining

- Edit the copy in `~/.claude/skills/<name>/`, then copy it back here so both stay identical.
- Keep each `SKILL.md` frontmatter `name` equal to its folder name.
- Re-check the `[UNVERIFIED]` items after real use and update the label.
- Larger references live in each skill's `references/` folder (`aks-buzz-scoring`, `aks-fcm-webpush`, `aks-firebase-auth-tokens`).
