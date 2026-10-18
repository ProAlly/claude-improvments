# J. Account flows: explicit link/unlink, phone-OTP login, Apple notifications, admin Apple revoke, session cookies

Placeholders from backend-nestjs.md (top table) apply: `conflict()`, `forbidden()`, `this.users`, `this.verifier`, `this.tokens`, `this.revocation`, `this.audit`, `dupKeyField()`, `now`. Additional placeholders here: `this.apple` (Apple REST client, J4), `encrypt()/decrypt()` (AES-256-GCM with a key from the secret manager), `this.queue` (job queue / outbox).

## J1. Explicit link / unlink (authenticated)
Implicit email linking at login (social-login.md B8) covers only verified-email matches. Users also need to add Google/Apple to an existing account (e.g. a phone-only account, J2) and to remove one.

**Identity model**: one Firebase uid per our user. Google and Apple on the same account share that uid because the CLIENT links them at Firebase level (`currentUser.linkWithCredential(cred)` / `linkWithProvider`) - the backend only records it.

`POST /auth/link { idToken }` - access JWT (normal guard), rate-limited:
```ts
async link(actor: User, idToken: string) {
  const id = await this.verifier.verify(idToken, { checkRevoked: true });     // fresh Firebase ID token of the provider to add
  const owner = await this.users.findOne({ firebaseUid: id.firebaseUid });
  if (owner && !owner._id.equals(actor._id)) throw conflict('PROVIDER_ALREADY_LINKED');   // that Google/Apple identity is another account
  if (actor.firebaseUid && actor.firebaseUid !== id.firebaseUid)
    throw conflict('ACCOUNT_LINK_CONFLICT');      // client must linkWithCredential on the EXISTING Firebase user first, then send its new ID token
  const set: Record<string, unknown> = { firebaseUid: id.firebaseUid };
  if (id.provider === 'APPLE') set.appleSub = id.providerUserId;              // J3 lookup key
  try {
    await this.users.updateOne({ _id: actor._id, $or: [{ firebaseUid: { $exists: false } }, { firebaseUid: id.firebaseUid }] },
      { $set: set, $addToSet: { providers: { $each: id.linkedProviders } } }); // linkedProviders = allow-listed keys of decoded.firebase.identities (extend E2)
  } catch (e) { if (dupKeyField(e) === 'firebaseUid') throw conflict('PROVIDER_ALREADY_LINKED'); throw e; }
  this.audit.log('auth.provider_linked', { userId: actor.id, provider: id.provider });
}
```
- Never copy the token's email onto the account during link unless `email_verified` AND the email is not used by another account; never change role.
- Apple: if the client sends `appleAuthorizationCode`, run the J4 exchange here too.

`DELETE /auth/providers/:provider` (`google.com` | `apple.com`) - access JWT + recent auth (fresh ID token or OTP within 5 min):
1. **Last-login-method guard, atomic** (two parallel unlinks must not both succeed):
   ```ts
   const methods = { $add: [ { $size: '$providers' },
     { $cond: [{ $ifNull: ['$passwordHash', false] }, 1, 0] },
     { $cond: [{ $ifNull: ['$phoneVerifiedAt', false] }, 1, 0] } ] };            // count every login method the product supports
   const res = await this.users.findOneAndUpdate(
     { _id: actor._id, providers: provider, $expr: { $gt: [methods, 1] } },
     { $pull: { providers: provider }, ...(provider === 'apple.com' ? { $unset: { appleSub: 1 } } : {}) }, { new: true });
   if (!res) throw conflict('LAST_LOGIN_METHOD');    // or 404 if the provider was not linked (check separately for a precise code)
   ```
2. Firebase: `getAuth(app).updateUser(uid, { providersToUnlink: [provider] })` [DOCS Node `UpdateRequest`]. If no Firebase provider remains, either keep the Firebase user (harmless) or `deleteUser(uid)` and `$unset firebaseUid` - state the choice.
3. Apple: revoke the Apple grant with the stored token and drop `appleRefreshTokenEnc` (J4). Google: client calls `GoogleSignIn.instance.disconnect()` (v7; v6 `GoogleSignIn().disconnect()`).
4. Our sessions are NOT revoked (the user is still the same account); audit `auth.provider_unlinked`.

