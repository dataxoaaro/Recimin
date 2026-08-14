# Sharing to Recimin from an iPhone

An installed web app cannot appear in the iOS share sheet. Web Share Target is
not implemented in WebKit — [the bug](https://bugs.webkit.org/show_bug.cgi?id=194593)
was filed in February 2019 and is still unassigned, and it is absent from
Safari 26, the Safari 27 beta and Interop 2026. A Shortcut is the way.

Roughly ten minutes, once per phone.

## 1. Create a device key

In Recimin: **Settings → Devices**, name it after the phone (`Aaro iPhone`),
tap **Add**. Copy the key immediately — it is shown once and never again.

Each phone gets its own key so a lost phone is one revocation rather than a
household-wide rotation.

## 2. Build the Shortcut

Shortcuts app → **+** → add these seven actions in order.

| # | Action | Setting |
|---|---|---|
| 1 | *Receive input from* | **Anything** — set in the shortcut Details pane |
| 2 | **Get URLs from Input** | Input: *Shortcut Input* |
| 3 | **If** | *URLs* → *count* → **is** → **0** |
| 4 | ↳ **Match Text** | Text: *Shortcut Input*, Pattern: `https?://[^\s]+` |
| 5 | ↳ **Get Group from Matched Text** | Group index 0 |
| 6 | **Get Contents of URL** | see below |
| 7 | **Show Notification** | Title: `Recimin`, Body: `Saving…` |

**Action 6, expanded:**

- URL: `https://your-domain.example/api/import` (your instance's public address)
- Method: **POST**
- Headers:
  - `Authorization` → `Bearer <the key from step 1>`
  - `Content-Type` → `application/json`
- Request Body: **JSON**, one field: `url` → the URL from step 2 (or step 5)

Then open Details and turn on **Show in Share Sheet**, with the type left as
**Anything**.

### Why "Anything" and why the regex

Narrowing the input type risks the Shortcut vanishing from Instagram and TikTok
entirely. And both apps frequently share **plain text containing a URL** rather
than a URL object, which is why steps 3–5 exist: without them the Shortcut
silently does nothing on roughly half the posts you try.

## 3. Pin it (iOS 26)

iOS 26 collapses Shortcuts behind a **More** button in the share sheet, so it
will not appear until you pin it.

Share anything once → scroll to the bottom of the share sheet → **Edit
Actions** → find Recimin → pin it to the top.

One-off, per phone. Skip it and the whole flow feels broken.

## 4. Turn on notifications

The API answers in about 200 ms and does the real work afterwards, so the
result arrives as a push rather than in the Shortcut.

Add Recimin to the Home Screen (Safari → Share → *Add to Home Screen*), open it
from the Home Screen icon, then **Settings → Notifications → Turn on
notifications**. Web Push only works in an installed PWA, not in a Safari tab.

## Using it

Instagram: tap the paper-plane on a reel → **Recimin**.
TikTok: **More** on the share screen → **Recimin**.

The notification arrives when the recipe is ready. Tapping it opens the draft.

## Sharing with the household

Share the Shortcut by iCloud link, but **replace the key** with a placeholder
first, and have each person paste their own from their own Settings page.

Two reasons: the key is visible in plaintext to anyone with the link, and
iCloud links are **snapshots** — editing the Shortcut afterwards does not
propagate to anyone who already installed it.

Never post that link anywhere public.

## When it does not work

| Symptom | Cause |
|---|---|
| Not in the share sheet at all | Not pinned (step 3), or the input type was narrowed |
| Works from Safari, not Instagram | Steps 3–5 missing; the app shared text, not a URL |
| "Could not connect" | The URL must be a real hostname with a valid certificate. Since iOS 17, App Transport Security rejects raw IP addresses, and self-signed certificates cannot be trusted. |
| 401 | The key was revoked, or `Bearer ` is missing before it |
| Nothing happens after the notification | Check **Imports** in the app — the job may have failed and can be retried there |
