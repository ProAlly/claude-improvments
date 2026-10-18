---
name: aks-nodemailer-smtp
description: Send email over SMTP with Nodemailer in NestJS/Node backends, using the VGA-project conventions. Use when the user mentions Nodemailer, SMTP, "send email", OTP email, verification code email, forgot/reset password email, welcome email, email templates, EmailService, SMTP_HOST/SMTP_PORT/SMTP_FROM env vars, support/contact-form mail, Arabic/English (RTL) emails, email attachments, or debugging "email not sending", "Invalid login", "ECONNECTION", or unhandled rejections from sendMail. Encodes the hardened standard (derive secure from port, pooling, always await, escape HTML, no plaintext passwords, verify at startup).
user-invocable: true
---

# aks-nodemailer-smtp — Nodemailer over SMTP, VGA standard

Nodemailer only (^9; 10.x exists, check release notes before upgrading). Applies to Node/NestJS backends. Based on the Al Mudarib, Outlet and Caffeine
backends, with their known defects fixed. Never put real hosts or credentials in code, docs or chat.

## Standard (non-negotiable rules)

1. **Transport**: `nodemailer@^9`. Config from env only. Constructor throws if `SMTP_HOST`/`SMTP_PORT` missing.
2. **`secure` derives from the port**, not a separate flag: 465 -> `secure: true`; 587 (and 25/2525) ->
   `secure: false` + `requireTLS: true`. Reject any other combination loudly. Do not trust `SMTP_SECURE`
   (a wrong flag causes silent hangs/"wrong version number").
3. **Pool**: `pool: true, maxConnections: 5, maxMessages: 100` (no VGA project pools today).
4. **TLS**: keep `tls.rejectUnauthorized: true`. Never disable it (FitFinds did). For a self-signed dev
   server use Mailpit/MailHog on a plain local port instead.
5. **Always await or explicitly catch every send.** No fire-and-forget (Outlet has 5 unawaited calls ->
   unhandled rejections). Never swallow the error and report success (FitFinds). If a send is
   intentionally non-blocking, use `void this.email.send(...).catch(err => logger.error(...))`.
