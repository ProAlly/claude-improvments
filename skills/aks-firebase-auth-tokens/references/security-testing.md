# G. Security checklist, dev/test, monitoring + H. Known VGA gaps + doc sources

## G1. Security checklist
- [ ] Backend receives and verifies a Firebase ID token (or provider token in Pattern 2) on EVERY social login. No endpoint creates/logs in a user from client-supplied email/uid/loginType.
- [ ] Named admin app, explicit `projectId`; credentials from env / secret manager only; credential files gitignored; any key ever committed is ROTATED (deleting from git history is not enough).
- [ ] Fail closed: missing config, Firebase network / certificate-fetch error, Redis down on admin routes -> deny (503/401), never allow.
- [ ] Provider allow-list; `email_verified` before email linking; role never from client; link conflicts return 409, never overwrite or crash (backend-nestjs.md E3).
- [ ] Separate secrets for access vs refresh and per actor; no fallback/default secrets (`process.env.X || 'secret'`); boot fails if missing; secrets >= 32 random bytes.
- [ ] Refresh tokens stored hashed, rotated atomically with `expiresAt > now` in the claim filter, reuse (revoked + unexpired) => revoke all; per-device sessions.
- [ ] Access TTL short and `expiresIn` from config (seconds); guard re-checks user state (DB / tv / second-floored timestamp / Redis) and the `sid` session.
- [ ] Server-side logout and logout-all exist and are called by clients; client logs out only on dead-session codes, not on network errors.
- [ ] Logout-all / ban / force-logout / compromise / deletion also revoke Firebase refresh tokens and FCM tokens via `clearAll` (revocation.md D4).
- [ ] `checkRevoked` on login exchange, `/auth/link` and sensitive Firebase-token endpoints.
- [ ] Rate limits on `/auth/*` (incl. OTP per phone); audit log without tokens/OTPs; no tokens in URLs or logs (also not `console.log(req.body)` on auth routes - FitFinds logs the social-login body).
- [ ] Apple: nonce used; Apple refresh token stored encrypted at sign-in; account deletion (user AND admin) revokes Apple tokens; deletion requires recent auth; Apple server-to-server notifications handled (account-flows.md J3/J4).
- [ ] Unlink cannot remove the last login method (atomic guard, account-flows.md J1).
- [ ] OTP / verification paths fail closed (no OTP echo, no fixed bypass codes in prod - G2).
- [ ] CORS restricted to known origins when cookies are used.

## G2. Dev bypass and environments
- Dev bypass tokens (Cozzy `dev:<email>:<name>:<provider>` when `ENVIRONMENT=development` AND `DEV_AUTH_BYPASS`) must never ship: prefer the **Firebase Auth emulator** instead. If a bypass exists: (a) double gate (env + flag), (b) startup assertion that throws if the flag is set while `ENVIRONMENT != development`, (c) CI check that the prod config/image has the flag unset, (d) never rely on a default `ENVIRONMENT` value of `development`.
- **OTP bypasses count as auth bypasses** - same "no bypass in prod" checks (a)-(d), plus a prod smoke test that `POST /auth/otp/request` returns no `otp` field:
  - Buzz flags (from skill `aks-dreams-sms`): `TEMP_OTP_ENABLED`, `TEMP_OTP_APP`, `TEMP_OTP_MERCHANT` (fixed codes accepted for any phone when enabled) and `EXPOSE_OTP_IN_RESPONSE` (OTP returned in the API response). Assert all are unset/false in production at boot and in CI.
  - Al Mudarib OTP echo (verified read-only, `src/modules/auth/auth.service.ts` ~145-185 `isOtpEchoAllowed()` / `otpEcho()`): the OTP is echoed in responses whenever `OTP_DELIVERY_ENABLED !== 'true'`, so an unset or mistyped variable FAILS OPEN (anyone who knows a phone number gets its OTP). Fix: echo only when an explicit dev flag is `true` AND the environment is development; assert at boot that delivery is enabled in production.
  - App-store reviewer accounts: one fixed phone only, explicit flag, logged use, never a wildcard code (aks-dreams-sms rule 7).
- Emulator: `firebase emulators:start --only auth`; backend sets `FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099`. With that variable set, the Admin SDK accepts UNSIGNED ID tokens and session cookies, and Firebase warns not to set it in production [DOCS emulator connect_auth] - so assert at boot that it is unset in prod (backend-nestjs.md E1). Flutter `FirebaseAuth.instance.useAuthEmulator('localhost', 9099)`; web `connectAuthEmulator(auth, 'http://127.0.0.1:9099')`. Emulator REST lets tests create users and fake Google/Apple sign-ins.
- Separate Firebase projects per environment (dev/staging/prod); `aud` check then naturally rejects cross-env tokens.

