---
name: aks-fcm-webpush
description: Implement or review Firebase Cloud Messaging (FCM) web push and server-side sending for dashboards and apps (VGA standard, Sanad model). Use for "push notifications", "web push", "firebase messaging", "FCM", "firebase-messaging-sw.js", "service worker notifications", "VAPID key", "device token", "registration token", "sendEachForMulticast", "dead token pruning", "notification permission prompt", "duplicate notifications", or Arabic RTL push. FCM only; OneSignal is out of scope.
user-invocable: true
---

# aks-fcm-webpush - FCM web push + server send (VGA standard)

Reference implementation: Sanad (`Sanad/backend/src/modules/notifications/{push-sender,device-tokens}.service.ts`,
`Sanad/dashboard/src/lib/webPush.ts`, `public/firebase-messaging-sw.js`, `PushPrePrompt.tsx`).
Other projects drift from it; this skill lists the fixes. Full code: `references/client.md`, `references/server.md`.

**Never** open or commit service-account JSON, `firebase.credentials.*`, `.env`, or real keys/VAPID values. Use placeholders and env var NAMES only.

## Workflow
1. Detect state: grep for `firebase-messaging-sw.js`, `getToken`, `firebase-admin`, `deviceToken`. Compare against the checklist below; fix gaps, do not rewrite what already conforms.
2. Client: apply `references/client.md`. 3. Backend: apply `references/server.md`. 4. Run the test checklist.

