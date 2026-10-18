# A + B. Decision guide and Google/Apple social login end-to-end

## A. Which token pattern

| Need | Use | Why | VGA status |
| --- | --- | --- | --- |
| Backend owns users, roles, sessions; client calls only our API | (i) Verify Firebase ID token once at login -> issue own access + refresh | Firebase only proves identity; we control TTL, revocation, roles, multi-actor | [VGA] Al Mudarib, Buzz, Outlet, Cozzy |
| User logged in via OUR backend (phone OTP, email/password, legacy) but the client must ALSO read/write Firestore / RTDB / Storage under Security Rules, or call Firebase callable functions as that user | (ii) `createCustomToken(uid, claims)` -> client `signInWithCustomToken` | Gives the client a Firebase Auth identity so `request.auth.uid` / `request.auth.token.role` work in rules | [NEW] not used anywhere in VGA |
| Server-rendered web dashboard wanting Firebase-managed httpOnly cookie | (iii) `createSessionCookie(idToken, {expiresIn})` + `verifySessionCookie(cookie, true)` | No client-side token refresh; 5 min-2 weeks lifetime [DOCS] | [NEW] not used in VGA; implementation notes in account-flows.md J5 (out of scope for current VGA dashboards) |
| No Firebase project wanted | Pattern 2: verify Google ID token (google-auth-library, aud = client IDs) and Apple identity token (Apple JWKS, aud = bundle/services ID, nonce) directly | One fewer vendor | [VGA] Amirni, Vetrina, CareLink |

Decision rules:
- Do NOT mint custom tokens just because "we use Firebase". If nothing on the client uses Firebase-secured data, (i) alone is complete.
- FCM push does not need a Firebase Auth user; device tokens are registered with our API (`aks-fcm-webpush`).
- (i) and (ii) can coexist: OTP users get our JWT + a custom token; social users already have a Firebase session (custom token unnecessary for them, but set custom claims if rules need roles).
- Never use the Firebase ID token itself as the API bearer for every request in a backend with its own roles: 1h TTL, revocation requires a network call, roles live in claims you must sync. (Acceptable for small Firebase-native backends; mark as an explicit decision.)
- Phone login through our own SMS gateway is a separate path into the same `issue()`; do not mix it with Firebase Phone Auth (account-flows.md J2).

## B1. Firebase console (once per project)
1. Authentication -> Sign-in method -> enable **Google** (set project support email) and **Apple**.
2. Apple provider: for iOS-native only, the bundle ID is enough. For web/Android Apple sign-in also fill Services ID, Apple Team ID, Key ID, private key (.p8) - the .p8 goes into the console, never into git. Copy the OAuth redirect URI shown (`https://<PROJECT_ID>.firebaseapp.com/__/auth/handler`) into the Apple Services ID "Return URLs" (Apple Developer -> Identifiers -> Services IDs -> Sign in with Apple -> Configure). If the backend exchanges Apple codes / receives Apple notifications (account-flows.md J3/J4), it needs its own Sign in with Apple key (.p8 in the secret manager) and the notification endpoint registered on the App ID.
3. Authentication -> Settings -> **Authorized domains**: add every web origin (prod, staging, custom auth domain). Remove `localhost` in prod-only projects if not needed.
4. Settings -> **User account linking**: choose "Link accounts that use the same email" (default, recommended) vs "Create multiple accounts for each identity provider". Our backend linking policy (B8) must match this choice.
5. Project settings -> Service accounts -> generate the Admin key ONLY into the secret manager / CI secret; never download into the repo. Prefer a dedicated service account with the **Firebase Authentication Admin** role (`roles/firebaseauth.admin`). If `createCustomToken` is used without a private key (ADC on GCP), the runtime service account needs `iam.serviceAccounts.signBlob` (grant **Service Account Token Creator**) AND the **IAM Service Account Credentials API** (`iamcredentials.googleapis.com`) must be enabled in the project - otherwise signing fails with an "IAM API is not enabled" error [DOCS create-custom-tokens troubleshooting].

## B2. Android
- Register the Android app with the exact `applicationId`.
- Add **SHA-1 and SHA-256** fingerprints for: debug keystore (each dev machine or a shared debug keystore), the upload key, AND the **Play App Signing** key (Play Console -> Setup -> App integrity). Missing Play signing SHA = Google sign-in works in debug/internal builds but fails in Play-installed builds (`ApiException: 10` / DEVELOPER_ERROR).
- Re-download `google-services.json` after adding fingerprints (it embeds OAuth client IDs). It contains public identifiers, not secrets; committing it is normal practice, but keep per-flavor files per environment.
- Apple sign-in on Android goes through Firebase's web flow (`signInWithProvider(AppleAuthProvider())`) and needs the Services ID config from B1. [UNVERIFIED] Apple `authorizationCode` may be null on Android in FlutterFire - affects B6 revocation (another reason to store the Apple refresh token server-side at first sign-in where a code IS available, J4).

