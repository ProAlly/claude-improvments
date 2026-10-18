---
name: aks-firebase-auth-tokens
description: Implement or review Google + Apple social login through Firebase Auth and the full token lifecycle in VGA backends (NestJS primary, FastAPI/Express notes) and Flutter/web clients - verify Firebase ID token then issue the app's own JWT, Firebase custom token generation (createCustomToken, setCustomUserClaims), and revocation (revokeRefreshTokens, verifyIdToken checkRevoked, logout, logout-all, force-logout, ban, account deletion, refresh-token rotation with reuse detection, Sanad model). Use for "social login", "sign in with Google", "sign in with Apple", "firebase auth", "firebase idToken", "verifyIdToken", "custom token", "signInWithCustomToken", "custom claims", "revoke tokens", "refresh token rotation", "reuse detection", "logout all devices", "force logout", "session cookie", "auth/id-token-revoked", "SHA-1 fingerprint", "Apple nonce", "Apple private relay email", or reviewing an auth/token flow for gaps.
user-invocable: true
---

# aks-firebase-auth-tokens - Social login + token generation and revocation (VGA standard)

Two layers, never confused:
1. **Firebase layer** - Firebase ID token (1h JWT) + Firebase refresh token, owned by the Firebase client SDK. Used to PROVE identity to our backend, and for Firebase-secured services (Firestore/Storage rules).
2. **App layer** - our own access JWT + rotating refresh token (Sanad model, with the expiry fix in `references/revocation.md` D3.1). This is the app's real session for our API.

Labels used throughout: **[VGA]** = existing practice in a named project (verified by reading code read-only unless noted), **[NEW]** = recommendation not yet shipped in any VGA project, **[DOCS]** = checked against official Firebase docs on 2026-10-15 (sources listed at the end of `references/security-testing.md`), **[UNVERIFIED]** = verify against current Firebase / Apple docs before relying on it.

**Never** open or commit `.env`, service-account JSON, `firebase.credentials.*`, Apple `.p8` keys, or the `Credentials VGA` folder. Use placeholders (`<PROJECT_ID>`, `<BUNDLE_ID>`) and env var NAMES only.

## Reference files
| File | Covers |
| --- | --- |
| `references/social-login.md` | A decision guide; B console/Android/iOS/web/Flutter setup (google_sign_in v7 + v6), Apple quirks, backend verification, account linking policy, disabled/deleted at login |
| `references/token-generation.md` | C createCustomToken, custom claims, own JWT issuing, multi-tenant claims |
| `references/revocation.md` | D full revocation matrix, Firebase vs own-JWT mechanisms, ordering rules, D5 cross-skill notes (FCM) |
| `references/backend-nestjs.md` | E NestJS code: placeholder list, admin init, verifier, SocialLoginService, TokenService (rotation fix), guard (`sid`, timestamp precision), error table, endpoints, rate limits, clock skew, schemas; FastAPI/Express notes |
| `references/account-flows.md` | J1 explicit link/unlink, J2 phone-OTP login, J3 Apple server-to-server notifications, J4 Apple token exchange + admin-initiated deletion, J5 session cookies (out of scope) |
| `references/client.md` | F Flutter + web storage, single-flight refresh, 401 retry, logout |
| `references/security-testing.md` | G security checklist, dev/OTP bypass rules, emulator, test list, monitoring; H known VGA gaps; doc sources |

## Workflow
1. **Detect state** (read-only): grep for `firebase-admin`, `verifyIdToken`, `verify_id_token`, `socialLogin`, `refreshToken`, `revokedAt`, `jti`, `sessionInvalidatedAt`, `google_sign_in`, `sign_in_with_apple`, `TEMP_OTP`, `EXPOSE_OTP`. Classify the project: Pattern 1 (Firebase ID token -> own JWT), Pattern 2 (provider libs, no Firebase), or broken (client email trusted).
2. **Decide** with section A (below). Default = Pattern 1 + Sanad rotation (with the expiry fix).
3. **Compare** against the No-gaps checklist at the bottom; fix gaps, do not rewrite what conforms.
4. **Implement** from the reference files. 5. **Test** with `references/security-testing.md` list.

