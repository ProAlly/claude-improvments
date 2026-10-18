# C. Token GENERATION

## C1. Firebase custom tokens - `createCustomToken(uid, developerClaims?)` [NEW in VGA]
When: see `social-login.md` A (ii). The real reason is to give a non-Firebase-login user a Firebase Auth identity for Firebase-secured services. Not needed for our own API.

Rules [DOCS unless marked]:
- `uid`: non-empty string, **1-128 chars** (`auth/invalid-uid`). Use our stable user id (e.g. Mongo ObjectId hex) - never email/phone (PII in rules logs; changes over time). If the user also signs in with Google/Apple, that Firebase uid is different: either always use custom tokens for that user, or reuse the stored `firebaseUid` as the custom-token uid so both paths map to one Firebase user.
- `developerClaims`: JSON-serializable, keep it tiny. The create-custom-tokens page documents NO size limit for these claims and no `auth/claims-too-large` for `createCustomToken` (that 1000-byte limit and code are documented for `setCustomUserClaims`, C2) - keep custom-token claims under 1000 bytes as a self-imposed rule, because they end up in every ID token. Reserved names must not be used: `acr, amr, at_hash, aud, auth_time, azp, cnf, c_hash, exp, iat, iss, jti, nbf, nonce, sub, firebase, user_id` [DOCS]; passing one to `createCustomToken` is rejected as an invalid-argument error (Node `auth/argument-error`/`auth/invalid-argument` [UNVERIFIED exact code]) - it is NOT the `auth/reserved-claims` code of `setCustomUserClaims`.
- The custom token itself expires **1 hour** after `iat` (max 3600s) [DOCS] - it is a one-shot login ticket, mint it right before returning it, never store it.
- Client: `FirebaseAuth.instance.signInWithCustomToken(token)` -> Firebase issues a normal ID token (1h, auto-refreshed) + refresh token (long-lived, until revoked/disabled/deleted) [DOCS]. Claims from the custom token appear in the ID token and in rules as `request.auth.token.<claim>`.
- Custom-token claims take priority over `setCustomUserClaims` claims with the same key [DOCS] - pick one source per claim.
- Signing: with a service-account private key the SDK signs locally (no network). With ADC (Cloud Run/Functions) it calls the IAM `signBlob` API -> the runtime service account needs `iam.serviceAccounts.signBlob` (role **Service Account Token Creator**) AND the **IAM Service Account Credentials API** (`iamcredentials.googleapis.com`) must be enabled in the project, else signing fails with "IAM API is not enabled" [DOCS create-custom-tokens troubleshooting].
- Rate-limit the endpoint that returns custom tokens; return it only to an authenticated caller for THEIR uid.

```ts
// Only for users already authenticated by OUR backend (OTP/password).
async mintFirebaseToken(user: { id: string; role: string; tenantId?: string; firebaseUid?: string }): Promise<string> {
  const claims = { role: user.role, ...(user.tenantId ? { tid: user.tenantId } : {}) };   // tiny, no PII
  return getAuth(this.app).createCustomToken(user.firebaseUid ?? user.id, claims);
}
// Returned inside the login response: { accessToken, refreshToken, expiresIn, firebaseCustomToken }
```

## C2. Custom user claims (roles in Firebase) - `setCustomUserClaims(uid, claims)` [NEW in VGA]
- Use only for access control in Firebase Security Rules (role, tenant). Profile data stays in our DB [DOCS best practice].
- **Overwrites** all existing custom claims - read-modify-write: `const cur = (await getUser(uid)).customClaims ?? {}; await setCustomUserClaims(uid, {...cur, role})`; `null` clears all [DOCS].
- Limit 1000 bytes (`auth/claims-too-large`); reserved names (`auth/reserved-claims`) [DOCS].
- **Propagation caveat**: new claims appear only after sign-in, the natural hourly refresh, or a forced refresh [DOCS]. Fix:
  1. Backend sets claims then signals the client (API response flag, FCM data message, or a Firestore `metadata/{uid}.refreshTime` doc the client listens to).
  2. Client calls `getIdToken(true)` (Flutter: `currentUser!.getIdToken(true)`; web: `getIdToken(user, true)`).
  3. For DOWNGRADES (remove admin) do not wait: also `revokeRefreshTokens(uid)` and verify sensitive calls with `checkRevoked` (revocation.md D2).