## B3. iOS
- Xcode -> Signing & Capabilities -> **Sign in with Apple**; also enable it on the App ID in Apple Developer.
- `GoogleService-Info.plist` in Runner target; add URL Types: `REVERSED_CLIENT_ID` from that plist (Google sign-in callback). For google_sign_in v6+/v7 also `GIDClientID` (and `GIDServerClientID` if a server client id is used) in Info.plist if the plugin docs require it [UNVERIFIED: depends on plugin version].
- App Store rule 4.8: if the app offers Google (third-party) login, it must also offer Sign in with Apple (or an equivalent privacy login) on iOS [UNVERIFIED: re-read current guideline text].

## B4. Web (dashboards)
- `signInWithPopup` for desktop dashboards (simple, keeps SPA state). `signInWithRedirect` for mobile browsers / when popups are blocked; since browsers block third-party storage, redirect requires `authDomain` to be the app's own domain or a reverse-proxy of `/__/auth/*` [UNVERIFIED: re-check Firebase "redirect best practices" page].
- After sign-in: `await user.getIdToken()` -> POST to `/auth/social`. Then optionally `signOut()` from Firebase if the dashboard only uses our session (reduces dual-session confusion) - [VGA] Buzz dashboard pattern is popup -> ID token -> backend.

## B5. Flutter flow (firebase_auth + google_sign_in + sign_in_with_apple)
Two separate snippets - do not share variables between them.

