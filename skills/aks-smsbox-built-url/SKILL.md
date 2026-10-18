---
name: aks-smsbox-built-url
description: Send SMS through SMSBox (Kuwait SMS gateway) by having the backend BUILD the SMSBox send URL and return it as `sms_url` (optionally `safe_url` with the password masked) so the dashboard or Flutter client sends the SMS with an HTTP GET. The backend never calls SMSBox itself because SMSBox geo-blocks non-Kuwait IPs. Use ONLY when the project uses SMSBox: the user mentions SMSBox, smsbox.com, Http_SendSMS, sms_url, safe_url, Kuwait SMS, or asks to add/review/fix SMS sending (OTP SMS, phone login, password reset by SMS) in a backend, dashboard, or Flutter app that uses SMSBox. If the project uses Dreams (dreams.sa), use skill aks-dreams-sms instead; if the SMS provider is unknown, ask.
user-invocable: true
---

# SMSBox via built URL (backend builds, client sends)

SMSBox rejects requests from non-Kuwait IPs, so our servers cannot call it.
**Rule 0: the backend ALWAYS builds the SMSBox send URL and returns it in the
API response; the client (dashboard / Flutter app) performs the HTTP GET.**
The backend never fetches SMSBox itself and never gets a delivery receipt.
**Applies only to SMSBox projects.** If the project uses Dreams, use skill
`aks-dreams-sms` (server-side send, different pattern). If the provider is unknown, ask.

## Gateway facts

- `GET https://smsbox.com/smsgateway/services/messaging.asmx/Http_SendSMS`
- Query params (camelCase as used in Caffeine/Al Mudarib/Outlet; casing was confirmed against a live account per the Vetrina `smsbox.provider.ts` comment (lines ~38-39); re-verify with a live test, do not use lowercase variants):
  `username`, `password`, `customerid`, `senderText`, `messageBody`,
  `recipientnumbers`, `defdate` (empty), `isblink=false`, `isflash=false`.
  Some projects (Al Mudarib) also add `isSMS=true`; keep it only if the project already has it.
- Env NAMES (values never in code, chat, or skills): `SMS_BASE_URL`, `SMS_USERNAME`,
  `SMS_PASSWORD`, `SMS_CUSTOMERID`, `SMS_SENDER`.
  In production, fail fast at startup if any is missing. No credential
  fallbacks in code, tests, or Flutter. Placeholders only: `<USER>`, `<PASS>`, `<CUST_ID>`, `<SENDER>`.
- Recipient: country-code digits, no `+`, no spaces (Kuwait: `965XXXXXXXX`). Normalise server-side.
- Reference implementations (read for style, do not copy secrets): Caffeine
  `backend/src/modules/common/services/smsbox.service.ts` (`buildSendUrl` via
  `URLSearchParams`); Al Mudarib `al-mudarib-backend` same path (correct `safeUrl`
  substitution); Outlet `apps/api` same path (recipient normalisation); CareLink
  `app/services/notification_service.py` `build_sms_url` (`urlencode`).
  Warning: Outlet's `smsbox.service.ts` (~line 59) builds `safeUrl` with
  `smsUrl.replace(encodeURIComponent(password), ...)`, the same bug class as Caffeine
  (rule 1); copy its recipient normalisation only, not its `safeUrl`.

## Rules (each one is a known past bug)