## A. Decision guide (summary; details in `references/social-login.md`)
- **(i) Verify Firebase ID token -> issue own JWT** - DEFAULT whenever the backend has its own users/roles/sessions. [VGA] Al Mudarib, Buzz, Outlet, Cozzy.
- **(ii) `createCustomToken`** - ONLY when a user who did NOT log in through Firebase (phone OTP via our SMS gateway, backend email/password, legacy account) must ALSO be signed into the Firebase client SDK to use Firebase-secured services (Firestore/RTDB/Storage rules with `request.auth`, callable functions). NOT needed if the client only talks to our API - our own JWT is enough. FCM does NOT require a Firebase Auth user. [NEW] - no VGA project uses it.
- **(iii) Firebase session cookies** (`createSessionCookie`, 5 min-2 weeks [DOCS]) - for server-rendered web dashboards that want httpOnly cookies instead of bearer tokens. [NEW] - OUT OF SCOPE for current VGA projects (SPA dashboards use our own JWT in an httpOnly refresh cookie); notes in `references/account-flows.md` J5.
- **Pattern 2** (google-auth-library / apple-signin-auth / JWKS, no Firebase) is acceptable [VGA: Amirni, Vetrina, CareLink]; the token-lifecycle rules (C, D, F, G) apply identically.
- **Phone OTP** through our own SMS gateway feeds the same `issue()`; never mixed with Firebase Phone Auth (`references/account-flows.md` J2).

