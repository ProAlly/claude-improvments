# Backend code (NestJS + Mongoose sketch; adapt to other stacks)

## File layout
```
src/modules/notifications/
  push-sender.service.ts       # firebase-admin wrapper, chunking, error classification
  device-tokens.service.ts     # register (exclusive) / unregister / prune / clearAll
  device-tokens.controller.ts  # POST/DELETE /notifications/devices
  dto/device-token.dto.ts      # { token: string (1..4096), platform: 'ios'|'android'|'web' }
  notification-dispatcher.ts   # prefs check + language buckets + enqueue
.env.example                   # FIREBASE_PROJECT_ID= FIREBASE_CLIENT_EMAIL= FIREBASE_PRIVATE_KEY=   (names only)
.gitignore                     # *firebase*credentials*, *service-account*.json
```

## Schema (per actor collection, or a separate DeviceToken collection)
NEW recommendation beyond Sanad: Sanad stores `deviceTokens: string[]` (plain strings) and its register DTO has no `platform`. The `{token, platform, lastSeen}` objects below (and the `FIREBASE_*` env names; Sanad uses `FCM_PROJECT_ID`/`FCM_CLIENT_EMAIL`/`FCM_PRIVATE_KEY`) are the VGA standard for new work/migrations.
```ts
@Prop({ type: [{ token: String, platform: { type: String, enum: ['ios','android','web'] }, lastSeen: Date, _id: false }], default: [] })
devices: { token: string; platform: 'ios'|'android'|'web'; lastSeen: Date }[];
// Index: { 'devices.token': 1 }  (needed for exclusive claim + prune)
```
Alternative at scale: separate `device_tokens` collection with UNIQUE index on `token` (exclusive claim = upsert `{token}` -> `{actorId, actorRole, platform, lastSeen}`), cap per actor by deleting oldest beyond 10. Simpler and race-free; prefer when many actor types exist.

## Controller
```ts
@Post('devices')  register(@CurrentActor() a, @Body() dto: DeviceTokenDto)   { return this.tokens.register(a, dto.token, dto.platform); }
@Delete('devices') unregister(@CurrentActor() a, @Body() dto: UnregisterDto) { return this.tokens.unregister(a, dto.token); } // token in BODY
```
Rate-limit both; idempotent; unregister never errors if absent.

## DeviceTokensService (exclusive claim)
```ts
async register(actor, token: string, platform) {
  await this.releaseFromOthers(token, actor);       // $pull token from every other holder in every collection
  // Single atomic pipeline update: dedupe, append newest, cap at MAX (=10)
  await model.updateOne({ _id: actor.id }, [{ $set: { devices: { $slice: [
    { $concatArrays: [
      { $filter: { input: { $ifNull: ['$devices', []] }, cond: { $ne: ['$$this.token', token] } } },
      [{ token, platform, lastSeen: '$$NOW' }],
    ] }, -MAX_DEVICE_TOKENS_PER_ACTOR ] } } }], { updatePipeline: true });
}
async unregister(actor, token) { await model.updateOne({ _id: actor.id }, { $pull: { devices: { token } } }); }
async prune(tokens: string[]) { /* updateMany across ALL holders: $pull devices {token: {$in: tokens}} */ }
// keep ONE `holders` list so a new role cannot be forgotten in one sweep.
```
Also `clearAll(actor)` on suspension/force-logout/account deletion, logout-all and suspected token compromise (see skill `aks-firebase-auth-tokens`, revocation D4/D5). Single-device logout removes that one token server-side inside the auth logout call.

