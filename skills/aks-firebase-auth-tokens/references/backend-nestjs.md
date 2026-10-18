# E. Backend implementation (NestJS + Mongoose primary; FastAPI/Express in E9)

Sketch code: adapt names to the project's conventions (e.g. Buzz bans native `Date` -> use its `DateService`; Buzz uses `getEnvByKey`). Placeholders only.

**Undefined helpers / injected members in the sketches below - PLACEHOLDERS the project must supply** (none is a library export):
| Placeholder | Meaning |
| --- | --- |
| `mapFirebaseError(e)` | maps Firebase Admin errors to the E5 table (Nest exceptions) |
| `sanitizeName(s)` | trim, strip control chars/HTML, cap length (e.g. 100) |
| `dupKeyField(e)` | returns the field that caused a Mongo `E11000` (`Object.keys(e.keyPattern ?? {})[0]`) or `null` if not a dup-key error (replaces a plain `isDupKey`) |
| `toPublic(user)` | strips private fields (password hash, firebaseUid, tokens, encrypted Apple token) |
| `sha256(s)` | `createHash('sha256').update(s).digest('hex')` |
| `addDays(d, n)` | date arithmetic (or the project's `DateService`) |
| `now` | a `Date` captured once at the top of the method (`const now = new Date()` / `this.date.now()`) |
| `ttlSeconds(ttl)` | `'15m'` -> `900` using the SAME parser as the signer (e.g. `ms(ttl)/1000`) |
| `unauthorized(code)` / `forbidden(code)` / `conflict(code)` | `new UnauthorizedException({ code, message, messageAr })` etc. |
| `this.users` | user Mongoose model |
| `this.sessions` | `auth_sessions` Mongoose model (E8) |
| `this.actors` | loader `load(actorType, id)` over the actor collections (user / staff / admin) |
| `this.revocation` | `SessionRevocationService` (revocation.md D4) |
| `this.audit` | audit logger (E7) |
| `this.verifier`, `this.tokens`, `this.jwt`, `this.cfg` | E2 verifier, E4 TokenService, `JwtService`, jwt config (token-generation.md C3) |

## File layout
```
src/modules/auth/
  firebase/firebase-admin.provider.ts   # E1 named app
  firebase/firebase-auth.verifier.ts    # E2
  social-login.service.ts               # E3
  account-link.service.ts               # account-flows.md J1 link / unlink
  token.service.ts                      # E4 issue / rotate / revoke (Sanad model + fixes)
  session-revocation.service.ts         # E4 logout-all / force-logout orchestration (revocation.md D4)
  guards/jwt-auth.guard.ts              # E4 guard
  apple/apple-token.service.ts          # account-flows.md J3/J4 (code exchange, revoke, S2S notifications)
  auth.controller.ts, admin-sessions.controller.ts   # E6
  dto/*.dto.ts                          # E6
  schemas/auth-session.schema.ts        # E8
.env.example   # FIREBASE_PROJECT_ID= FIREBASE_CLIENT_EMAIL= FIREBASE_PRIVATE_KEY=  JWT_ACCESS_SECRET= JWT_ACCESS_TTL=15m JWT_REFRESH_TTL_DAYS=30
               # APPLE_TEAM_ID= APPLE_KEY_ID= APPLE_PRIVATE_KEY= APPLE_CLIENT_ID= APPLE_TOKEN_ENC_KEY=   (only if J3/J4 are implemented)
.gitignore     # *service-account*.json, *firebase*credentials*, *.p8, .env*  (except .env.example)
```

## E1. firebase-admin init (NAMED app, env only)
```ts
export const FIREBASE_AUTH_APP = 'FIREBASE_AUTH_APP';
export const firebaseAdminProvider: Provider = {
  provide: FIREBASE_AUTH_APP,
  useFactory: (): App | null => {
    if (process.env.NODE_ENV === 'production' && process.env.FIREBASE_AUTH_EMULATOR_HOST)   // security-testing.md G2
      throw new Error('FIREBASE_AUTH_EMULATOR_HOST must not be set in production');
    const name = 'auth';                                   // named: never collides with push-sender (aks-fcm-webpush)
    try { return getApp(name); } catch { /* not yet created */ }
    const json = process.env.FIREBASE_SERVICE_ACCOUNT_JSON;            // option B: one JSON env var / secret manager
    const projectId = process.env.FIREBASE_PROJECT_ID;
    const clientEmail = process.env.FIREBASE_CLIENT_EMAIL;
    const privateKey = process.env.FIREBASE_PRIVATE_KEY?.replace(/\\n/g, '\n');   // literal \n -> newline
    if (json) { const sa = JSON.parse(json); return initializeApp({ credential: cert(sa), projectId: sa.project_id }, name); }
    if (projectId && clientEmail && privateKey) return initializeApp({ credential: cert({ projectId, clientEmail, privateKey }), projectId }, name);
    if (process.env.GOOGLE_APPLICATION_CREDENTIALS || process.env.K_SERVICE)   // option C: ADC (path set by platform, file NOT in repo)
      return initializeApp({ credential: applicationDefault(), projectId }, name);
    new Logger('FirebaseAdmin').warn('Firebase auth not configured - social login disabled');
    return null;                                            // callers fail closed with 503
  },
};
```
[VGA] Buzz `buzz-auth` named app from `FIREBASE_*`. Outlet (`apps/api/src/config/firebase.credentials.ts`) and Al Mudarib (`src/config/firebase.credentials.ts`) import a `firebase.credentials.ts` module that IS tracked in git (`git ls-files`, checked 2026-10-15); its contents were NOT opened by this skill [verify content before claiming exposure]. If it holds a service-account private key: move to env / secret manager and rotate the key (delete the old key in GCP IAM -> Service accounts -> Keys); removing it from git history alone is not enough.

## E2. FirebaseAuthVerifier
```ts
const ALLOWED = new Map([['google.com', 'GOOGLE'], ['apple.com', 'APPLE']] as const);
@Injectable()
export class FirebaseAuthVerifier {
  constructor(@Inject(FIREBASE_AUTH_APP) private readonly app: App | null) {}
  async verify(idToken: string, opts = { checkRevoked: true }): Promise<FirebaseIdentity> {
    if (!this.app) throw new ServiceUnavailableException({ code: 'AUTH_PROVIDER_NOT_CONFIGURED' });
    let d: DecodedIdToken;
    try { d = await getAuth(this.app).verifyIdToken(idToken, opts.checkRevoked); }
    catch (e) { throw mapFirebaseError(e); }                       // E5
    const provider = ALLOWED.get(d.firebase?.sign_in_provider as any);
    if (!provider) throw new BadRequestException({ code: 'UNSUPPORTED_AUTH_PROVIDER' });
    const ids = (d.firebase?.identities ?? {}) as Record<string, unknown>;
    const sub = Array.isArray(ids[d.firebase.sign_in_provider]) ? String((ids[d.firebase.sign_in_provider] as unknown[])[0]) : d.uid;
    const linkedProviders = Object.keys(ids).filter((p) => ALLOWED.has(p as any));   // providers linked on this Firebase user (J1)
    return { firebaseUid: d.uid, provider, providerUserId: sub, linkedProviders, email: d.email?.toLowerCase(),
             emailVerified: d.email_verified === true, name: d.name, picture: d.picture, authTime: d.auth_time };
  }
}
```
Based on [VGA] Buzz `firebase-auth.verifier.ts` (adds `checkRevoked`, provider rejection, and 503 vs 401 split). With `checkRevoked=true` the Node SDK first checks whether the user is disabled (`auth/user-disabled`) and then revocation (`auth/id-token-revoked`) [DOCS Node `BaseAuth.verifyIdToken` reference].

## E3. SocialLoginService (linking per social-login.md B8)
```ts
async login(dto: SocialLoginDto, ctx: DeviceCtx) {
  const id = await this.verifier.verify(dto.idToken);
  let isNewUser = false;
  let user = await this.users.findOne({ firebaseUid: id.firebaseUid });
  if (!user && id.email && id.emailVerified) {                                   // NEVER without emailVerified (Outlet gap)
    const byEmail = await this.users.findOne({ email: id.email, deletedAt: null }); // soft-deleted rows never capture a new login
    if (byEmail) {
      if (byEmail.actorType !== 'user') throw conflict('ACCOUNT_ROLE_CONFLICT');
      if (byEmail.passwordHash && !byEmail.emailVerifiedAt) throw conflict('LOGIN_WITH_PASSWORD_TO_LINK');
      user = await this.users.findOneAndUpdate({ _id: byEmail._id, firebaseUid: { $exists: false } },
        { $set: { firebaseUid: id.firebaseUid, ...(id.provider === 'APPLE' ? { appleSub: id.providerUserId } : {}) },
          $addToSet: { providers: { $each: id.linkedProviders } } }, { new: true });   // providers stored as 'google.com' / 'apple.com'
      if (!user) {                                        // already bound: same uid (concurrent link) or ANOTHER uid
        user = await this.users.findOne({ _id: byEmail._id, firebaseUid: id.firebaseUid });   // concurrent request won with the same uid
        if (!user) throw conflict('ACCOUNT_LINK_CONFLICT');  // e.g. Firebase deleteUser + re-signup gave a new uid -> support / J1 relink flow
      }
    }
  }
  if (!user) {
    try {
      user = await this.users.create({ firebaseUid: id.firebaseUid,
        email: id.emailVerified ? id.email : undefined,              // unverified email is never stored in the unique `email` field
        emailVerifiedAt: id.emailVerified ? new Date() : null,
        name: sanitizeName(dto.name ?? id.name), providers: id.linkedProviders,
        appleSub: id.provider === 'APPLE' ? id.providerUserId : undefined,   // account-flows.md J3 lookup key
        role: 'CUSTOMER' /* server-side only */ });
      isNewUser = true;
    } catch (e) {
      const key = dupKeyField(e);
      if (key === 'firebaseUid') user = await this.users.findOne({ firebaseUid: id.firebaseUid });  // concurrent first login: other request created it
      else if (key === 'email') throw conflict('ACCOUNT_LINK_CONFLICT');   // email taken by an account we may not auto-link (other uid / not deleted-anonymised)
      else throw e;
      if (!user) throw conflict('ACCOUNT_LINK_CONFLICT');                  // defensive: never dereference null
    }
  }
  if (user.deletedAt) throw forbidden('ACCOUNT_DELETED');      // only reachable inside a restore grace period (see below)
  if (!user.isActive) throw forbidden('ACCOUNT_DISABLED');
  this.audit.log('auth.social.login', { userId: user.id, provider: id.provider, isNewUser, ip: ctx.ip });
  return { user: toPublic(user), ...(await this.tokens.issue(user, ctx)), isNewUser };
}
```
Rules behind the code:
- `isNewUser` is `true` only when THIS request inserted the row. The concurrent loser re-reads the winner's row and returns `isNewUser=false` - the client must not run onboarding twice; onboarding state should live on the user (`profileCompletedAt`) rather than rely on `isNewUser` alone.
- Profile capture on first login only: `name` (Apple hint, social-login.md B6) and `picture` are written in `create`, never overwritten on later logins (user edits win). Returning users: `$addToSet providers` from `id.linkedProviders`, backfill `appleSub` if missing, store the Apple refresh token if `appleAuthorizationCode` was sent (account-flows.md J4), update `lastLoginAt`.
- **Account deletion must free the identifiers**: on deletion (immediately, or when the restore grace period ends via a purge job) set `email = 'deleted+<id>@invalid.local'`, `$unset firebaseUid` (keep `deletedFirebaseUid` for audit), clear phone. Otherwise the unique indexes make the email/uid unusable forever. During a grace period the row keeps `firebaseUid`, so the same Firebase user gets `ACCOUNT_DELETED` (restore flow, Outlet offers restore); a re-signup with a NEW uid but the same email is not captured by `byEmail` (filtered on `deletedAt: null`) but WOULD collide on the unique `email` index -> 409 `ACCOUNT_LINK_CONFLICT` until purge; state the product choice (shorter grace or anonymise immediately).
- `ACCOUNT_LINK_CONFLICT` support path: the user signs in with the method already bound to the account and uses explicit linking (account-flows.md J1), or support relinks after identity checks.

## E4. TokenService (Sanad model + fixes) and guard
```ts
async issue(actor, ctx): Promise<TokenPair> {
  const now = new Date();
  const refresh = randomBytes(32).toString('hex');
  const session = await this.sessions.create({ actorId: actor.id, actorType: actor.actorType, tokenHash: sha256(refresh),
    jti: randomUUID(), deviceId: ctx.deviceId, ip: ctx.ip, userAgent: ctx.userAgent?.slice(0, 256),
    createdAt: now, expiresAt: addDays(now, this.cfg.refresh.ttlDays) });
  const accessToken = this.jwt.sign({ sub: actor.id, typ: actor.actorType, role: actor.role, sid: session.id, tv: actor.tokenVersion ?? 0 },
    { secret: this.cfg.access.secret, expiresIn: this.cfg.access.ttl, audience: this.cfg.access.aud, issuer: this.cfg.issuer, jwtid: session.jti });
  return { accessToken, refreshToken: refresh, tokenType: 'Bearer', expiresIn: ttlSeconds(this.cfg.access.ttl), sessionId: session.id };  // expiresIn from config, not hardcoded
}
async rotate(raw: string, ctx) {   // Sanad atomic claim + reuse => revoke all, WITH the expiry fix
  const now = new Date();
  const hash = sha256(raw);
  const claimed = await this.sessions.findOneAndUpdate(
    { tokenHash: hash, revokedAt: { $exists: false }, expiresAt: { $gt: now } },   // expiry IN the filter: an expired token is never claimed
    { $set: { revokedAt: now, revokeReason: 'ROTATED', lastUsedAt: now } });
  if (claimed) {
    const actor = await this.actors.load(claimed.actorType, claimed.actorId);          // re-check active/deleted at every refresh
    if (!actor || actor.deletedAt) throw forbidden('ACCOUNT_DELETED');
    if (!actor.isActive) throw forbidden('ACCOUNT_DISABLED');
    const pair = await this.issue(actor, ctx);
    await this.sessions.updateOne({ _id: claimed._id }, { replacedBy: pair.sessionId });  // [NEW] forensics
    return pair;
  }
  const existing = await this.sessions.findOne({ tokenHash: hash });                // non-mutating: tell the cases apart
  if (existing?.revokedAt && existing.expiresAt > now) {                            // revoked AND still within its life = reuse
    await this.sessions.updateOne({ _id: existing._id }, { reusedAt: now });
    await this.revocation.revokeAll(existing.actorType, existing.actorId, 'REFRESH_REUSE');  // D4 incl. Firebase revoke + FCM clearAll
  }
  throw unauthorized('REFRESH_INVALID');      // same body for unknown / expired / reused - no oracle
}
async logout(raw: string) {
  // Sanad revokeRefreshToken: read owner (even if already revoked), then
  // updateOne({tokenHash, revokedAt absent}, {revokedAt: now, revokeReason: 'LOGOUT'}); idempotent; return owner for FCM cleanup
}
```
**KNOWN SANAD BUG (verified read-only in `Sanad/backend/src/modules/auth/token.service.ts` ~79-95):** the claim filter is `{ tokenHash, revokedAt: { $exists: false } }` with no expiry condition; the expiry is checked AFTER `revokedAt` was already set. An expired refresh token is therefore claimed (marked revoked) and returns 401; if the client retries the same token (network retry, second tab, app restart), the row is now revoked -> reuse detection -> `revokeAllSessions` logs the user out on every device. Fix = the `expiresAt: { $gt: now }` filter above (or a non-mutating `findOne` expiry pre-check before the claim) AND only treat a revoked row as reuse while it is unexpired. Do not copy the Sanad snippet unchanged.

**Guard (`JwtAuthGuard`)**: verify signature with access secret + `audience` + `issuer` + `clockTolerance: 30`; load actor (cached 30-60s) -> reject if missing, `!isActive`, `deletedAt`, `payload.tv !== actor.tokenVersion`, or `payload.iat < actor.tokensValidBeforeSec` (see "Timestamp precision" below); **session check (single-session revoke, [NEW])**: load `auth_sessions` by `_id = payload.sid` (indexed `_id`; cache together with the actor) and reject 401 `SESSION_REVOKED` if the row is missing or `revokedAt` is set with `revokeReason !== 'ROTATED'` (a normal rotation revokes the old row while its access token is still legitimately in flight). Residual window: an access token minted BEFORE the last rotation of a session that is then logged out still points at a `ROTATED` row and lives until its short expiry; to close it, follow `replacedBy` to the chain head (cache it) or use the Redis variant keyed per chain. Cheaper alternative at scale: `revokeSession`/`logout` write Redis `revoked:sid:{sid}` with TTL = access TTL and the guard checks that key. Optional Redis `banned:{sub}` check. Attach actor from DB (roles from DB, not payload). Separate guard/strategy per actor audience.

**Timestamp precision** (`tokensValidBefore` kill-switch): JWT `iat` has 1-second precision. If you store `tokensValidBefore = new Date()` (ms) and compare `iat*1000 < tokensValidBefore`, a NEW pair issued in the same second right after the bump (password change: "keep caller logged in, issue new pair") has `iat*1000 <= tokensValidBefore` and is rejected for its whole life. Rules:
- Store the cut-off FLOORED to whole seconds: `tokensValidBeforeSec = Math.floor(Date.now()/1000)`; guard rejects only `payload.iat < tokensValidBeforeSec`. Tokens minted in that same second are accepted (a <=1 s window for old tokens; acceptable).
- For flows that revoke everything and immediately issue a new pair (password/phone/email change), prefer `tokenVersion++` (`tv`) - exact, no clock involved - and issue the new pair AFTER the increment so it carries the new `tv`.
- Firebase uses the same granularity: `tokensValidAfterTime` is compared in seconds against the ID token (the official samples divide it by 1000 "in seconds") [DOCS manage-sessions].

## E5. Error-code -> HTTP mapping
| Condition | HTTP | Body `code` | Client action |
| --- | --- | --- | --- |
| Firebase `auth/id-token-expired` | 401 | `TOKEN_EXPIRED` | `getIdToken(true)` and retry once |
| Firebase `auth/id-token-revoked`, `auth/user-not-found` | 401 | `TOKEN_REVOKED` | full re-login |
| Firebase `auth/argument-error`, `auth/invalid-id-token`, `auth/invalid-argument`, wrong project | 401 | `TOKEN_INVALID` | re-login |
| Firebase `auth/user-disabled`; our `isActive=false`/banned | 403 | `ACCOUNT_DISABLED` | show support message, do NOT retry |
| Soft-deleted account (grace period) | 403 | `ACCOUNT_DELETED` | restore flow or message |
| Email belongs to other role (staff/admin) | 409 | `ACCOUNT_ROLE_CONFLICT` | message |
| Email account is password-based and unverified | 409 | `LOGIN_WITH_PASSWORD_TO_LINK` | sign in with password, then link (account-flows.md J1) |
| Email account already bound to another Firebase uid / email taken | 409 | `ACCOUNT_LINK_CONFLICT` | sign in with the existing method, or contact support |
| Explicit link: provider identity already used by another account | 409 | `PROVIDER_ALREADY_LINKED` | message (account-flows.md J1) |
| Unlink would remove the last login method | 409 | `LAST_LOGIN_METHOD` | add another method first (J1) |
| Verified phone already belongs to another account | 409 | `PHONE_IN_USE` | sign in with phone, then link (account-flows.md J2) |
| Unsupported provider | 400 | `UNSUPPORTED_AUTH_PROVIDER` | - |
| Firebase not configured / network / `app/*` / cert fetch failure (Python `CertificateFetchError`) | 503 | `AUTH_PROVIDER_UNAVAILABLE` | retry later (never authenticate) |
| Access JWT expired/invalid | 401 | `ACCESS_EXPIRED` / `ACCESS_INVALID` | refresh then retry once |
| Access JWT whose session (`sid`) was revoked | 401 | `SESSION_REVOKED` | clear tokens, re-login (do not refresh) |
| Refresh invalid/expired/reused | 401 | `REFRESH_INVALID` | clear tokens, re-login |
| Valid token, insufficient role | 403 | `FORBIDDEN` | - |
| Rate limited | 429 | `TOO_MANY_REQUESTS` | backoff |
Rule: 401 = "who are you?" (re-auth may fix it); 403 = "known, not allowed" (re-auth will not fix it); 409 = "identity is fine, account state conflicts". Bilingual `message`/`messageAr` per VGA convention [VGA Sanad].
Node `mapFirebaseError`: switch on `e.code` (`auth/...`); anything that is not an `auth/*` token/user error (e.g. `app/network-error`, `auth/internal-error` on certificate fetch [UNVERIFIED exact Node code for cert-fetch failure]) -> 503, never 401 and never success.

## E6. Endpoints and DTOs
| Method + path | Auth | Body | Result |
| --- | --- | --- | --- |
| `POST /auth/social` | public, rate-limited | `{ idToken: string(20..4096), deviceId?: string(<=128), name?: string(<=100), language?: 'ar'|'en', appleAuthorizationCode?: string(<=512) }` | user + token pair + `isNewUser` (+ `firebaseCustomToken` only if C1 applies) |
| `POST /auth/otp/request`, `POST /auth/otp/verify` | public, rate-limited | phone + code | phone-OTP path -> same `issue()` (account-flows.md J2) |
| `POST /auth/refresh` | public (refresh token is the credential), rate-limited | `{ refreshToken: string(64) }` or httpOnly cookie | new pair |
| `POST /auth/logout` | refresh token in body/cookie (access optional) | `{ refreshToken, fcmToken? }` (Sanad names it `deviceToken`) | 204, idempotent; removes THIS device's FCM token server-side (owner resolved from the refresh token) |
| `POST /auth/logout-all` | access JWT | - | 204; revocation D4 |
| `GET /auth/sessions` / `DELETE /auth/sessions/:id` | access JWT | - | list (ip, userAgent, deviceId, createdAt, lastUsedAt, `current: sid === payload.sid`) / revoke one (ownership check, 404 if not owned) |
| `POST /auth/link` | access JWT, rate-limited | `{ idToken }` | link Google/Apple to the caller (account-flows.md J1) |
| `DELETE /auth/providers/:provider` | access JWT + recent auth | - | unlink; 409 `LAST_LOGIN_METHOD` guard (J1) |
| `POST /admin/users/:id/force-logout` | admin JWT + role | `{ reason }` | 204; revocation D4; audit |
| `POST /admin/users/:id/ban` / `unban` | admin | `{ reason }` | D1 rows |
| `DELETE /me` | access JWT + recent auth | `{ idToken? (fresh, auth_time<5m), appleAuthorizationCode? }` | deletion per D1 |
| `DELETE /admin/users/:id` | admin | `{ reason }` | deletion per D1 incl. Apple revoke from stored token (account-flows.md J4) |
| `POST /webhooks/apple/sign-in-notifications` | public, verified by Apple JWS signature | Apple payload | account-flows.md J3 |
| `POST /auth/firebase-token` (C1 only) | access JWT | - | `{ customToken }` for caller's own uid |
Never put tokens in URL paths/query strings. `ValidationPipe({ whitelist: true, forbidNonWhitelisted: true })`. Route classes for the client 401 interceptor (client.md F3): `/auth/refresh`, `/auth/social`, `/auth/logout`, `/auth/otp/*` do NOT use the access JWT; `/auth/logout-all`, `/auth/sessions*`, `/auth/link`, `/auth/providers/*` DO.

## E7. Rate limiting, audit, clock skew
- `@nestjs/throttler`: `/auth/social`, `/auth/refresh`, `/auth/otp/*`, `/auth/link` e.g. 10/min per IP + per deviceId (OTP also per phone); admin routes stricter. Behind proxy set `trust proxy` correctly.
- Audit events: `auth.social.login`, `auth.otp.login`, `auth.refresh.reuse_detected` (WARN), `auth.logout`, `auth.logout_all`, `auth.session_revoked`, `auth.provider_linked`, `auth.provider_unlinked`, `auth.force_logout`, `auth.ban`, `auth.account_deleted`, `auth.apple_notification`, `auth.claims_changed`. Fields: actor, target, ip, userAgent, sessionId, reason. NEVER log tokens, ID tokens, refresh tokens, Apple codes/tokens, OTPs, private keys; at most last 6 chars of a token hash.
- Clock skew: own JWT `clockTolerance: 30`. Firebase: the Node Admin SDK `verifyIdToken(idToken, checkRevoked?)` exposes NO clock-tolerance option (signature verified in the Node reference) [DOCS]; whether it applies any internal leeway is [UNVERIFIED] - assume none. Python `verify_id_token(..., clock_skew_seconds=0)` accepts 0-60 seconds, default 0 [DOCS]. A server clock that is off by more than a few seconds therefore causes spurious `TOKEN_INVALID` ("used before issued") on fresh ID tokens and wrong `revokeRefreshTokens` cut-offs (Firebase's reference warns the server clock must be synchronized [DOCS]) -> run NTP (chrony/systemd-timesyncd; managed platforms do this) and alert on drift.

## E8. Schemas and indexes
```ts
// users (add)
firebaseUid?: string     // index { firebaseUid: 1 }, { unique: true, sparse: true }  (or partialFilterExpression {firebaseUid: {$type: 'string'}})
email?: string           // unique with partialFilterExpression {email: {$type: 'string'}}; anonymised on deletion (E3)
phone?: string           // E.164, unique partial; set by the OTP path (account-flows.md J2)
providers: string[]; emailVerifiedAt?: Date; phoneVerifiedAt?: Date; passwordHash?: string
tokenVersion: number (default 0); tokensValidBeforeSec?: number   // whole seconds (E4 timestamp precision)
isActive: boolean; deletedAt?: Date; deletedFirebaseUid?: string
appleSub?: string               // index { appleSub: 1 } unique sparse; Apple notifications lookup (account-flows.md J3)
emailForwardingEnabled?: boolean // Apple relay email forwarding state (J3)
appleRefreshTokenEnc?: string   // AES-256-GCM ciphertext, key from secret manager (account-flows.md J4); never returned by toPublic
// auth_sessions
{ actorId: ObjectId, actorType: string, tenantId?: ObjectId, tokenHash: string, jti: string, deviceId?: string,
  ip?: string, userAgent?: string, createdAt: Date, lastUsedAt?: Date, expiresAt: Date,
  revokedAt?: Date, revokeReason?: 'ROTATED'|'LOGOUT'|'SESSION_REVOKED'|'LOGOUT_ALL'|'REFRESH_REUSE'|'FORCE_LOGOUT'|'BAN'|'DELETED',
  reusedAt?: Date, replacedBy?: ObjectId }
// indexes
{ tokenHash: 1 } unique
{ actorId: 1, actorType: 1, revokedAt: 1 }          // revoke-all, list sessions
{ jti: 1 } unique                                   // denylist / forensics
{ purgeAt: 1 } expireAfterSeconds: 0  with purgeAt = expiresAt + 7d   (or { expiresAt: 1 } expireAfterSeconds: 0)
```
Note: with the E4 fix, reuse detection only fires for unexpired revoked rows, so purging rows at `expiresAt` loses nothing; keeping them 7 more days helps forensics only.

## E9. FastAPI / Express equivalence
- FastAPI: `firebase_admin.initialize_app(credentials.Certificate(json.loads(os.environ['FIREBASE_SERVICE_ACCOUNT_JSON'])), name='auth')`; `auth.verify_id_token(tok, app=app, check_revoked=True, clock_skew_seconds=5)` (0-60 allowed [DOCS]). **Catch order matters**: `ExpiredIdTokenError` and `RevokedIdTokenError` are SUBCLASSES of `InvalidIdTokenError` [DOCS Python reference], so catch them first:
  ```python
  try: d = auth.verify_id_token(tok, app=app, check_revoked=True, clock_skew_seconds=5)
  except auth.RevokedIdTokenError: raise HTTPException(401, {'code': 'TOKEN_REVOKED'})
  except auth.ExpiredIdTokenError: raise HTTPException(401, {'code': 'TOKEN_EXPIRED'})
  except auth.UserDisabledError: raise HTTPException(403, {'code': 'ACCOUNT_DISABLED'})
  except auth.CertificateFetchError: raise HTTPException(503, {'code': 'AUTH_PROVIDER_UNAVAILABLE'})
  except auth.InvalidIdTokenError: raise HTTPException(401, {'code': 'TOKEN_INVALID'})
  except (ValueError, firebase_admin.exceptions.FirebaseError): raise HTTPException(503, {'code': 'AUTH_PROVIDER_UNAVAILABLE'})  # never authenticate
  ```
  (`UserDisabledError` subclasses `InvalidArgumentError`, not `InvalidIdTokenError`; `CertificateFetchError` subclasses `UnknownError` [DOCS].) Use a `Depends(get_current_user)` that does the guard checks ([VGA] Cozzy `tv` check). Separate `JWT_ACCESS_SECRET` / `JWT_REFRESH_SECRET`; startup assert no dev bypass and no `FIREBASE_AUTH_EMULATOR_HOST` when `ENVIRONMENT != development`.
- Express: same admin calls; middleware `requireAuth` = guard E4; `express-rate-limit`; refresh cookie via `res.cookie('rt', v, { httpOnly: true, secure: true, sameSite: 'strict', path: '/auth' })`.