## Core rules (each expanded in the references)
- Client sends the **Firebase ID token**, never just email/uid. Backend verifies with Admin SDK (named app), then checks `firebase.sign_in_provider` allow-list, `email_verified` before ANY email-based linking, user disabled/deleted state.
- Link accounts by `firebaseUid` (unique sparse index) first; by email only if `email_verified === true` and the existing account policy allows it; never link into staff/admin roles; an email account bound to another uid => 409 `ACCOUNT_LINK_CONFLICT` (never overwrite, never crash). Deletion anonymises email and unsets `firebaseUid` so re-signup is possible.
- Own tokens: access short TTL (15m-1d) carrying `sid`, `tv`; refresh opaque random 32 bytes stored **SHA-256 hashed** with `revokedAt`, per-session row (multi-device), separate secrets/audiences per token type and actor type, `expiresIn` in seconds in the response read from the same config that signed the token.
- Rotation: atomic claim (`findOneAndUpdate` on `{hash, revokedAt: absent, expiresAt > now}`); presenting a revoked AND unexpired token = reuse => revoke all sessions of that actor ([VGA] Sanad; Sanad's own filter lacks the expiry condition - KNOWN SANAD BUG). Client refresh must be single-flight; optional short grace ([VGA] Fursatuk 30s).
- Revocation needs a per-request check for access tokens: DB re-load (Al Mudarib) or `tv` (preferred for revoke-then-reissue) / second-floored `tokensValidBefore` compare or Redis denylist (Buzz), plus the `sid` session check so single-session revoke is immediate. Stateless-only access tokens stay valid until expiry - keep TTL short if you choose that.
- Firebase side: `revokeRefreshTokens(uid)` on logout-all/ban/compromise; existing Firebase ID tokens remain valid up to 1h unless verified with `checkRevoked=true` [DOCS]. Only the login exchange (and `/auth/link`) needs `checkRevoked` (one extra network call [DOCS]).
- Logout-all / ban / force-logout / compromise / deletion ordering: user state -> own refresh rows -> Redis -> Firebase `revokeRefreshTokens` (Apple revoke + `deleteUser` for deletion) -> FCM `clearAll` -> audit log. Single-device logout removes the FCM token server-side in `POST /auth/logout`.
- Apple: store the Apple refresh token (encrypted) at sign-in so ANY deletion can revoke Apple; handle Apple server-to-server notifications (Firebase does not).
- Fail closed: missing Firebase config => 503/401, never a bypass. No dev or OTP bypass in a production build; `FIREBASE_AUTH_EMULATOR_HOST` unset in prod.
- Map errors: invalid/expired/revoked token => 401; disabled/banned/deleted => 403; account-state conflicts (role conflict, link conflict, password-to-link, last login method) => 409; unsupported provider => 400; not configured => 503. Full table: `references/backend-nestjs.md` E5.

## I. No-gaps checklist (every lifecycle step -> where it is handled)
| # | Lifecycle step | Handled in |
| --- | --- | --- |
| 1 | Pick architecture (own JWT vs custom token vs session cookie) | A above; `social-login.md` A |
| 2 | Firebase console: enable Google + Apple providers, authorized domains, IAM role | `social-login.md` B1 |
| 3 | Android setup: SHA-1/SHA-256 (debug, upload, Play App Signing), google-services.json | `social-login.md` B2 |
| 4 | iOS setup: Sign in with Apple capability, URL scheme (REVERSED_CLIENT_ID), GoogleService-Info.plist | `social-login.md` B3 |
| 5 | Web: popup vs redirect, authorized domains, Apple Services ID + return URL | `social-login.md` B4 |
| 6 | Flutter sign-in flow (google_sign_in v7 / v6, Apple), send ID token not email | `social-login.md` B5; `client.md` F1 |
| 7 | Apple quirks: nonce, name first time only (email claim every login), private relay, stable `sub`, token revoke on deletion (5.1.1) | `social-login.md` B6 |
| 8 | Backend verify (signature/aud/iss/exp, provider, email_verified, error codes) | `social-login.md` B7; `backend-nestjs.md` E2 |
| 9 | Account linking at login (firebaseUid, verified email, role guard, link conflict 409) | `social-login.md` B8; `backend-nestjs.md` E3 |
| 10 | First login vs returning: `isNewUser` only for the inserting request, concurrent loser re-reads, profile captured on create only, returning user backfills providers/appleSub | `backend-nestjs.md` E3 (rules under the code); `social-login.md` B8 step 3 |
| 11 | Disabled / deleted / banned users at login | `social-login.md` B9; `revocation.md` D1 |
| 12 | Issue own access + refresh tokens | `token-generation.md` C3; `backend-nestjs.md` E4 |
| 13 | Firebase custom token generation (when needed) | `token-generation.md` C1 |
| 14 | Custom claims / roles + propagation | `token-generation.md` C2 |
| 15 | Multi-tenant / multi-actor claims and secrets | `token-generation.md` C4 |
| 16 | Refresh endpoint | `backend-nestjs.md` E4/E6 |
| 17 | Rotation + reuse detection + grace (expiry in claim filter, Sanad bug) | `revocation.md` D3; `backend-nestjs.md` E4 |
| 18 | Revoke single session (logout this device, revoke session by id) incl. its in-flight access token via `sid` | `revocation.md` D1; `backend-nestjs.md` E4 guard |
| 19 | Revoke all (logout-all, password/phone change, compromise) incl. same-second new pair | `revocation.md` D1/D3/D4; `backend-nestjs.md` E4 "Timestamp precision" |
| 20 | Admin force-logout / ban / disable | `revocation.md` D1; `backend-nestjs.md` E6 |
| 21 | Account deletion (own data, anonymise email/uid, Firebase deleteUser, Apple revoke) | `revocation.md` D1; `social-login.md` B6; `backend-nestjs.md` E3 |
| 22 | Access-token kill-switch (DB re-check / timestamp / Redis / tokenVersion / sid) | `revocation.md` D3 |
| 23 | Firebase revokeRefreshTokens + checkRevoked cost | `revocation.md` D2 |
| 24 | Force claim refresh on client | `token-generation.md` C2; `client.md` F3 |
| 25 | Client token storage (secure storage / httpOnly cookie) | `client.md` F2 |
| 26 | Single-flight refresh, 401 -> refresh -> retry once; logout only on dead-session codes; correct excluded routes | `client.md` F3 |
| 27 | Logout flow (server + FirebaseAuth + Google signOut) | `client.md` F4 |
| 28 | FCM device token cleanup (server-side on logout, `disable()` on client, `clearAll` on D4 events) | `revocation.md` D4/D5; `client.md` F4; skill `aks-fcm-webpush` |
| 29 | Secrets: env/secret manager, rotation if exposed, separate keys | `backend-nestjs.md` E1; `security-testing.md` G1 |
| 30 | Rate limiting, audit logging (no tokens), clock skew / NTP | `backend-nestjs.md` E7 |
| 31 | Error -> HTTP status mapping | `backend-nestjs.md` E5 |
| 32 | DB schemas + indexes (users.firebaseUid, appleSub, auth_sessions TTL) | `backend-nestjs.md` E8 |
| 33 | Dev/test: no dev or OTP bypass in prod, emulator var unset, Auth emulator, test cases | `security-testing.md` G2/G3 |
| 34 | Monitoring/alerts (reuse events, failure spikes) | `security-testing.md` G4 |
| 35 | Known VGA gaps not to copy | `security-testing.md` H |
| 36 | FastAPI / Express equivalents (Python exception order) | `backend-nestjs.md` E9 |
| 37 | Explicit link (`POST /auth/link`) / unlink (`DELETE /auth/providers/:p`) with last-login-method guard | `account-flows.md` J1 |
| 38 | Phone-OTP login path -> same `issue()`; no Firebase Phone Auth mix; linking phone-only accounts; SMS skills | `account-flows.md` J2 |
| 39 | Apple server-to-server notifications (consent-revoked, account-delete, email-disabled/enabled) | `account-flows.md` J3; `revocation.md` D1 |
| 40 | Admin-initiated deletion of an Apple user (stored Apple refresh token, REST revoke) | `account-flows.md` J4; `social-login.md` B6 |
| 41 | Session cookies (option iii) - out of scope for VGA; notes if adopted | `account-flows.md` J5 |
| 42 | Cross-skill FCM alignment (`aks-fcm-webpush` clearAll list) | `revocation.md` D5 |