**Google, google_sign_in v7 (2025+; pin the major version in pubspec, e.g. `google_sign_in: ^7.x`)** - v7 is a singleton that must be initialized once, separates authentication from authorization, and `authentication` carries only an `idToken` (no `accessToken`) [DOCS pub.dev changelog + MIGRATION.md; exact signatures below UNVERIFIED - check the package README for your version]:
```dart
// once at app start
await GoogleSignIn.instance.initialize(serverClientId: '<WEB_CLIENT_ID>');   // param names per platform [UNVERIFIED]

Future<void> signInWithGoogle(String deviceId) async {
  final GoogleSignInAccount account;
  try {
    account = await GoogleSignIn.instance.authenticate();   // replaces signIn(); user cancel -> GoogleSignInException (canceled) [UNVERIFIED code name]
  } on GoogleSignInException catch (e) {
    if (e.code == GoogleSignInExceptionCode.canceled) return; // cancel is not an error
    rethrow;
  }
  final idToken = account.authentication.idToken;           // v7: no accessToken here; scopes/access tokens via authorizationClient
  final cred = GoogleAuthProvider.credential(idToken: idToken);
  await FirebaseAuth.instance.signInWithCredential(cred);
  final firebaseIdToken = await FirebaseAuth.instance.currentUser!.getIdToken();   // Firebase ID token, NOT the Google one
  await api.post('/auth/social', {'idToken': firebaseIdToken, 'deviceId': deviceId});
}
```
On web, `authenticate()` may be unsupported (check `GoogleSignIn.instance.supportsAuthenticate()`; web uses the plugin's rendered button) [UNVERIFIED]. Sign-out: `GoogleSignIn.instance.signOut()` / `disconnect()`.

**Google, legacy v6 form** (only if the project is pinned to `google_sign_in: ^6.x`):
```dart
final g = await GoogleSignIn().signIn();                    // null => user cancelled
if (g == null) return;
final ga = await g.authentication;
await FirebaseAuth.instance.signInWithCredential(
    GoogleAuthProvider.credential(idToken: ga.idToken, accessToken: ga.accessToken));
final firebaseIdToken = await FirebaseAuth.instance.currentUser!.getIdToken();
await api.post('/auth/social', {'idToken': firebaseIdToken, 'deviceId': deviceId});
// sign-out: GoogleSignIn().signOut()
```

**Apple (iOS native)**:
```dart
Future<void> signInWithApple(String deviceId) async {
  final rawNonce = generateNonce();                          // 32+ random chars
  final hashed = sha256.convert(utf8.encode(rawNonce)).toString();
  final a = await SignInWithApple.getAppleIDCredential(
    scopes: [AppleIDAuthorizationScopes.email, AppleIDAuthorizationScopes.fullName], nonce: hashed);
  final oauth = OAuthProvider('apple.com').credential(idToken: a.identityToken, rawNonce: rawNonce);
  // [UNVERIFIED] some firebase_auth versions use AppleAuthProvider.credentialWithIDToken(idToken, rawNonce, fullName)
  await FirebaseAuth.instance.signInWithCredential(oauth);
  final firebaseIdToken = await FirebaseAuth.instance.currentUser!.getIdToken();
  await api.post('/auth/social', {
    'idToken': firebaseIdToken, 'deviceId': deviceId,
    'name': [a.givenName, a.familyName].whereType<String>().join(' '),   // non-null only on FIRST authorization (B6)
    'appleAuthorizationCode': a.authorizationCode,                       // single-use; backend exchanges it (J4)
  });
}
// Alternative: FirebaseAuth.instance.signInWithProvider(AppleAuthProvider()) - Firebase handles the nonce.
```
The authorization code is single-use: give it to ONE consumer. If the backend exchanges it (J4), do not also pass it to Firebase as `accessToken` [UNVERIFIED whether Firebase consumes it]; if you use FlutterFire `revokeTokenWithAuthorizationCode` at deletion, get a fresh code then.
Rules: send the Firebase **ID token** (never only email / uid / loginType - FitFinds gap). Send Apple `givenName/familyName` in the same request as a hint (B6). Handle `FirebaseAuthException` codes `account-exists-with-different-credential` (B8), `network-request-failed`, user cancel.

## B6. Apple quirks
- **Nonce**: client sends SHA-256(rawNonce) to Apple, raw nonce to Firebase; Firebase checks it. Backend only sees the Firebase ID token, so nonce is client-side in Pattern 1. In Pattern 2 (direct Apple verify) the backend must compare the token `nonce` claim with the expected hash.
- **What is first-time-only**: the user's **name** (`fullName` / `givenName` / `familyName`) and the `email` FIELD of the native credential object are returned only on the first authorization. The Apple **identity token** carries the `email` claim (real or relay) on every login once the user shared it, so the Firebase ID token normally has `email` on returning logins too. The name is NOT in the Firebase ID token; take it from the client hint, only on user creation, sanitized and length-limited.
- **Private relay emails** (`...@privaterelay.appleid.com`): treat as a valid but unlinkable-by-human email; outbound mail to it requires registering our sending domains in Apple Developer (Email Communication). Do not use it to auto-link to an existing password account unless `email_verified` (Apple emails are reported verified [UNVERIFIED]) AND policy allows. Forwarding can be turned off/on by the user - Apple sends `email-disabled` / `email-enabled` notifications (J3).
- **Stable identity**: Apple's `sub` is stable for the same user across all apps of the same developer team (it differs across teams), so hiding the email or changing the relay address does not change the Firebase uid; key on `firebaseUid`, not email. A user who revokes the app's access (Settings -> Apple ID -> Sign in with Apple -> Stop using) keeps the same `sub` on the next sign-in but is shown the first-time consent again (name may be resent).
- **Account deletion (App Store 5.1.1(v))**: apps with account creation must offer in-app deletion; for Sign in with Apple users, revoke the Apple tokens.
  - User-initiated (Flutter): re-authenticate with Apple to get a fresh `authorizationCode`, call `FirebaseAuth.instance.revokeTokenWithAuthorizationCode(code)`, then delete the Firebase user and our data [DOCS: FlutterFire federated-auth page]. Android may return a null code [UNVERIFIED community report].
  - Backend REST revoke (fallback for null code, and the ONLY option for admin-initiated deletion): `POST https://appleid.apple.com/auth/revoke` requires a `token` (an Apple **refresh or access token**, `token_type_hint`), `client_id`, and a `client_secret` JWT signed with the Apple .p8 key - an authorization code is NOT accepted there. The token is obtained by exchanging the authorization code at `POST https://appleid.apple.com/auth/token` (`grant_type=authorization_code`). Therefore the backend must exchange the code AT SIGN-IN (it is short-lived and single-use) and store the Apple refresh token encrypted; otherwise an admin cannot revoke Apple when the user is not present. Full flow: account-flows.md J4 [UNVERIFIED endpoint parameter details - Apple docs not fetchable in authoring session].
- **Server-to-server notifications** (consent revoked, account deleted, email forwarding changed) are NOT handled by Firebase - account-flows.md J3.

## B7. Backend verification (what verifyIdToken does and what YOU must add)
`verifyIdToken(token)` checks signature (Google x509 certs, cached by SDK), `alg=RS256`, `exp`, `iat`, `aud == projectId`, `iss == https://securetoken.google.com/<projectId>`, non-empty `sub`, `auth_time` in the past [DOCS manual-verification list; SDK does these]. It does NOT check revocation unless `checkRevoked=true` [DOCS].
You must add:
1. Named admin app initialized with an explicit `projectId` (Buzz `buzz-auth`) so aud is checked against the right project.
2. `checkRevoked: true` on the login exchange (one network call per login - cheap). With it, the Node SDK first checks for a disabled user and throws `auth/user-disabled`, then revocation `auth/id-token-revoked` [DOCS Node `BaseAuth.verifyIdToken` reference].
3. Provider allow-list on `decoded.firebase.sign_in_provider` (`google.com`, `apple.com`; add `phone`/`password` only deliberately - and never `phone` if phone login runs through our own SMS OTP, J2). [VGA] Outlet, Buzz.
4. `decoded.email_verified === true` before email-based linking. [GAP] Outlet links by email without this.
5. Optional freshness: reject if `now - auth_time > 5 min` for sensitive operations (re-auth for account deletion, unlink).
Error mapping (Node codes [DOCS errors page]): `auth/id-token-expired` -> 401 `TOKEN_EXPIRED` (client: `getIdToken(true)` and retry once); `auth/id-token-revoked` -> 401 `TOKEN_REVOKED` (client: full re-login); `auth/user-disabled` -> 403 `ACCOUNT_DISABLED`; `auth/argument-error` / `auth/invalid-id-token` / `auth/invalid-argument` (malformed, wrong project) -> 401 `TOKEN_INVALID`; `auth/user-not-found` (with checkRevoked, user deleted) -> 401; network/`app/*`/certificate-fetch errors -> 503 (fail closed, never authenticate). Full table: backend-nestjs.md E5. Log code + uid suffix, never the token.

## B8. Account linking policy
Order (code: backend-nestjs.md E3):
1. Find by `firebaseUid` (unique, sparse index) -> returning user.
2. Else, if `email` present AND `email_verified` AND a NON-deleted account with that email exists: link ONLY if that account's role is the same actor type (Outlet blocks non-CUSTOMER - good; else 409 `ACCOUNT_ROLE_CONFLICT`); set `firebaseUid`, add provider. If the existing account was password-based and unverified -> 409 `LOGIN_WITH_PASSWORD_TO_LINK` (prevents pre-registration takeover). If it is already bound to a DIFFERENT `firebaseUid` (e.g. after Firebase `deleteUser` + re-signup) -> 409 `ACCOUNT_LINK_CONFLICT`, never a silent overwrite and never a crash.
3. Else create (first login): role hard-coded server-side, never from client; store `email` / `emailVerifiedAt` only if `email_verified`; `isNewUser=true` only for the request that inserted.
- Deleted accounts must not block re-signup forever: anonymise email and unset `firebaseUid` on deletion (or at the end of the restore grace period) (backend-nestjs.md E3).
- Firebase console "one account per email" setting means a Google user later using Apple with the same email gets `account-exists-with-different-credential` on the client: fetch sign-in methods, sign in with the existing provider, then `linkWithCredential`. Firebase uid stays the same -> backend unaffected. Explicit, user-driven linking and unlinking (e.g. phone-only account adding Google): account-flows.md J1.
- Store `providers: ['google.com','apple.com']` and the underlying provider sub (`decoded.firebase.identities[provider][0]`, [VGA] Buzz `providerUserId`) for support/audit.
- Race: two concurrent first logins -> unique index on `firebaseUid` makes the second insert fail; catch duplicate key (11000), check WHICH key collided (`keyPattern`): `firebaseUid` -> re-read and continue; `email` -> 409 `ACCOUNT_LINK_CONFLICT`.

## B9. Disabled / deleted / banned at login
- Our DB: `isActive=false` / banned -> 403 `ACCOUNT_DISABLED`; soft-deleted within a restore grace period -> 403 `ACCOUNT_DELETED` (Outlet offers restore); after anonymisation the old row no longer matches, so the next login creates a new account - state the product decision.
- Firebase: `auth/user-disabled` -> 403. Keep both in sync: when banning in our DB also `updateUser(uid, {disabled: true})` (revocation.md D1).
- Never issue tokens before these checks; never create a user row for a disabled Firebase user.
