# Wechat Porting Notes

This channel is ported from the local unpacked npm references under `samples/`:

- `samples/openclaw-weixin/src/channel.ts`
- `samples/openclaw-weixin/src/api/api.ts`
- `samples/openclaw-weixin/src/api/types.ts`
- `samples/openclaw-weixin/src/monitor/monitor.ts`
- `samples/openclaw-weixin/src/messaging/process-message.ts`
- `samples/openclaw-weixin/src/messaging/send.ts`
- `samples/openclaw-weixin/src/messaging/send-media.ts`
- `samples/openclaw-weixin/src/auth/login-qr.ts`
- `samples/openclaw-weixin/src/auth/accounts.ts`
- `samples/openclaw-weixin/src/api/session-guard.ts`
- `samples/openclaw-weixin/src/storage/sync-buf.ts`
- `samples/openclaw-weixin-cli/package/cli.mjs`

Porting intent:

- Keep protocol-compatible HTTP endpoints and headers.
- Keep long-poll + cursor persistence behavior.
- Keep session-expired pause semantics (`errcode=-14`).
- Keep media upload via CDN + AES-128-ECB.
- Keep QR login as a dedicated command (`weavbot wechat login`).

## Latest sync (2026-04-16) — upstream v2.1.7

### Added / Fixed

1. **Missing iLink headers** (`api.py`)
   - Added `iLink-App-Id` and `iLink-App-ClientVersion` to all GET and POST requests.
   - `iLink-App-ClientVersion` is encoded as `0x00MMNNPP` from `weavbot.__version__`.

2. **StreamingMarkdownFilter** (`markdown_filter.py`)
   - Ported the upstream character-level filter to Python.
   - Integrated into `channel.py` outbound text path so Markdown goes from unsupported to partially supported.

3. **QR login protocol updates** (`auth.py`)
   - Removed client-side timeout for `get_bot_qrcode` (matches upstream 2.1.4).
   - Added `scaned_but_redirect` IDC redirect handling.
   - Added QR auto-refresh on expiry (max 3 refreshes).
   - Network/gateway errors during status polling are treated as `wait` instead of fatal.

4. **Dynamic long-poll timeout** (`polling.py`, `api.py`)
   - `get_updates` now accepts an optional `timeout_ms` parameter.
   - `run_long_poll` reads `resp.longpolling_timeout_ms` from the server and updates the next poll timeout accordingly.