1. **Build with `URLSearchParams` / `urlencode`.** Never string concatenation.
   Build `safe_url` by constructing a second URL with `password=***`, never by
   string-replacing inside the real URL (Caffeine's bug leaves the password or breaks encoding).
2. **Keep `https`.** Never downgrade to `http` (Letsplay does).
3. **No hardcoded credential fallbacks** in backend or Flutter (FitFinds, Letsplay do; Caffeine too: 'dev' creds and a localhost base URL outside production, `smsbox.service.ts` ~41-55). Config comes from env only.
4. **Never log the full URL** (it contains the password). Log `safe_url`, recipient (masked), and outcome.
5. **OTP is generated on the server** (never on the device; FitFinds does). Store it HASHED
   with expiry, 60 s resend cooldown, max 5 verify attempts, then lock/invalidate.
   Compare in constant time.
6. **Never echo the raw OTP** in a response outside dev/test (Letsplay does). The code
   only travels inside `sms_url`'s `messageBody`.
7. **SMSBox ASMX reportedly returns HTTP 200 even on failure** (documented in CareLink
   `tests/test_otp_sms_qa.py`; verify with a live test). The client/QA must read the response
   body (it contains a status code/text), not just the HTTP status. See "Verify delivery" below.
8. **Sender ID**: use the approved sender registered on the SMSBox account (`<SENDER>`);
   unapproved or too-long sender text silently fails. Keep it in env.
9. **Unicode/Arabic is NOT handled in any existing project.** Treat existing messages as
   English-only. Before shipping Arabic, verify encoding against SMSBox docs and a live
   test on the real account (percent-encoded UTF-8 `messageBody`, any unicode flag, and
   per-message length limits). Do not assume it works.
10. Message text is localized per user language (when English-only is a limitation, fall
    back to English and tell the user).

## Security trade-off (state it plainly to the user)

The returned `sms_url` carries the SMSBox account password to every client that
requests it, and anyone who can call the endpoint can extract it. This is the accepted
design (geo-block workaround); do not change the design, but mitigate:

- Rate-limit the request-OTP endpoint per phone and per IP; the 60 s cooldown is server-enforced.
- Restrict who can call it (authenticated session, App Check/attestation, or known client where the flow allows).
- Short-lived responses: `Cache-Control: no-store`; never persist `sms_url` in client storage or logs.
- Use a dedicated low-balance SMSBox account/sub-user so a leak is bounded; rotate the password on any suspected leak.

## Backend sketch (NestJS, placeholders only)

```ts
@Injectable()
export class SmsBoxService {
  private readonly cfg = {
    base: env('SMS_BASE_URL'),             // https://smsbox.com/smsgateway/services/messaging.asmx/Http_SendSMS
    user: env('SMS_USERNAME'),             // <USER>
    pass: env('SMS_PASSWORD'),             // <PASS>
    cust: env('SMS_CUSTOMERID'),           // <CUST_ID>
    sender: env('SMS_SENDER'),             // <SENDER>
  };

  constructor() {
    // production-only validation: fail fast at boot if any value is missing
    if (process.env.NODE_ENV === 'production') {
      for (const [k, v] of Object.entries(this.cfg)) {
        if (!v) throw new Error(`SMSBox config missing: ${k}`);
      }
    }
  }

  buildSendUrl(rawPhone: string, message: string): { smsUrl: string; safeUrl: string } {
    const to = normalizeKw(rawPhone);      // digits only, 965 prefix, no '+'
    const make = (password: string) => {
      const q = new URLSearchParams({
        username: this.cfg.user, password,
        customerid: this.cfg.cust, senderText: this.cfg.sender,
        messageBody: message, recipientnumbers: to,
        defdate: '', isblink: 'false', isflash: 'false',
      });
      return `${this.cfg.base}?${q.toString()}`;
    };
    return { smsUrl: make(this.cfg.pass), safeUrl: make('***') };
  }
}
// OTP service: code = crypto.randomInt(0, 1e6) padded; store hash+expiry+attempts+lastSentAt;
// reject if now - lastSentAt < 60s; response: { sent: true, sms_url, safe_url, expires_in }.
// `env(name)` returns process.env[name] ?? '' (no fallback values); the constructor throws at boot in production only.
```

## Client contract (hand this section to other developers)

Request-OTP (or any SMS-sending) endpoint response:

```json
{ "sent": true, "sms_url": "https://smsbox.com/...Http_SendSMS?...", "safe_url": "https://...password=***...", "expires_in": 300 }
```

Client must:
1. HTTP **GET** `sms_url` exactly as returned (do not re-encode, edit, or rebuild it).
2. Fire it immediately, with a timeout (about 10 s), once per response; do not retry-loop.
3. Never log, persist, or display `sms_url`; log `safe_url` only.
4. Treat HTTP 200 as "sent to gateway", not "delivered"; inspect the body if the app needs success state.
5. Never see or compute the OTP; the user types it and the app sends it to the verify endpoint.

Dashboard (browser; SMSBox is assumed to send no CORS headers, unverified here, so use no-cors and ignore the opaque response):

```ts
const ctrl = new AbortController();
const t = setTimeout(() => ctrl.abort(), 10000);
try {
  await fetch(result.sms_url, { mode: 'no-cors', credentials: 'omit', signal: ctrl.signal });
} finally { clearTimeout(t); }
```

Flutter/Dart (mobile is not subject to CORS, so the body is readable):

```dart
final res = await http
    .get(Uri.parse(smsUrl))   // smsUrl from the API; never build or log it here
    .timeout(const Duration(seconds: 10));
if (res.statusCode != 200) { /* report failure */ }
// body check: SMSBox returns 200 even on errors; map its status text to an error state
```

The user's phone must be able to reach SMSBox from a Kuwait IP for the send to succeed;
the client device, not the server, is what SMSBox sees.

## Verify delivery (QA checklist)

- Live send to a test number; confirm receipt, not only HTTP 200.
- Capture the response body for a deliberately wrong password and wrong sender; record the
  failure strings so clients can map them.
- Confirm the sender shows as expected and long messages split/limit as expected.
- Confirm no full URL appears in server logs, crash reports, or analytics.
- Test from a non-Kuwait network to confirm the failure is surfaced to the user, not swallowed.
- If Arabic is required: live-test Arabic text before sign-off (rule 9).

## When applying this skill

1. Find the project's existing SMS/OTP module first; extend it rather than adding a second one.
2. Check each rule above against the code and report violations before writing new code.
3. Never read `.env` files or credential vaults to "fill in" values; use env names and placeholders.