## Client rules
- `firebase-messaging-sw.js` at the app root (scope `/`), served `Cache-Control: no-cache` (nginx: `location = /firebase-messaging-sw.js { add_header Cache-Control "no-cache"; }`).
- Public Firebase web config + VAPID public key come from env (`VITE_FIREBASE_*`), passed to the SW via the registration query string. Never hard-code in the SW.
- Pin SDK: the SW imports `firebase-*-compat.js` at the SAME version as the app (pass `SDK_VERSION` as `?v=`, validate with semver regex, fall back to a constant).
- Call `Notification.requestPermission()` / `getToken` ONLY after a user gesture, behind a pre-prompt UI explaining why. No `await` before `requestPermission()` in the click handler. Remember "dismissed" and "opted out" locally.
- `getToken(messaging, { vapidKey, serviceWorkerRegistration })`; empty string = wrong VAPID key for the project (report `no-token`).
- POST token to backend with `platform: 'web'`. Re-sync silently on app start / `visibilitychange` when permission is already `granted` (no prompt) so rotation and account switches are handled.
- Logout: DELETE token on backend (token in BODY) AND `deleteToken()` locally; do not persist opt-out on logout, only on explicit "turn off".
- Foreground: `onMessage` shows an in-app toast / bumps the inbox (FCM shows nothing when the tab is focused).
- Background handler MUST NOT call `showNotification` if `payload.notification` exists (browser already shows it; doing both duplicates). Only render data-only messages.
- `notificationclick`: close, read `data.url` (also `FCM_MSG.data`), accept same-origin only (simplification: Sanad's SW instead resolves the target via `push-routes.js` `resolvePushPath(data)` from `data.screen/type/entityId`; use that when routes are not plain URLs), focus an existing tab or `openWindow`. Register this listener BEFORE loading firebase-messaging-compat if you need `stopImmediatePropagation`.
- Arabic: for data-only rendering set `lang` and `dir` (`rtl` for `ar`) from `data.lang`.
- Guard everything: unsupported browser, no config, Safari private mode, non-HTTPS => hide the toggle, never throw.

## Backend rules
- Labels: items marked NEW are VGA-standard recommendations beyond what Sanad ships. Sanad itself stores `deviceTokens: string[]` (plain strings), its DTO has no `platform`, and its env keys are `FCM_PROJECT_ID`/`FCM_CLIENT_EMAIL`/`FCM_PRIVATE_KEY`.
- Storage (NEW vs Sanad): ARRAY of tokens per actor, each `{ token, platform: 'ios'|'android'|'web', lastSeen }`, max ~10 (keep newest). Never a single string field (Outlet/Letsplay overwrite = one device only).
- EXCLUSIVE claim: on register, first remove the token from every other actor in every collection (Sanad `releaseFromOthers`), then upsert on the caller. Prevents shared-device leakage.
- Routes (authenticated): `POST /notifications/devices {token, platform}`, `DELETE /notifications/devices {token}`. Token in the BODY, never in the URL path (leaks into logs; Amirni does this wrongly). Validate token length/type with a DTO.
- Send: `firebase-admin` NAMED app (`initializeApp(cfg, 'push-sender')`), creds from env NAMES `FIREBASE_PROJECT_ID`, `FIREBASE_CLIENT_EMAIL`, `FIREBASE_PRIVATE_KEY` (standard for new projects; Sanad uses `FCM_*`) (`.replace(/\\n/g, '\n')`) or one JSON env var / secret manager. If unset: log one warning, return zero stats, never fake success. Add credential files to `.gitignore` (Letsplay, Al Mudarib, Outlet committed them; Caffeine keeps one in docs/ - remove and rotate).
- `sendEachForMulticast` in chunks of 500. Payload = `notification` (localized per recipient: bucket recipients by language AR/EN, one send per bucket) + `data` (all values strings; `type`, `entityId`, `url`, `lang`) + `webpush: { headers: { TTL, Urgency, Topic: collapseKey }, fcmOptions: { link } }` (TTL/Urgency/fcmOptions.link are NEW, Sanad sends only `Topic`). Add `webpush.Topic`, android tag and apns-collapse-id ONLY when a collapseKey is set (never empty/undefined values: they can fail the whole message with invalid-argument).
- Check the user's notification preferences BEFORE sending. Enqueue (BullMQ/event/outbox) instead of sending inside the request path; no per-recipient N+1 awaits (Letsplay).
- Pruning: ONLY on `messaging/registration-token-not-registered` and `messaging/invalid-registration-token`. NEVER on `messaging/invalid-argument` (message-level: an oversized/bad payload fails every recipient and would wipe valid tokens; Buzz bug). Return `messageError` separately. Log per-token error code (Amirni only counts). A whole-chunk throw is transient: prune nothing.
- Optional topics: `subscribeToTopic` for broadcast segments; keep per-actor token arrays as source of truth for targeted sends.

## Mobile (iOS/Android)
Same endpoints with `platform: 'ios'|'android'`. iOS needs an APNs auth key uploaded in Firebase console and Push capability; Flutter uses `firebase_messaging` (`getToken`, `onTokenRefresh` -> re-POST, `onMessage`, `FirebaseMessaging.onBackgroundMessage`). Sanad and Caffeine Flutter apps have no FCM package yet.

## Out of scope
OneSignal (FitFinds; known bugs: tag userId vs external id mismatch, API key logged) - do not mix with this skill.

## Test checklist
- Permission denied: toggle shows guidance, no token POSTed, no crash. Dismissed pre-prompt not re-shown every load.
- Granted: token stored; push arrives in background (one notification, not two) and foreground (toast).
- Token refresh: delete token / clear site data, reload -> new token registered, old one pruned on next send.
- Logout: backend array no longer has token; `deleteToken` ran; no push after logout.
- Two accounts, one browser: A registers, A logs out/B logs in -> token only on B; push for A not received.
- Dead token: send to a fake/expired token -> pruned; send with 5KB payload -> NO tokens pruned, `messageError` logged.
- Arabic: AR user gets Arabic title/body, RTL rendering; EN user gets English.
- Click: opens/focuses same-origin `data.url`; cross-origin url ignored.
- Cap: registering the 11th token drops the oldest. SW cache: new SW deploy picked up (no-cache header).
- Missing env: server boots, logs one warning, sends nothing.