- Mapping to our roles: our DB is the source of truth. Claims are a projection written on role change by one function `syncFirebaseClaims(user)`; never read roles back FROM Firebase claims into our DB, and our API guard never trusts Firebase claims (it uses our JWT + DB).

## C3. Our own JWT issuing (the app session) - [VGA] Sanad / Fursatuk / Buzz model
| Item | Standard | Source |
| --- | --- | --- |
| Access token | JWT HS256 (or RS256 if other services verify), TTL from config: 15m (sensitive) to 1d max; claims `sub`, `role`/`typ` actor type, `jti`, `sid` (session id), `tv` (token version) optional, `iat`, `exp`, `iss`, `aud` | [VGA] Buzz access has `jti`; [NEW] `sid` |
| Refresh token | Opaque `randomBytes(32).toString('hex')`, stored as **SHA-256 hash** in `auth_sessions`, TTL 30d (sliding via rotation, absolute cap optional e.g. 90d); atomic claim must include `expiresAt > now` (revocation.md D3.1, KNOWN SANAD BUG) | [VGA] Sanad (opaque + hash + reuse => revoke all) |
| Alternative refresh | Signed JWT refresh with a separate refresh secret. Variants: Fursatuk stores a `jti` record (`revoked`, `replacedByJti`) and revokes all outside a 30s grace; Buzz stores the SHA-256 of the refresh JWT in a `sessions` row and swaps the hash in place atomically on rotation (`atomicSwap`), logout = `findOneAndDelete`/`deleteOne` - Buzz has NO revoke-all on reuse (an already-rotated token just gets 401 `REFRESH_REVOKED`, `auth.service.ts` ~226-243) | [VGA] Fursatuk, Buzz |
| Secrets | Separate secret per token type (access vs refresh) AND per actor/issuer (app user, tenant staff, system admin) | [VGA] Buzz three issuers |
| Audience | `aud` per actor surface (`app`, `dashboard`, `admin`); guard verifies `aud` so a user token cannot call admin routes even if the secret leaks across modules | [NEW] |
| Never | Same key for access + refresh distinguished only by a `type` claim (Cozzy, Letsplay, CareLink) | [GAP] |
| Response | `{ accessToken, refreshToken, tokenType: 'Bearer', expiresIn: <seconds from the SAME config used to sign> }` | [GAP] Al Mudarib hardcodes `expiresIn: 86400` in `src/modules/user/user.model.ts` (`token()` ~247, `refreshToken()` ~285) while signing with `env.JWT_EXPIRES_IN`; Fursatuk returns the config STRING (e.g. `'15m'`), not seconds |
| One session per device | One `auth_sessions` row per login with `ip`, `userAgent` [VGA Sanad stores only these two] + `deviceId` [NEW]; do NOT store a single refresh hash on the user (Vetrina, Outlet = one device only) | [VGA] Sanad (per-login rows); [NEW] `deviceId` |
| Clock skew | Verify with `clockTolerance: 30` seconds | [NEW] |

Config sketch:
```ts
export default registerAs('jwt', () => ({
  access:  { secret: req('JWT_ACCESS_SECRET'),  ttl: process.env.JWT_ACCESS_TTL ?? '15m', aud: 'app' },
  refresh: { ttlDays: Number(process.env.JWT_REFRESH_TTL_DAYS ?? 30), absoluteDays: 90 },
  issuer: process.env.JWT_ISSUER ?? '<api-host>',
}));   // req() throws at boot if missing - NO fallback secrets (Amirni/CareLink gap)
```
`expiresIn` for the response: parse the same `ttl` string with one helper (`ms(ttl)/1000`) or store TTL in seconds in config.

## C4. Multi-tenant and multi-actor claims
- Actor type in token (`typ: 'user'|'staff'|'admin'`) + separate secrets/audiences per type ([VGA] Buzz app/tenant/system issuers).
- Tenant: `tid` claim for the CURRENT tenant only; guard re-checks membership in DB (membership can be revoked mid-token). Tenant switch = new token pair, not a mutable claim.
- Firebase rules multi-tenant: put `tid` in custom claims (C1/C2), rules check `request.auth.token.tid == resource.data.tenantId`. Firebase Identity Platform multi-tenancy (`tenantId` on Auth) is a different, paid feature [UNVERIFIED pricing] - not used in VGA.
- Session rows carry `actorType` + `actorId` (+ `tenantId`) so revoke-all can be scoped per actor ([VGA] Sanad `actorRole`).
