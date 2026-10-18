# F. Client side (Flutter + web)

## F1. Sign-in -> backend exchange
See `social-login.md` B5. Always POST the Firebase **ID token**; include `deviceId` (stable per install, e.g. a UUID in secure storage) so sessions are listable/revocable per device. Phone-OTP login: account-flows.md J2.

## F2. Storage
| Item | Flutter | Web dashboard |
| --- | --- | --- |
| Our refresh token | `flutter_secure_storage` (Keychain / Android Keystore-backed). Never SharedPreferences. | httpOnly + Secure + SameSite=Strict cookie scoped to `/auth` [NEW]; if the API is cross-site and cookies are impossible, memory + sessionStorage as last resort, never localStorage if avoidable |
| Our access token | memory (+ secure storage optional for cold start) | memory only |
| Firebase session | managed by firebase_auth SDK | managed by Firebase JS SDK (IndexedDB); call `signOut` after exchange if not needed |
| Custom token (C1) | never stored; use immediately | same |
Cookie-based refresh needs CSRF defence: SameSite=Strict + custom header (e.g. `X-Requested-With`) check on `/auth/refresh`, or a double-submit token.

## F3. Refresh: single-flight, 401 -> refresh -> retry once
Parallel requests that all get 401 and all call `/auth/refresh` with the same token: the first rotates, the others present a now-revoked token -> server reuse detection REVOKES ALL SESSIONS (Sanad) - the user is logged out by their own app. Fursatuk mitigates server-side with a 30s grace; the client must still de-duplicate.

Two rules the sketch enforces:
- **Log out only when the session is really dead**: refresh answered 401 `REFRESH_INVALID` / `TOKEN_REVOKED` / `SESSION_REVOKED`, or 403 `ACCOUNT_DISABLED` / `ACCOUNT_DELETED`. A network error, timeout, 5xx or 429 during refresh must NOT delete tokens - surface the error (offline banner / retry) and keep the refresh token for the next attempt.
- **Only skip the refresh-and-retry path for routes that do not use the access JWT**: `/auth/refresh`, `/auth/social`, `/auth/logout` (and `/auth/otp/*`). Routes like `/auth/logout-all`, `/auth/sessions`, `/auth/link`, `/auth/providers/*` DO use the access JWT and must get the normal refresh-then-retry (backend-nestjs.md E6).
```dart
// Dio interceptor sketch
class SessionDead implements Exception {}
const _noRefreshPaths = {'/auth/refresh', '/auth/social', '/auth/logout', '/auth/otp/request', '/auth/otp/verify'};
const _deadCodes = {'REFRESH_INVALID', 'TOKEN_REVOKED', 'SESSION_REVOKED', 'ACCOUNT_DISABLED', 'ACCOUNT_DELETED'};

Completer<String>? _refreshing;
Future<String> refreshOnce() {                                     // completes with a token, or errors
  if (_refreshing != null) return _refreshing!.future;             // join the in-flight refresh
  final c = _refreshing = Completer<String>();
  () async {
    try {
      final rt = await storage.read(key: 'rt');
      if (rt == null) throw SessionDead();
      final r = await rawDio.post('/auth/refresh', data: {'refreshToken': rt});   // rawDio: no interceptor loop
      await storage.write(key: 'rt', value: r.data['refreshToken']);               // persist BEFORE releasing waiters
      access = r.data['accessToken']; c.complete(access);
    } on DioException catch (e) {
      final data = e.response?.data;
      final code = data is Map ? data['code'] : null;
      final status = e.response?.statusCode;
      if ((status == 401 || status == 403) && _deadCodes.contains(code)) { c.completeError(SessionDead()); }
      else { c.completeError(e); }                                  // network / 5xx / 429: keep tokens
    } catch (e) { c.completeError(e); }
    finally { _refreshing = null; }
  }();
  return c.future;
}
onError: (e, h) async {
  final req = e.requestOptions;
  final path = req.uri.path;                                        // normalised (baseUrl + path)
  if (e.response?.statusCode == 401 && req.extra['retried'] != true && !_noRefreshPaths.any(path.endsWith)) {
    final String t;
    try { t = await refreshOnce(); }
    on SessionDead { await localLogout(); return h.next(e); }       // session really dead -> go to login (F4 steps 2-5)
    catch (_) { return h.next(e); }                                 // transient: surface the error, tokens kept
    req.extra['retried'] = true; req.headers['Authorization'] = 'Bearer $t';
    return h.resolve(await dio.fetch(req));                         // retry exactly once
  }
  if (e.response?.statusCode == 403) { /* ACCOUNT_DISABLED etc: show message, do not refresh */ }
  h.next(e);
}
```
- Web: same pattern with a module-level `refreshPromise` and the same two rules. Multiple tabs: use `BroadcastChannel` or a Web Lock (`navigator.locks.request('refresh', ...)`) so only one tab refreshes [NEW].
- Proactive refresh ~60s before `expiresIn` elapses reduces 401s; still keep the reactive path.
- Firebase ID token for the exchange: always call `getIdToken()` right before the call; the SDK returns the cached token or refreshes it when it is close to expiry. The pre-expiry threshold is platform dependent and not something to rely on (roughly 30 s in the JS SDK, ~5 min in the iOS SDK [UNVERIFIED exact values]); on `TOKEN_EXPIRED` call `getIdToken(true)` once.
- Claims changed (C2): on server signal, `currentUser.getIdToken(true)`.

## F4. Logout flow (order matters)
1. `POST /auth/logout { refreshToken, fcmToken }` - the server revokes the session row AND removes this device's FCM token (owner resolved from the refresh token; revocation.md D5). Best-effort; continue on network failure but queue a retry if possible.
2. FCM: call `aks-fcm-webpush`'s `disable()` helper (web `references/client.md` `disable()`; Flutter equivalent: DELETE + `FirebaseMessaging.instance.deleteToken()` + clear stored token) - not a raw `deleteToken()`. Its `DELETE /notifications/devices` is redundant after step 1: treat it as idempotent / skippable; the local `deleteToken()` and clearing the stored token are what matter.
3. `await FirebaseAuth.instance.signOut()`.
4. Google: google_sign_in v7 `await GoogleSignIn.instance.signOut()` (v6: `await GoogleSignIn().signOut()`). Use `disconnect()` only for "unlink Google" / account deletion - it revokes the grant. Apple has no client signOut; nothing to do.
5. Delete secure-storage entries (refresh, access, cached user); clear in-memory state and caches; navigate to login.
Logout-all: call `/auth/logout-all` with the access token (normal refresh-retry applies), then steps 2-5 locally (the server already ran `clearAll`, revocation.md D4). On receiving a dead-session code anywhere (F3 `_deadCodes`): run steps 2-5 without step 1.
Account deletion: re-auth (Apple: fresh authorization code, sent to the backend or used with `revokeTokenWithAuthorizationCode` - social-login.md B6), `DELETE /me`, then steps 2-5 (Google `disconnect()` instead of `signOut()`).