## J2. Phone-OTP login path (our own SMS gateway)
Flow: `POST /auth/otp/request { phone }` -> generate OTP (CSPRNG, 4-6 digits), store **hashed** with TTL (e.g. 5 min) and attempt counter, send via the project's SMS skill -> `POST /auth/otp/verify { phone, code, deviceId }` -> constant-time compare, max attempts (e.g. 5) then lock, single use (delete on success) -> find user by `phone` (E.164) or create (`phoneVerifiedAt = now`, role server-side, `isNewUser`) -> same checks as E3 (`deletedAt`, `isActive`) -> **`this.tokens.issue(user, ctx)`** (identical token pair, session row, rotation, revocation as social login).
- SMS provider: Kuwait SMSBox -> skill `aks-smsbox-built-url` (backend builds `sms_url`, client sends it); Dreams (dreams.sa) -> skill `aks-dreams-sms`. Those skills own delivery, error mapping, phone normalisation and OTP bypass rules.
- **Do NOT mix Firebase Phone Auth with our own SMS OTP.** Pick one: if phone login runs through our gateway, do not enable the Firebase Phone provider and keep `phone` OFF the `/auth/social` provider allow-list (social-login.md B7) - otherwise there are two phone identities, two rate limits, two bypass surfaces and duplicate accounts. If the client also needs a Firebase identity for rules, mint a custom token after OTP verification (token-generation.md C1).
- **Linking phone-only accounts to a later Google/Apple login**: a phone-only account has no email, so implicit email linking (B8) never matches and a Google/Apple login from a fresh install creates a SECOND account. Prevent it: (a) in-app "Link Google / Apple" while logged in by phone -> J1 `POST /auth/link`; (b) on the login screen of a fresh install, offer phone first ("already have an account?") and then link; (c) if a newly created social account later verifies a phone already owned by another account, return 409 `PHONE_IN_USE` and offer "sign in with phone, then link" - merging two accounts is a separate, audited support operation, never automatic.
- Phone change: re-verify the new number by OTP, then revocation D1 "Phone / email change" (RA except current, `tv++`).
- OTP must never be echoed in responses outside dev - security-testing.md G2.

## J3. Apple server-to-server notifications (Firebase does NOT handle these)
Apple POSTs to the endpoint registered for the Sign in with Apple configuration of the App ID / Services ID when a user changes their Apple-side relationship with the app. Firebase Auth ignores them, so the backend must act.
`POST /webhooks/apple/sign-in-notifications` (public, no session):
1. Body carries a signed JWT (`{ "payload": "<JWS>" }` [UNVERIFIED wrapper field name]). Verify it with Apple's JWKS (`https://appleid.apple.com/auth/keys`), `iss = https://appleid.apple.com`, `aud = <our client_id>` (bundle id / services id), `alg` from the header checked against the expected algorithm. Reject anything unverified with 400 and do nothing.
2. Parse the `events` claim (a JSON string): `{ type, sub, email?, is_private_email?, event_time }`.
3. Find the user by `appleSub` (stored at login/link from E2 `providerUserId` when provider is APPLE; index `{ appleSub: 1 }` unique sparse). Unknown `sub` -> 200, log.
4. Deduplicate (`sub + type + event_time`), respond 200 quickly, process via `this.queue` (each handler idempotent).

| Apple `type` | Meaning | Our action (revocation.md D1 row) |
| --- | --- | --- |
| `email-disabled` | user turned off forwarding to the relay email | set `emailForwardingEnabled=false`; stop sending email to the relay address; no session change |
| `email-enabled` | forwarding turned back on | set `emailForwardingEnabled=true` |
| `consent-revoked` | user stopped using Sign in with Apple with this app | D1 "Apple consent-revoked" = D4 revoke-all (RA, KS, FB, clearAll); delete `appleRefreshTokenEnc`; if Apple was the ONLY login method, the user must sign in again (same `sub`, new consent) |
| `account-delete` (some sources spell it `account-deleted` - accept both) | user deleted their Apple account | D1 "Account deletion" flow without the Apple revoke step (grant already gone): RA, KS, `deleteUser(uid)`, clearAll, anonymise per backend-nestjs.md E3 (or flag for review if the account has other login methods) |
Event names and payload shape: [UNVERIFIED - Apple developer docs were not fetchable during authoring; a secondary source lists exactly these four types]. Audit every event (`auth.apple_notification`, type, user id; never the JWS).

