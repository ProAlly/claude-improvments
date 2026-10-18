# Client code (Vite/React; adapt to CRA/Next env prefixes)

## File layout
```
public/firebase-messaging-sw.js      # root scope, no-cache
src/lib/webPush.ts                   # enable/disable/sync/onForegroundMessage
src/lib/pushToken.ts                 # localStorage: stored token, opted-out flag
src/components/PushPrePrompt.tsx     # explains why, button = user gesture
.env.example                         # VITE_FIREBASE_API_KEY, _AUTH_DOMAIN, _PROJECT_ID, _MESSAGING_SENDER_ID, _APP_ID, _VAPID_KEY (names only)
```

## public/firebase-messaging-sw.js
```js
/* eslint-env serviceworker */
/* global importScripts, firebase */
const params = new URLSearchParams(self.location.search);

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

// Register BEFORE loading firebase-messaging-compat so we can pre-empt its click handler.
self.addEventListener('notificationclick', (event) => {
  event.stopImmediatePropagation();
  event.notification.close();
  const raw = event.notification.data || {};
  const data = (raw.FCM_MSG && raw.FCM_MSG.data) || raw;
  let target = self.location.origin + '/';
  try {
    const url = new URL(data.url || '/', self.location.origin);
    if (url.origin === self.location.origin) target = url.href; // same-origin only
  } catch (_) {}
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      const existing = list.find((c) => new URL(c.url).origin === self.location.origin && 'focus' in c);
      if (existing) {
        const f = existing.focus();
        return 'navigate' in existing
          ? Promise.resolve(f).then(() => existing.navigate(target)).catch(() => undefined)
          : f;
      }
      return self.clients.openWindow(target);
    }),
  );
});

const FALLBACK_SDK_VERSION = '<match package.json firebase version>';
const v = params.get('v') || '';
const sdkVersion = /^\d+\.\d+\.\d+$/.test(v) ? v : FALLBACK_SDK_VERSION;
importScripts(`https://www.gstatic.com/firebasejs/${sdkVersion}/firebase-app-compat.js`);
importScripts(`https://www.gstatic.com/firebasejs/${sdkVersion}/firebase-messaging-compat.js`);

const config = {
  apiKey: params.get('apiKey'),
  authDomain: params.get('authDomain'),
  projectId: params.get('projectId'),
  messagingSenderId: params.get('messagingSenderId'),
  appId: params.get('appId'),
};

if (config.projectId && config.apiKey) {
  firebase.initializeApp(config);
  const messaging = firebase.messaging();
  messaging.onBackgroundMessage((payload) => {
    if (payload.notification) return;            // browser already shows it -> no duplicate
    const data = payload.data || {};
    const options = {
      body: data.body || '',
      icon: '/notification-icon.png',
      badge: '/notification-icon.png',
      tag: data.tag || undefined,                // collapse repeats
      data,
    };
    if (data.lang === 'ar' || data.lang === 'en') {
      options.lang = data.lang;
      options.dir = data.lang === 'ar' ? 'rtl' : 'ltr';
    }
    self.registration.showNotification(data.title || '<App name>', options);
  });
}
```

## src/lib/webPush.ts (condensed from Sanad)
Placeholders (not defined here; implement in the app): `api` (your authenticated HTTP client; Sanad `apiClient`), `isEnabledHere`, and the `pushToken.ts` localStorage helpers `setStoredPushToken`, `getStoredPushToken`, `clearStoredPushToken`, `isPushOptedOut`, `setPushOptedOut`.
```ts
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};
const vapidKey = import.meta.env.VITE_FIREBASE_VAPID_KEY;

// Lazy-load the SDK (~100 kB); most sessions never touch push.
const sdk = async () => ({ ...(await import('firebase/app')), ...(await import('firebase/messaging')) });

export const isConfigured = () => Boolean(firebaseConfig.projectId && firebaseConfig.apiKey && vapidKey);

async function registerServiceWorker() {
  const { SDK_VERSION } = await sdk();
  const p = new URLSearchParams(Object.entries(firebaseConfig).filter(([, v]) => v) as [string, string][]);
  p.set('v', SDK_VERSION);                       // SW pins the same SDK version
  return navigator.serviceWorker.register(`/firebase-messaging-sw.js?${p}`, { scope: '/' });
}

// Cached app + messaging (Sanad pattern): initializeApp twice throws app/duplicate-app.
let app: any, messaging: any;
async function getMessagingInstance() {
  const { initializeApp, getMessaging } = await sdk() as any;
  if (!app) app = initializeApp(firebaseConfig);
  if (!messaging) messaging = getMessaging(app);
  return messaging;
}

// MUST run from a click handler; no await before requestPermission().
export async function enable() {
  if (!isConfigured() || !('Notification' in window) || !('serviceWorker' in navigator))
    return { ok: false, reason: 'unsupported' as const };
  const granted = await Notification.requestPermission();
  if (granted !== 'granted') return { ok: false, reason: 'denied' as const };
  const { isSupported, getToken } = await sdk() as any;
  if (!(await isSupported())) return { ok: false, reason: 'unsupported' as const };
  setPushOptedOut(false);                          // explicit turn-on clears an earlier opt-out, else syncRegistration stays suppressed
  const reg = await registerServiceWorker();
  const token = await getToken(await getMessagingInstance(), { vapidKey, serviceWorkerRegistration: reg });
  if (!token) return { ok: false, reason: 'no-token' as const };   // wrong VAPID key
  await api.post('/notifications/devices', { token, platform: 'web' });
  setStoredPushToken(token);
  return { ok: true };
}

// App start + visibilitychange, after login. Never prompts.
export async function syncRegistration() {
  if (Notification.permission !== 'granted' || isPushOptedOut()) return;
  /* getToken as above; if token && token !== getStoredPushToken() -> POST, store */
}

// Logout / explicit off. Backend first (token in BODY), then local deleteToken.
export async function disable({ optOut = false } = {}) {
  if (optOut) setPushOptedOut(true);
  const stored = getStoredPushToken();
  if (!stored) return;                            // avoid downloading the SDK for nothing
  try { await api.delete('/notifications/devices', { data: { token: stored } }); } catch {}
  try { const { deleteToken } = await sdk(); await deleteToken(await getMessagingInstance()); } catch {}
  clearStoredPushToken();
}

// Foreground: FCM shows nothing while the tab is focused.
export function onForegroundMessage(cb: (title: string, body: string, data?: Record<string, string>) => void) {
  if (!isEnabledHere()) return () => {};
  let stop: (() => void) | null = null, cancelled = false;
  (async () => {
    const { onMessage } = await sdk();
    const s = onMessage(await getMessagingInstance(), (p) => {
      const { title, body } = p.notification ?? {};
      if (title) cb(title, body ?? '', p.data);
    });
    cancelled ? s() : (stop = s);
  })().catch(() => {});
  return () => { cancelled = true; stop?.(); };
}
```
Also: guard against enable()/sync/disable races with a generation counter (see Sanad webPush.ts) so a late sync cannot re-register after logout.

## Pre-prompt UI
Banner/modal (AR/EN) saying what is sent and that it can be turned off; primary button calls `enable()`; "Not now" stores a dismissal timestamp. If `Notification.permission === 'denied'`, show instructions to re-enable in browser site settings instead of a dead button.

## Flutter notes
`firebase_messaging`: `requestPermission()` (iOS), `getToken()` -> POST `platform` ios/android, `onTokenRefresh` -> re-POST, `onMessage` -> in-app, background handler top-level `@pragma('vm:entry-point')`. Logout: DELETE token + `deleteToken()`.