6. **From**: `options.from || SMTP_FROM || SMTP_USER`. Support/contact mail sets `replyTo = sender`
   and sends *from* the system address (never spoof the user's address as `from`).
7. **Escape every user-supplied value** interpolated into HTML (names, messages, store names). Only Outlet
   (`templates/notification.ts`) escapes; Al Mudarib (`welcome.ts`, `password-reset-confirmation.ts`
   interpolate `${fullName}` raw) and Caffeine (support email) do not. Use the `escapeHtml` helper
   below; reject CR/LF in subject, to, cc, bcc, from, replyTo.
8. **Never email a generated plaintext password** (Outlet does). Send a set-password link or OTP.
9. **Never log OTPs/links/tokens in production.** Dev fallback only: log to console when
   `NODE_ENV !== 'production'` AND `EMAIL_DEV_FALLBACK=true` (staging must not opt in implicitly), and still return a clear flag (`{ delivered: false, devFallback: true }`)
   — never a silent `true` (Amirni returns true).
10. **Templates**: TS functions returning HTML, wrapped by one shared `template.ts` (+ `theme.ts`).
    Load nothing from relative filesystem paths (FitFinds breaks when CWD changes); if files are
    unavoidable use `path.join(__dirname, ...)` and ship them in the build assets.
11. **No leftover branding**: subjects/titles come from a single `APP_NAME` constant (Al Mudarib
    subjects still say "Nest Auth").
12. **Attachments**: never pass user-supplied URLs as `path` (Nodemailer fetches them server-side -> SSRF;
    Caffeine support attachments do this). Accept uploaded buffers, or allow-list hosts/schemes
    (https only, no private IPs), and cap size/count/mime types.
13. **Localization**: subject and body in AR/EN based on user locale; Arabic wraps content in
    `<div dir="rtl" lang="ar" style="text-align:right">`. Always provide a `text` alternative.
14. **Verify at startup**: `transporter.verify()` in `onModuleInit`. Fatal in production, warn-only in dev.
15. **Errors**: wrap into domain errors (Outlet style): user/pass not configured -> `SMTP_MISSING_CREDENTIALS`;
    credentials present but rejected (EAUTH/535), config or connection failure -> `SMTP_CONFIG_ERROR` (HttpException 5xx, no raw SMTP text to clients).

## Env (placeholders only)

```
SMTP_HOST=smtp.example.com
SMTP_PORT=587            # 465 => implicit TLS, 587 => STARTTLS
SMTP_USER=<smtp-username>
SMTP_PASS=<smtp-password-or-app-password>
SMTP_FROM="App Name <no-reply@example.com>"
EMAIL_ADMIN=admin@example.com        # internal notices
SUPPORT_EMAIL=support@example.com    # support inbox
EMAIL_DEV_FALLBACK=false             # true only on local dev: swallow send errors (never in staging/prod)
# SMTP_SECURE is intentionally ignored; secure is derived from SMTP_PORT.
```

Dev (Mailpit): `SMTP_HOST=localhost SMTP_PORT=1025`, no user/pass (see Port policy note below).

## NestJS EmailService sketch

```ts
import { Injectable, Logger, OnModuleInit, HttpException, HttpStatus } from '@nestjs/common';
import * as nodemailer from 'nodemailer';
import type { Attachment } from 'nodemailer/lib/mailer';

export interface IEmailOptions {
  to: string | string[];
  subject: string;
  html: string;
  text?: string;
  from?: string;
  cc?: string | string[];
  bcc?: string | string[];
  replyTo?: string;
  attachments?: Attachment[]; // buffers/validated only; never raw user URLs
}
export interface SendResult { delivered: boolean; devFallback?: boolean; messageId?: string }

const PROD_PORTS = new Set([465, 587, 25, 2525]);
const DEV_PLAIN_PORTS = new Set([1025, 1026]); // Mailpit/MailHog local only
const hasCRLF = (v?: string | string[]) => [v].flat().some(x => x && /[\r\n]/.test(x));

@Injectable()
export class EmailService implements OnModuleInit {
  private readonly logger = new Logger(EmailService.name);
  private readonly isProd = process.env.NODE_ENV === 'production';
  private readonly transporter: nodemailer.Transporter;

  constructor() {
    const { SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS } = process.env;
    if (!SMTP_HOST || !SMTP_PORT) {
      throw new Error('SMTP_HOST and SMTP_PORT must be set');
    }
    const port = Number(SMTP_PORT);
    if (!Number.isInteger(port)) throw new Error('SMTP_PORT must be an integer');
    if (!PROD_PORTS.has(port) && !(!this.isProd && DEV_PLAIN_PORTS.has(port))) {
      throw new Error(`SMTP_PORT ${port} is not allowed (use 465/587/25/2525; 1025/1026 only outside production)`);
    }
    if (this.isProd && !SMTP_USER) {
      throw new HttpException({ code: 'SMTP_MISSING_CREDENTIALS' }, HttpStatus.INTERNAL_SERVER_ERROR);
    }

    const secure = port === 465;
    const plainDev = !this.isProd && DEV_PLAIN_PORTS.has(port);

    this.transporter = nodemailer.createTransport({
      host: SMTP_HOST,
      port,
      secure,
      requireTLS: !secure && !plainDev,
      auth: SMTP_USER ? { user: SMTP_USER, pass: SMTP_PASS } : undefined,
      pool: true,
      maxConnections: 5,
      maxMessages: 100,
      connectionTimeout: 10_000,
      greetingTimeout: 10_000,
      socketTimeout: 20_000,
      tls: { rejectUnauthorized: true },
    });
  }

  async onModuleInit() {
    try {
      await this.transporter.verify();
      this.logger.log('SMTP transport verified');
    } catch (err) {
      if (this.isProd) throw this.wrap(err);
      this.logger.warn(`SMTP verify failed (non-fatal in dev): ${(err as Error).message}`);
    }
  }

  /** Always await this, or `.catch` it explicitly. */
  async send(o: IEmailOptions): Promise<SendResult> {
    if ([o.to, o.cc, o.bcc, o.subject, o.from, o.replyTo].some(hasCRLF)) {
      throw new Error('Invalid header value');
    }
    try {
      const info = await this.transporter.sendMail({
        from: o.from || process.env.SMTP_FROM || process.env.SMTP_USER,
        to: o.to, cc: o.cc, bcc: o.bcc, replyTo: o.replyTo,
        subject: o.subject, html: o.html,
        text: o.text ?? o.html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim(),
        attachments: o.attachments,
      });
      return { delivered: true, messageId: info.messageId };
    } catch (err) {
      if (!this.isProd && process.env.EMAIL_DEV_FALLBACK === 'true') {
        // Local dev only (explicit opt-in, not staging): surface content locally, but do NOT pretend it was delivered.
        this.logger.warn(`DEV FALLBACK (not delivered) to=${String(o.to)} subject=${o.subject}: ${(err as Error).message}`);
        return { delivered: false, devFallback: true };
      }
      this.logger.error(`sendMail failed: ${(err as Error).message}`);
      throw this.wrap(err);
    }
  }

  /** Support/contact form: system sender, replyTo = the visitor. */
  sendSupport(senderEmail: string, subject: string, html: string, text?: string) {
    return this.send({
      to: process.env.SUPPORT_EMAIL!, replyTo: senderEmail, subject, html, text,
    });
  }

  private wrap(err: unknown) {
    const e = err as { code?: string; responseCode?: number };
    // Credentials present but rejected (EAUTH/535) is a config error; SMTP_MISSING_CREDENTIALS
    // is only thrown in the constructor when user/pass are not configured.
    return new HttpException(
      { code: 'SMTP_CONFIG_ERROR', message: 'Email delivery failed' },
      HttpStatus.SERVICE_UNAVAILABLE,
    );
  }
}
```

Callers: `await this.email.send(...)` inside the flow, and decide explicitly what to do on
`delivered:false` (e.g. OTP flows return an error to the user; do not say "code sent").

## Template example (shared wrapper + OTP)

```ts
// NOTE: templates/template.ts, theme.ts and otp.template.ts below are PROJECT paths to create
// in your own codebase, not files bundled with this skill.
// templates/template.ts  (single shared layout; colors/fonts from theme.ts)
import { theme } from './theme';
export const APP_NAME = process.env.APP_NAME ?? 'App';
export const escapeHtml = (v: unknown) =>
  String(v ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));

export type Lang = 'en' | 'ar';
export const wrap = (title: string, body: string, lang: Lang = 'en') => `<!doctype html>
<html lang="${lang}" dir="${lang === 'ar' ? 'rtl' : 'ltr'}"><body style="margin:0;background:${theme.bg};font-family:${theme.font}">
<table role="presentation" width="100%"><tr><td align="center" style="padding:24px">
<div style="max-width:560px;background:#fff;border-radius:8px;padding:24px;text-align:${lang === 'ar' ? 'right' : 'left'}">
<h2 style="color:${theme.primary};margin-top:0">${escapeHtml(title)}</h2>${body}
<hr><small style="color:#888">&copy; ${escapeHtml(APP_NAME)}</small>
</div></td></tr></table></body></html>`;

// templates/otp.template.ts  (PROJECT path, not bundled with this skill)
import { wrap, escapeHtml, APP_NAME, Lang } from './template';
const T = {
  en: { subject: `Your ${APP_NAME} verification code`, hi: 'Hello', msg: 'Your verification code is', exp: 'It expires in' , min: 'minutes. If you did not request it, ignore this email.' },
  ar: { subject: `رمز التحقق الخاص بك في ${APP_NAME}`, hi: 'مرحباً', msg: 'رمز التحقق الخاص بك هو', exp: 'ينتهي خلال', min: 'دقائق. إذا لم تطلبه، تجاهل هذه الرسالة.' },
};
export function otpEmail(name: string, code: string, minutes: number, lang: Lang = 'en') {
  const t = T[lang];
  const html = wrap(t.subject, `
    <p>${t.hi} ${escapeHtml(name)},</p><p>${t.msg}:</p>
    <p style="font-size:28px;letter-spacing:6px;font-weight:bold">${escapeHtml(code)}</p>
    <p>${t.exp} ${minutes} ${t.min}</p>`, lang);
  return { subject: t.subject, html, text: `${t.msg}: ${code}` };
}
// usage: await email.send({ to, ...otpEmail(user.name, code, 10, user.lang) });
```

Standard template set: registration OTP, resend OTP, forgot password (OTP/link), welcome,
password-reset confirmation, store/vendor/staff notices, support/contact.

## Port policy note

Only 465 (secure) and 587/25/2525 (requireTLS) are valid in production; the constructor throws on any
other port. The plain Mailpit/MailHog ports (1025/1026) are permitted only when `NODE_ENV !== 'production'`.

## Testing

- **Mailpit** (preferred): `docker run -p 1025:1025 -p 8025:8025 axllent/mailpit`; UI at http://localhost:8025.
  MailHog is equivalent. **Ethereal** (`nodemailer.createTestAccount()`) for throwaway hosted inboxes;
  open `nodemailer.getTestMessageUrl(info)`.
- Unit test templates as pure functions: assert escaping (`<script>` in name is neutralised),
  AR gets `dir="rtl"`, no `undefined` in output.
- Unit test EmailService with a mocked transporter (`nodemailer.createTransport` jest mock): assert
  secure/requireTLS per port, `from` fallback chain, replyTo for support, CRLF rejection, error wrapping,
  and `delivered:false` in dev fallback.
- Startup check: wrong password in dev must warn, in prod must fail boot.

## When SMTP/Nodemailer is NOT the right tool

This skill is Nodemailer-only. Existing exceptions in the codebase, acceptable when:
- **CareLink** — Gmail with XOAUTH2 via Python `smtplib`: acceptable for a Python backend using a
  Google Workspace/Gmail account where app passwords are disallowed. In Node, use Nodemailer's
  `auth: { type: 'OAuth2', ... }` instead.
- **Amirni** — Brevo REST API: acceptable when the host blocks outbound SMTP ports or when you need
  provider features (templates, webhooks, tracking, high volume). Still apply rules 5, 7-9 above.

## Checklist before finishing

- [ ] env names only, placeholders in `.env.example`, nothing real committed
- [ ] every `send` awaited/caught; failures surfaced to the caller
- [ ] all interpolated values escaped; subject has no CR/LF
- [ ] no plaintext password or OTP in prod logs/emails
- [ ] AR/EN + RTL; no stale brand names
- [ ] tested against Mailpit