## J4. Apple token exchange and admin-initiated deletion of an Apple user
Apple's REST `POST https://appleid.apple.com/auth/revoke` needs `client_id`, `client_secret`, `token` (an Apple refresh or access token) and `token_type_hint`; it does not take an authorization code. Only the device can produce an authorization code, and it is short-lived and single-use. So for an admin (or J3/automated) deletion, where no user is present, the backend can revoke Apple ONLY if it stored an Apple refresh token earlier.
At sign-in / link (when `appleAuthorizationCode` is sent, social-login.md B5):
1. Build `client_secret`: ES256 JWT signed with the Apple .p8 key (secret manager) - header `kid=<APPLE_KEY_ID>`, claims `iss=<APPLE_TEAM_ID>`, `iat`, `exp` (<= 6 months), `aud=https://appleid.apple.com`, `sub=<client_id>`. Cache and re-sign before expiry.
2. `POST https://appleid.apple.com/auth/token` (form-encoded) `client_id, client_secret, code, grant_type=authorization_code` -> `{ refresh_token, id_token, ... }`. Check that `id_token.sub` equals the user's `appleSub`.
3. Store `appleRefreshTokenEnc = encrypt(refresh_token)` (AES-256-GCM, key `APPLE_TOKEN_ENC_KEY` from the secret manager, never logged, excluded from `toPublic`).
4. Exchange failure must NOT fail the login: log (no code in logs), mark `appleTokenMissing`, retry at the next Apple login.
At deletion (user-initiated `DELETE /me` or admin `DELETE /admin/users/:id`):
1. If `appleRefreshTokenEnc` exists: `POST /auth/revoke` with `token=decrypt(...)`, `token_type_hint=refresh_token`; 200 = done. Retry via queue on 5xx/network.
2. Else, user-initiated: require a fresh authorization code from the client (FlutterFire `revokeTokenWithAuthorizationCode(code)` or send it to the backend for steps above). Admin-initiated with no stored token: Apple cannot be revoked - record `appleRevokePending` in the audit log and tell the operator; this is the reason to store the token at sign-in.
3. Then continue revocation.md D4 (RA, KS, `deleteUser`, clearAll, anonymise, audit).
All Apple endpoint parameter details: [UNVERIFIED - re-check Apple "Generate and validate tokens" and "Revoke tokens" docs before implementing].

## J5. Firebase session cookies (option iii) - OUT OF SCOPE for current VGA projects
VGA dashboards are SPAs that use our own JWT with an httpOnly refresh cookie (client.md F2), so session cookies are not part of the standard. Notes only, if a server-rendered dashboard ever adopts them [DOCS manage-cookies unless marked]:
- Login: client signs in with Firebase, POSTs the ID token to `/sessionLogin` with a CSRF token; server requires a recent sign-in (`auth_time` within ~5 min), then `createSessionCookie(idToken, { expiresIn })` (5 min - 2 weeks) and sets it `httpOnly`, `secure`, `sameSite`, `path=/`. On Firebase Hosting the cookie must be named `__session` [UNVERIFIED].
- CSRF: double-submit token or SameSite=Strict + Origin check on `/sessionLogin` and every state-changing request.
- Every request: `verifySessionCookie(cookie, true)` (checkRevoked: disabled -> `auth/user-disabled`, revoked -> `auth/session-cookie-revoked`); on failure clear the cookie and redirect to login. Cache per uid briefly if the network call is too costly.
- Logout: `res.clearCookie('__session')`; for logout-everywhere also `revokeRefreshTokens(decoded.sub)` (revokes the user's sessions on all devices). The rest of revocation.md D1/D4 applies unchanged.
