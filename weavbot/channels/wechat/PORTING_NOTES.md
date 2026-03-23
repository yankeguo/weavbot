# Wechat Porting Notes

This channel is ported from the local unpacked npm references under `samples/`:

- `samples/openclaw-weixin/package/src/channel.ts`
- `samples/openclaw-weixin/package/src/api/api.ts`
- `samples/openclaw-weixin/package/src/api/types.ts`
- `samples/openclaw-weixin/package/src/monitor/monitor.ts`
- `samples/openclaw-weixin/package/src/messaging/process-message.ts`
- `samples/openclaw-weixin/package/src/messaging/send.ts`
- `samples/openclaw-weixin/package/src/messaging/send-media.ts`
- `samples/openclaw-weixin/package/src/auth/login-qr.ts`
- `samples/openclaw-weixin/package/src/auth/accounts.ts`
- `samples/openclaw-weixin/package/src/api/session-guard.ts`
- `samples/openclaw-weixin/package/src/storage/sync-buf.ts`
- `samples/openclaw-weixin-cli/package/cli.mjs`

Porting intent:

- Keep protocol-compatible HTTP endpoints and headers.
- Keep long-poll + cursor persistence behavior.
- Keep session-expired pause semantics (`errcode=-14`).
- Keep media upload via CDN + AES-128-ECB.
- Keep QR login as a dedicated command (`weavbot wechat login`).
