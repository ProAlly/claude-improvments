---
name: aks-dreams-sms
description: Integrate the Dreams SMS gateway (dreams.sa) for OTP and notification texts the way the Buzz backend does - server-side GET to sendSmsOtp, reply-code parsing, error mapping, circuit breaker, E.164 phone handling, IP allow-listing (-124). Use when the user mentions Dreams SMS, dreams.sa, sendSmsOtp, "OTP via Dreams", Dreams reply codes (-110, -113, -116, -124), SMS_PROVIDER dreams, DREAMS_SMS_* env vars, or swapping/adding Dreams as an SMS provider in a NestJS/Node backend.
user-invocable: true
---

# Dreams SMS (dreams.sa) integration - the Buzz pattern

SMSBox projects use `aks-smsbox-built-url` instead (backend builds a URL the client calls); if the provider is unknown, ask.

Reference implementation: `buzz-backend/src/modules/auth/sms.service.ts`
(adapter, `DREAMS_REPLY_CODES`, `parseDreamsReply`), config in
`src/config/configuration.ts`, admin diagnostic in
`src/system/system-sms.controller.ts`. Re-read these when exact behaviour
matters; do not rely on this summary for code details.

## Decision note: server-side call vs built URL

Dreams is called **server-side** by our backend with `fetch` and a 10s timeout.
This differs from SMSBox, where the pattern is a built URL (see skill
`aks-smsbox-built-url`). Do not assume a built-URL variant for Dreams. If the
user may want one, **ask first**. Note a built URL would put `secret_key` in
something that can be logged or shared.

## Contract (as used in Buzz)

- Base: `https://dreams.sa/index.php/v2/api` (override via `DREAMS_SMS_BASE_URL`, strip trailing `/`).
- Request: `GET {base}/sendSmsOtp` with query params `user`, `secret_key`, `sender`, `to`, `message`.
- `to` = E.164 with the leading `+` stripped. Normalize input first (Buzz uses `libphonenumber-js` `toE164`).
- HTTP is **200 for every outcome**. Judge the body, not the status.
- Success body: `1`, `Success`, `Result:...` (e.g. `Result:SMS_ID:mobile`), or a positive integer id.
- Negative integer = reply code: -100, -110..-119, -122..-124 (table `DREAMS_REPLY_CODES`).
- Empty or unrecognised body = failure, never "sent" (a wording change must not silently swallow OTPs).
- Not in the Buzz code, so do not invent: balance check, delivery reports, bulk/scheduled sending. Mark as "check Dreams portal docs".
- Arabic/Unicode message handling is unverified here: check Dreams docs before sending Arabic OTP text.

## Reply-code classes and HTTP mapping

| Class | Codes | Client response |
|---|---|---|
| number problem | -117, -122 | 400 `SMS_NUMBER_REJECTED` (user can fix) |
| account: auth | -110, -111, -112 | 503 `SMS_PROVIDER_AUTH_FAILED` |
| account: balance | -113 | 503 `SMS_PROVIDER_NO_BALANCE` |
| account: sender | -115, -116, -123 | 503 `SMS_PROVIDER_SENDER_INVALID` |
| account: IP | -124 | 503 `SMS_PROVIDER_IP_NOT_ALLOWED` (allow-list server IP in Dreams portal) |
| other account/service | -100, -114, -118, -119, unknown | 503 `SMS_SEND_FAILED` |
| breaker open | n/a | 503 `SMS_PROVIDER_UNAVAILABLE` |

Provider details (code, meaning, raw reply) go in the response only when not
production; always log them server-side (truncate reply, never log the URL).

## Rules to encode

