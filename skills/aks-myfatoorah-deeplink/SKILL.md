---
name: aks-myfatoorah-deeplink
description: Use whenever integrating or modifying MyFatoorah payments in any project (payment gateway, checkout, KNET, SendPayment, ExecutePayment, InitiateSession, GetPaymentStatus, MakeRefund, CallBackUrl, ErrorUrl, payment callback, return-to-app after payment). Always return the payer to the mobile app via DEEPLINKING (Sanad is the deeplink reference; Caffeine is only the landing-page fallback), never a bare web page. Asks up front whether a backend callback endpoint is wanted, then builds the callback to re-verify status server-side and 302 to the app deep link. Triggers - "MyFatoorah", "payment gateway", "deep link", "deeplink", "checkout", "KNET", "payment callback", "payment return URL", "pay and return to app".
user-invocable: true
---

# MyFatoorah + Deeplink return

Rule: any MyFatoorah integration returns the payer to the app through a
deep link. Do not invent a different return mechanism.

## Step 0 - Ask first (before building anything)

Ask the user: **"Do you want a backend callback endpoint?"** Plan: no callback
URLs or endpoints unless the user explicitly asks. Require an explicit answer
before building anything; there is no default.

- **Yes.** MyFatoorah `CallBackUrl` / `ErrorUrl` point at one thin
  backend GET endpoint. It never trusts the query string, re-derives status
  server-side via `GetPaymentStatus` (key `PaymentId`, fallback `InvoiceId`),
  then 302-redirects to the app deep link.
- **No.** No backend callback endpoint. Set `CallBackUrl`/`ErrorUrl` to an
  https App Link / Universal Link that opens the app, or to a static https
  landing page that opens `<scheme>://payment/result`. The app then polls
  payment status through the backend. Still no query string on those URLs
  (see Pitfalls).

Do not create callback URLs or endpoints unless the user said yes.

## Deeplink shape

Primary (Sanad pattern):

`<scheme>://payment/result?status=paid|failed|pending|refunded|unknown&reference=<invoiceId>&orderId=<id>`

`status` is always present. Unknown/unverifiable outcomes map to `unknown`
or `pending`, never `paid`.

Legacy webview fallback (Caffeine), avoid unless the app cannot register a
scheme: Caffeine uses no deep link. It serves an HTML landing page
`/payment/success|error?status=&amount=` that sets `window.paymentResult`
and calls `window.close()` so the webview can detect completion. Sanitize
`amount` to digits only.

## Reference implementations (read for detail, do not copy blindly)

- Sanad: `backend/src/modules/payments/payment-gateway.service.ts`
  (SendPayment with `NotificationOption: LNK` returns `InvoiceURL`;
  GetPaymentStatus; MakeRefund), `payment-callback.controller.ts` (routes
  `payments/callback/success|error`, settle checkout return then 302),
  `payment-resync.runner.ts` (poller settles abandoned payers). Webhook was
  deliberately removed.
- Caffeine: `backend/src/modules/common/services/myfatoorah.service.ts`
  (ExecutePayment hosted; v3 sessions for embedded card),
  `wallet.controller.ts` / `order.controller.ts` callbacks,
  `payment-landing.helper.ts` (only builds the landing URL), reconciliation
  cron. The landing page itself (`window.paymentResult`, `window.close()`)
  lives in `caffeine-app/backend/src/modules/payment/payment.controller.ts`.

## Env vars (names only)

- `MYFATOORAH_API_KEY`
- `MYFATOORAH_API_BASE_URL` (apitest host default for test; live host per country)
- `PAYMENT_CALLBACK_BASE_URL` (public HTTPS base)
- `MOBILE_DEEP_LINK_SCHEME` (app scheme; new convention of this skill, not
  from Sanad, which hardcodes `sanad://payment/result` in
  `payment-gateway.service.ts`)

Dev stub when no API key is set: simulate InvoiceURL/status locally, never
call the gateway.

## Pitfalls