## PushSenderService
Placeholders (not defined here): `this.logger` (Nest `Logger`), `this.warnOnce()` (log one "FCM not configured" warning, guarded by a boolean flag). Sanad takes config via `ConfigService` (`fcm.projectId` etc., fed by `FCM_PROJECT_ID`/`FCM_CLIENT_EMAIL`/`FCM_PRIVATE_KEY`); the `process.env.FIREBASE_*` below is the standard naming for new projects (see Naming note).
```ts
const DEAD = new Set(['messaging/registration-token-not-registered', 'messaging/invalid-registration-token']);
const MESSAGE_LEVEL = new Set(['messaging/invalid-argument', 'messaging/invalid-payload', 'messaging/payload-size-limit-exceeded']);

@Injectable()
export class PushSenderService implements OnModuleDestroy {
  private app: App | null | undefined;

  async sendBulk(tokens: string[], n: { title: string; body: string; data?: Record<string, unknown>; collapseKey?: string; link?: string; ttlSeconds?: number; urgent?: boolean }) {
    const result = { sent: 0, failed: 0, invalidTokens: [] as string[], messageError: undefined as string | undefined };
    const app = this.getApp();
    if (!app || !tokens.length) { if (!app) this.warnOnce(); return result; }   // honest zero, never fake success
    const data = Object.fromEntries(Object.entries(n.data ?? {}).map(([k, v]) => [k, String(v)])); // FCM data = strings only
    const messaging = getMessaging(app);
    for (let i = 0; i < tokens.length; i += 500) {
      const chunk = tokens.slice(i, i + 500);
      try {
        const res = await messaging.sendEachForMulticast({
          tokens: chunk,
          notification: { title: n.title, body: n.body },
          data,
          webpush: {   // TTL/Urgency/fcmOptions.link = NEW recommendation beyond Sanad (Sanad sends only Topic)
            headers: { TTL: String(n.ttlSeconds ?? 86400), Urgency: n.urgent ? 'high' : 'normal', ...(n.collapseKey ? { Topic: n.collapseKey } : {}) },
            ...(n.link ? { fcmOptions: { link: n.link } } : {}),     // must be https
          },
          // Add android/apns ONLY when collapseKey is set (as Sanad does): an empty
          // 'apns-collapse-id' or undefined tag can trigger message-level invalid-argument for ALL recipients.
          ...(n.collapseKey
            ? { android: { notification: { tag: n.collapseKey } }, apns: { headers: { 'apns-collapse-id': n.collapseKey } } }
            : {}),
        });
        result.sent += res.successCount; result.failed += res.failureCount;
        res.responses.forEach((r, idx) => {
          if (r.success) return;
          const code = r.error?.code;
          this.logger.warn(`FCM token error ${code} (…${chunk[idx].slice(-6)})`);   // per-token log, never full token
          if (code && DEAD.has(code)) result.invalidTokens.push(chunk[idx]);        // prune ONLY these
          else if (code && MESSAGE_LEVEL.has(code)) result.messageError ??= `${code}: ${r.error?.message}`; // NOT pruned
        });
      } catch (e) { this.logger.error(`FCM chunk failed: ${(e as Error).message}`); result.failed += chunk.length; } // transient; prune nothing
    }
    return result;
  }

  private getApp() {
    if (this.app !== undefined) return this.app;
    const projectId = process.env.FIREBASE_PROJECT_ID, clientEmail = process.env.FIREBASE_CLIENT_EMAIL;
    const privateKey = process.env.FIREBASE_PRIVATE_KEY?.replace(/\\n/g, '\n');
    this.app = projectId && clientEmail && privateKey
      ? initializeApp({ credential: cert({ projectId, clientEmail, privateKey }) }, 'push-sender')   // NAMED app
      : null;
    return this.app;
  }
  onModuleDestroy() { if (this.app) void deleteApp(this.app); }
}
```
JSON alternative: `FIREBASE_SERVICE_ACCOUNT_JSON` env (or secret manager) -> `cert(JSON.parse(...))`. Never read a committed file.

## Dispatcher (preferences, language, queue)
```ts
async notify(userIds, payload: { type, entityId, url, i18n: { ar: {title, body}, en: {title, body} } }) {
  const recipients = await this.prefs.filterAllowed(userIds, payload.type);   // respect opt-outs BEFORE send
  const tokensByLang = await this.tokens.groupByLang(recipients);             // { ar: [...], en: [...] }
  for (const lang of ['ar', 'en']) {
    await this.queue.add('push', { lang, tokens: tokensByLang[lang], title: payload.i18n[lang].title, body: payload.i18n[lang].body,
      data: { type: payload.type, entityId: payload.entityId, url: payload.url, lang }, collapseKey: `${payload.type}-${payload.entityId}` });
  }
}
// queue processor: res = await sender.sendBulk(...); await tokens.prune(res.invalidTokens);
```
Never `await` sends inside the HTTP request path or per-recipient loops.

## Topics (optional)
`messaging.subscribeToTopic(tokens, 'announcements-ar')` / `messaging.send({ topic, ... })` for broad broadcasts; unsubscribe on token removal. Keep token arrays as the source of truth for targeted sends.