1. **Secret is in the query string.** Never log the URL. Catch fetch errors and rethrow a sanitized one (error name only).
2. **Circuit breaker** (key `dreams:sms`) wraps transport/HTTP failures only (network, timeout, non-2xx). Gateway rejections are returned out of the breaker and thrown after, so one bad number never opens it for everyone.
3. **Provider selector** `SMS_PROVIDER` = `dreams | twilio | log`. If unset, first provider with full credentials; incomplete creds for the requested one fall back to `log` with an error log. `log` mode only logs, never sends: make sure it cannot be active silently in production.
4. **Env names**: `DREAMS_SMS_USER`, `DREAMS_SMS_SECRET_KEY`, `DREAMS_SMS_SENDER`, `DREAMS_SMS_BASE_URL`; Twilio fallback `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`. Put names only in `.env.example`; never real values or sender names in code, docs, or chat.
5. **Every send is billed.** Rate-limit OTP requests per phone and per IP, enforce a resend cooldown, cap attempts.
6. **OTP hashed at rest** (Buzz: SHA-256 + constant-time compare), short TTL, single use.
7. **Never ship hardcoded OTP bypasses.** Buzz has a "temp dev bypass" (`otp.service.ts` ~L150) and a reviewer-phone fixed OTP (`configuration.ts` ~L28). The Buzz flags to look for and flag in any review are `TEMP_OTP_ENABLED`, `TEMP_OTP_APP`, `TEMP_OTP_MERCHANT` (`configuration.ts` ~L13-24, default `false`; fixed 4-6 digit codes accepted for any phone when enabled) and `EXPOSE_OTP_IN_RESPONSE` (~L11, returns the OTP in the API response). Treat these as debt, not a pattern to copy. If an app-store reviewer flow is unavoidable: gate on `NODE_ENV` plus an explicit flag, single phone only, **fail closed** (off when unset, error if enabled in production without the flag), and log its use. Flag existing bypasses to the user.
8. **diagnose()** (Buzz route: `POST /system/sms/test`, guarded with `@Roles(SYSTEM_ADMIN)` in `system-sms.controller.ts`; guidance: keep any diagnose/billed-test route admin-only) does a **real billed send**, bypasses the breaker, and calls `api.ipify.org` to report the server's public IP, useful for -124 allow-listing. Restrict it to admins and rate-limit it.

## NestJS adapter sketch (placeholders)

```ts
@Injectable()
export class SmsService {
  private readonly logger = new Logger(SmsService.name);
  constructor(
    @Inject(APP_CONFIG) private readonly config: AppConfig, // dreams: {user, secretKey, sender, baseUrl}
    private readonly breaker: CircuitBreakerService,
  ) {}

  async send(to: string, body: string): Promise<string> {
    try {
      const reply = await this.breaker.exec('dreams:sms', async () => {
        const { status, raw } = await this.call(to, body);
        if (status < 200 || status >= 300) throw new Error(`HTTP ${status}`);
        return { ...parseDreamsReply(raw), raw };
      });
      if (reply.rejectedCode) throw new SmsRejectedError(reply.rejectedCode, reply.raw);
      return reply.reference;
    } catch (err) {
      // CircuitOpenError -> 503 SMS_PROVIDER_UNAVAILABLE
      // SmsRejectedError -> lookup DREAMS_REPLY_CODES -> 400 or 503 per table above
      throw err;
    }
  }

  private async call(to: string, message: string) {
    const { user, secretKey, sender, baseUrl } = this.config.dreams;
    const q = new URLSearchParams({ user, secret_key: secretKey, sender, to: to.replace(/^\+/, ''), message });
    try {
      const res = await fetch(`${baseUrl}/sendSmsOtp?${q}`, { signal: AbortSignal.timeout(10_000) });
      return { status: res.status, raw: await res.text() };
    } catch (e) {
      throw new Error(`Dreams SMS request failed (${e instanceof Error ? e.name : 'unknown'})`); // no URL
    }
  }
}

export function parseDreamsReply(raw: string) {
  const t = raw.trim().replace(/^"(.*)"$/, '$1').trim();
  if (/^-\d+$/.test(t)) return { reference: '', rejectedCode: t };
  if (/^result\s*:/i.test(t)) return { reference: t.replace(/^result\s*:\s*/i, '') };
  if (/^\d+$/.test(t) && Number(t) > 0) return { reference: t };
  if (/^success$/i.test(t)) return { reference: 'dreams-accepted' };
  return { reference: '', rejectedCode: t ? 'UNRECOGNISED_REPLY' : 'EMPTY_RESPONSE' };
}
```

## Checklist when integrating

- Env names added to `.env.example` and validated at startup (Buzz: zod); read via the project's env helper.
- Phone normalized to E.164 before send; `+` stripped only at the HTTP call.
- Reply parser unit-tested for every success form and several negative codes.
- Rate limit + cooldown + attempt cap on the OTP request endpoint.
- No hardcoded OTPs; any test/reviewer path gated and fail-closed.
- Server public IP allow-listed in the Dreams portal before first live send.
