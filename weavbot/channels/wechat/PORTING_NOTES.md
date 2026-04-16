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

## Latest sync (2026-04-16) — upstream v2.1.8

### Added / Fixed

1. **iLink-App-Id header** (`api.py`)
   - Changed from empty string to `"bot"` to match upstream `package.json` `ilink_appid` field.

2. **StreamingMarkdownFilter** (`markdown_filter.py`)
   - Ported the upstream character-level filter to Python.
   - Integrated into `channel.py` outbound text path so Markdown goes from unsupported to partially supported.

3. **QR login protocol updates** (`auth.py`)
   - Removed client-side timeout for `get_bot_qrcode` (matches upstream 2.1.4).
   - Added `scaned_but_redirect` IDC redirect handling.
   - Added QR auto-refresh on expiry (max 3 refreshes).
   - Network/gateway errors during status polling are treated as `wait` instead of fatal.
   - `LoginResult.base_url` now returns server-provided `baseurl` instead of hard-coded `DEFAULT_BASE_URL`.

4. **Dynamic long-poll timeout** (`polling.py`, `api.py`)
   - `get_updates` now accepts an optional `timeout_ms` parameter.
   - `run_long_poll` reads `resp.longpolling_timeout_ms` from the server and updates the next poll timeout accordingly.

5. **CDN upload retry** (`media.py`)
   - Added `_cdn_upload_with_retries()` with up to 3 retry attempts on server errors (5xx).
   - Client errors (4xx) abort immediately, matching upstream `cdn-upload.ts`.

6. **CDN download full_url** (`media.py`, `channel.py`)
   - `download_media_file` now accepts optional `full_url` parameter, used directly when provided.
   - Inbound media extraction reads `media.full_url` and passes it to the download function.

7. **Inbound image aeskey** (`channel.py`)
   - Now checks `image_item.aeskey` (hex key) first, falling back to `media.aes_key`.
   - Hex key is converted to base64 to match the decrypt function's expected format.

8. **Voice-to-text** (`channel.py`)
   - Added extraction of `voice_item.text` (voice-to-text transcription) from inbound messages.

9. **Quoted message handling** (`channel.py`)
   - Added `ref_msg` extraction: builds `[引用: title | body]` prefix from quoted messages.

10. **TypingManager config cache** (`typing_manager.py`)
    - Added exponential backoff retry on `getConfig` failures (2s → 4s → ... → 3600s max).
    - Added jittered TTL for cache entries, matching upstream `WeixinConfigManager`.

11. **Session guard on outbound** (`channel.py`)
    - `send()` now checks `guard.is_paused()` before attempting any API call.

12. **Protocol type alignment** (`types.py`)
    - Added `client_id`, `update_time_ms`, `delete_time_ms` to `WechatMessage`.
    - Added `full_url` to `CdnMedia`.

13. **Cipher size calculation** (`media.py`)
    - Fixed `_cipher_size` to use `ceil(size/16)*16` matching upstream `aesEcbPaddedSize`.