## G3. Test list (unit + integration; Jest e2e or pytest)
Firebase verification:
1. valid Google token -> 200, user created, `isNewUser=true`; second call -> same user, `isNewUser=false`.
2. valid Apple token, first login with name hint -> name saved; second login without name -> name unchanged; `appleSub` stored.
3. expired ID token -> 401 `TOKEN_EXPIRED`.
4. revoked (after `revokeRefreshTokens`, token iat before revocation) with checkRevoked -> 401 `TOKEN_REVOKED`.
5. disabled Firebase user -> 403 `ACCOUNT_DISABLED` (checkRevoked surfaces `auth/user-disabled`); disabled in our DB -> 403.
6. token from another project (wrong `aud`) / garbage string / empty -> 401 `TOKEN_INVALID`.
7. `sign_in_provider` = `password`/`anonymous`/`phone` (when phone runs through our OTP) -> 400.
8. existing account with same email, `email_verified=false` -> NOT linked (new account without `email`, or 409 per policy).
9. existing staff/admin account with same email -> 409 `ACCOUNT_ROLE_CONFLICT`, no token.
10. concurrent first login (2 parallel requests) -> exactly one user row; exactly one response has `isNewUser=true`; no 500.
11. Firebase not configured -> 503, no user created; Python: cert fetch failure -> 503.
12. email account already bound to a DIFFERENT firebaseUid (simulate Firebase deleteUser + re-signup) -> 409 `ACCOUNT_LINK_CONFLICT`, no TypeError, no overwrite.
13. password-based unverified account with same email -> 409 `LOGIN_WITH_PASSWORD_TO_LINK`.
14. soft-deleted then anonymised account -> same Google identity can sign up again (new row).
Own tokens:
15. refresh rotates: old refresh -> 401 afterwards.
16. replayed (already rotated, unexpired) refresh outside grace -> 401 AND all sessions of the actor revoked AND reuse audit event AND `clearAll` called.
17. **expired** refresh presented twice -> 401 both times, row NOT marked revoked by the first call, NO revoke-all (regression for the Sanad bug).
18. two parallel refreshes with same token -> exactly one succeeds (atomic claim); with grace configured, behaviour matches the documented choice.
19. refresh for disabled/deleted user -> 403.
20. logout -> refresh unusable AND the access token of that session rejected (`SESSION_REVOKED` via `sid`); logout twice -> 204 (idempotent); logout removes this device's FCM token server-side.
21. `DELETE /auth/sessions/:id` -> that session's access token rejected on the next request; other sessions unaffected; foreign id -> 404.
22. access token issued after rotation (old session row `revokeReason='ROTATED'`) still in flight -> accepted until expiry (no false `SESSION_REVOKED`).
23. logout-all -> all refresh rows revoked, access tokens issued before rejected (tv/timestamp/Redis), Firebase `revokeRefreshTokens` called (mock), FCM `clearAll` called.
24. password change -> other sessions dead; the NEW pair returned in the same second is accepted (timestamp floored to seconds or `tv++`).
25. admin force-logout / ban -> same as 23 plus login blocked.
26. access token with wrong `aud` (user token on admin route) -> 401; with wrong secret -> 401; access token used as refresh -> 401.
27. role downgrade -> next request sees new role (DB-backed guard) or rejected (tv bump).
28. `expiresIn` in response is a number of seconds equal to the configured TTL.
Account flows (account-flows.md J):
29. `POST /auth/link` with a Google identity already used by another account -> 409 `PROVIDER_ALREADY_LINKED`; phone-only account links Google -> `firebaseUid` set, later Google login returns the same account.
30. unlink the only login method -> 409 `LAST_LOGIN_METHOD`; two parallel unlinks of the last two methods -> exactly one succeeds.
31. OTP verify -> same token pair shape as social login; wrong code x N -> locked; `otp` absent from responses with prod config.
32. Apple notification with a bad signature -> 400, no change; `consent-revoked` -> sessions revoked + `clearAll`; `account-delete` -> deletion flow; duplicate delivery -> processed once.
33. admin deletion of an Apple user with stored token -> Apple `/auth/revoke` called (mock) before `deleteUser`; without stored token -> `appleRevokePending` audited.
Claims / custom tokens (if C1/C2 used):
34. `createCustomToken`: uid > 128 chars -> `auth/invalid-uid`-style error; a reserved claim (e.g. `sub`, `firebase`) in `developerClaims` -> argument error (not `auth/reserved-claims`); our own size guard rejects claims > 1000 bytes before calling the SDK (the SDK documents no limit for custom-token claims).
35. `setCustomUserClaims`: payload > 1000 bytes -> `auth/claims-too-large`; reserved claim -> `auth/reserved-claims`.
36. claim propagation: after `setCustomUserClaims`, old ID token lacks claim; after `getIdToken(true)` claim present (emulator).
Client:
37. 5 parallel 401s -> exactly one `/auth/refresh` call; all 5 retried once.
38. refresh answered 401 `REFRESH_INVALID` -> local logout, login screen; refresh fails with a NETWORK error -> tokens kept, error surfaced, no logout; 403 -> no refresh loop.
39. 401 on `/auth/logout-all` or `/auth/sessions` -> refresh + retry happens; 401 on `/auth/refresh` / `/auth/social` / `/auth/logout` -> no refresh attempt.
40. logout clears secure storage, FirebaseAuth currentUser null, GoogleSignIn signed out, FCM `disable()` ran (stored token cleared, `deleteToken` called).