- Callback base falling back to localhost: the gateway cannot reach it.
  Fail fast at startup if `PAYMENT_CALLBACK_BASE_URL` is unset/localhost in non-dev.
- Never accept a client-supplied `callbackUrl` (Amirni does; reject it).
- The app must register the scheme: Android intent-filter, iOS
  `CFBundleURLTypes`. (Sanad's app side is not done yet; its assetlinks
  package looks like a template placeholder - check before relying on App Links.)
- MyFatoorah appends `?paymentId=` to `CallBackUrl`/`ErrorUrl` without checking
  for an existing query string (Sanad `payment-gateway.service.ts`), so a URL
  like `...callback?via=success` becomes unparseable. Never put a query string
  on them; put markers in the path (e.g. `/callback/success`).
- Same value for `CallBackUrl` and `ErrorUrl` is fine only if the endpoint
  distinguishes outcome by re-querying status.
- Settlement must be idempotent: callback and resync poller can both fire.
- Open `InvoiceURL` in an in-app webview or external browser.
- Check status server-side only; query-string status is untrusted.
- Webhooks are out of scope unless the user asks. If asked, HMAC verification
  must fail CLOSED when the secret is unset (Al Mudarib fails open - do not copy).

## Checklist

- [ ] Asked about callback endpoint; recorded the answer
- [ ] Env vars read from config; startup fails fast on bad callback base
- [ ] Dev stub when no key
- [ ] Callback re-queries GetPaymentStatus (PaymentId, fallback InvoiceId)
- [ ] Settlement idempotent; resync/reconcile job for abandoned payers
- [ ] Redirect always includes `status`
- [ ] App registers scheme and handles `payment/result`
- [ ] No client-supplied callback URLs; no secrets in code or logs

## Minimal sketch (NestJS-style, placeholders)

```ts
@Injectable()
export class PaymentGatewayService {
  constructor(private cfg: ConfigService, private http: HttpService) {}

  async createInvoice(o: { orderId: string; amount: number }) {
    const base = this.cfg.getOrThrow('PAYMENT_CALLBACK_BASE_URL');
    const res = await this.post('/v2/SendPayment', {
      NotificationOption: 'LNK',
      InvoiceValue: o.amount,
      CustomerReference: o.orderId,
      CallBackUrl: `${base}/payments/callback/success`,
      ErrorUrl: `${base}/payments/callback/error`,
    });
    return { invoiceUrl: res.Data.InvoiceURL, invoiceId: res.Data.InvoiceId };
  }

  async getStatus(key: string, keyType: 'PaymentId' | 'InvoiceId') {
    const res = await this.post('/v2/GetPaymentStatus', { Key: key, KeyType: keyType });
    return mapToStatus(res.Data.InvoiceStatus); // paid|failed|pending|refunded|unknown
  }
}

@Controller('payments/callback')
export class PaymentCallbackController {
  // `payments` (settlement service) and `cfg` are placeholders for your own providers.
  constructor(private payments: PaymentSettlementService, private cfg: ConfigService) {}

  @Get(':outcome(success|error)')
  async handle(@Param('outcome') outcome: string, @Query() q: any, @Res() res: Response) {
    const [key, type] = q.paymentId ? [q.paymentId, 'PaymentId'] : [q.Id, 'InvoiceId'];
    let r: { status: string; invoiceId?: string; orderId?: string };
    try {
      r = await this.payments.settleCheckoutReturn(key, type); // idempotent
    } catch {
      // never 500 the payer: the resync poller settles it later
      r = { status: outcome === 'error' ? 'failed' : 'unknown' };
    }
    const scheme = this.cfg.getOrThrow('MOBILE_DEEP_LINK_SCHEME');
    const params = new URLSearchParams({ status: r.status });
    if (r.invoiceId) params.set('reference', r.invoiceId);
    if (r.orderId) params.set('orderId', r.orderId);
    res.redirect(302, `${scheme}://payment/result?${params}`);
  }
}
```

Ports directly to FastAPI / Express: one GET route, server-side status
re-query, idempotent settle, 302 to the deep link.