## G4. Monitoring
- Metrics/alerts: count of `REFRESH_REUSE` events (alert on spikes or any for admins), social login failure rate by code, 503 `AUTH_PROVIDER_UNAVAILABLE`, `ACCOUNT_LINK_CONFLICT` rate, OTP verify failures/lockouts per phone, Apple notification events, rate-limit hits, force-logout/ban actions.
- Dashboards show sessions per user (detect abnormal device counts).
- Track Firebase Admin key age and Apple .p8 key age; rotate on schedule and on staff changes. Alert on server clock drift (backend-nestjs.md E7).

## H. Known VGA gaps - do not copy
| Project | Gap | Correct pattern |
| --- | --- | --- |
| FitFinds | `/social-login` (api.fitfind.com `user.controller.js` `socialLogin`) trusts client `name/email/phone/loginType`, no provider token verified; Flutter app never sends the idToken => account takeover by email. Also logs the request body. [verified read-only] | B5/B7: send + verify Firebase ID token |
| Outlet | Links existing account by email without `email_verified` (`firebase-auth.service.ts`); default (unnamed) admin app; single `refreshTokenHash` per user = one device. [verified]. `apps/api/src/config/firebase.credentials.ts` is tracked in git (`git ls-files`) - contents not opened [verify content before claiming exposure] | B8 + named app + per-session rows; if the file holds a key: env + rotate |
| Sanad | Rotation claim filter lacks `expiresAt` -> expired token is claimed, then a retry triggers revoke-all (`token.service.ts` ~79-95) [verified read-only]. Otherwise the reference model. | revocation.md D3.1 / backend-nestjs.md E4 fix |
| Cozzy space | Dev bypass `dev:<email>:...` in `firebase_service.py` (env + flag gated) [verified]; access and refresh signed with the same secret distinguished by type claim; logout client-side only. Good: `tv`/tokenVersion check [verified]. | G2 assertions; separate secrets; server logout |
| Letsplay, CareLink | Access + refresh share the same key; no server-side logout | C3, D1 |
| caffeine-app | `tokensInvalidBefore` set only on phone change, not on logout; no server-side logout; service-account JSON sitting ungitignored in docs | D3.3 on all events; remove + rotate key |
| Al Mudarib | `expiresIn: 86400` hardcoded in `src/modules/user/user.model.ts` (`User.token()` ~247 and `refreshToken()` ~285) while the JWT is signed with `env.JWT_EXPIRES_IN` [verified read-only]; OTP echo fails open when `OTP_DELIVERY_ENABLED` is not `'true'` (`auth.service.ts` ~155) [verified]; `src/config/firebase.credentials.ts` is tracked in git (`git ls-files`) - contents not opened [verify content before claiming exposure]. Good: guard re-loads user + `sessionInvalidatedAt` [verified]. | C3 config-derived TTL; G2 OTP rule; env creds (rotate if a key is in the file) |
| Letsplay | committed `firebase-credentials.py` | env/secret manager; rotate |
| Amirni | Dashboard JWT subjects trusted without DB lookup (stale roles); hardcoded fallback secrets | D3.6; boot-fail on missing secret |
| CareLink | Default weak `SECRET_KEY` | boot-fail, 32+ random bytes |
| Vetrina | One stored refresh hash per user => single session | per-session rows |
| Buzz | Refresh = signed JWT whose SHA-256 is swapped in place atomically (good), but NO revoke-all on reuse - a replayed rotated token only gets 401 `REFRESH_REVOKED` (`auth.service.ts` ~226-243) [verified read-only] | D3.1 reuse => revoke all (needs revoked rows kept instead of swapped away) |
| All Firebase projects | `verifyIdToken` without `checkRevoked`; no `revokeRefreshTokens` anywhere | D2 |
| Fursatuk | (a) Rotation is NOT atomic: `findOne` -> `record.revoked` check -> `issueTokenPair` -> `record.save()` (`services/token.service.ts` ~96-150), so two parallel refreshes with the same token can both mint pairs; (b) 30s reuse grace issues a NEW pair (attacker inside the window also succeeds); (c) response `expiresIn` is the config string (e.g. `'15m'`), not seconds (~92) [verified read-only] | (a) atomic claim (D3.1); (b) D3.2 + client single-flight; (c) C3 seconds |
Gaps not marked [verified] come from the earlier discovery pass and were not re-read in this skill's authoring session.

## Doc sources (checked 2026-10-15)
- https://firebase.google.com/docs/auth/admin/create-custom-tokens - uid 1-128 chars, reserved claim names, 1h custom token expiry, `signBlob` permission, Service Account Token Creator, IAM API must be enabled (troubleshooting); no claims size limit documented for custom tokens.
- https://firebase.google.com/docs/auth/admin/custom-claims - 1000-byte limit, overwrite semantics, propagation, `getIdToken(true)`.
- https://firebase.google.com/docs/auth/admin/manage-sessions - `revokeRefreshTokens`, `tokensValidAfterTime` (compared in seconds in the samples), `checkRevoked` + cost, ID token 1h, automatic revocation events.
- https://firebase.google.com/docs/reference/admin/node/firebase-admin.auth.baseauth - `verifyIdToken(idToken, checkRevoked?)`: with checkRevoked, disabled user -> `auth/user-disabled`, then `auth/id-token-revoked`; `revokeRefreshTokens` requires a synchronized server clock; no clock-tolerance parameter.
- https://firebase.google.com/docs/reference/admin/node/firebase-admin.auth.updaterequest - `providersToUnlink`.
- https://firebase.google.com/docs/reference/admin/python/firebase_admin.auth - `verify_id_token(..., clock_skew_seconds=0)` (0-60); `ExpiredIdTokenError`/`RevokedIdTokenError` subclass `InvalidIdTokenError`; `UserDisabledError` subclasses `InvalidArgumentError`; `CertificateFetchError` subclasses `UnknownError`.
- https://firebase.google.com/docs/auth/admin/verify-id-tokens - verification checks (aud, iss, exp, iat, sub, auth_time); no revocation check by default.
- https://firebase.google.com/docs/auth/admin/manage-cookies - session cookie 5 min-2 weeks, httpOnly/secure, CSRF, `verifySessionCookie(..., true)`.
- https://firebase.google.com/docs/emulator-suite/connect_auth - with `FIREBASE_AUTH_EMULATOR_HOST` set the Admin SDK accepts unsigned ID tokens and session cookies; do not set it in production.
- https://firebase.google.com/docs/auth/admin/errors - error codes used in E5.
- https://firebase.google.com/docs/auth/flutter/federated-auth - Apple `revokeTokenWithAuthorizationCode`.
- https://pub.dev/packages/google_sign_in/changelog and the package MIGRATION.md (flutter/packages) - v7: singleton `GoogleSignIn.instance`, mandatory `initialize`, `authenticate` replaces `signIn`, authentication and authorization separated, access tokens via authorization calls.
- Role `roles/firebaseauth.admin` (Firebase Authentication Admin) and Apple `sub` stability per developer team: confirmed by the skill reviewer (2026-10-15).
Not verified against primary docs: Apple App Store guideline wording (4.8, 5.1.1(v)), Apple REST `/auth/token` and `/auth/revoke` parameter details, Apple server-to-server notification payload wrapper and exact event names (secondary source only), Android null Apple authorizationCode (community report), exact google_sign_in v7 method/exception names and per-platform `initialize` params, Firebase ID-token pre-refresh thresholds per platform, Node error code for certificate-fetch failures and for reserved claims in `createCustomToken`, `__session` cookie name requirement, google_sign_in plugin iOS Info.plist keys.
