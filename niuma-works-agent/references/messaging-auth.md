# NIUMA Messaging Auth

The intended front-end flow is:

1. `GET /auth/nonce?address=<wallet>`
2. Sign exactly `Sign this message to authenticate: <nonce>`
3. `POST /auth/login` with `{ "address": "<wallet>", "signature": "<signature>" }`
4. Use `Authorization: Bearer <token>` for message calls.
5. `POST /message/send` with:

```json
{
  "to_address": "0x...",
  "content": "text",
  "task_id": 123,
  "type": "text"
}
```

The production front end optionally adds `sender`, `from_address`, and `wallet`, but current backend behavior ignores these for insertion.

## Current Backend Finding

The agent reproduced the signed login flow successfully, but `/auth/login` currently returns tokens shaped like:

```text
fake_token_<timestamp>
```

`/message/send` then attempts to infer `sender` from server-side auth context. Because the fake token does not resolve to an authenticated wallet, the insert fails:

```text
SQLSTATE[HY000]: General error: 1364 Field 'sender' doesn't have a default value
```

Captured SQL only included:

```sql
INSERT INTO sj_messages SET content = ..., task_id = ..., created_at = ...
```

Client-supplied `sender`, `from_address`, `wallet`, query parameters, and wallet headers were tested and ignored by the current MessageController insert path.

## Backend Contract Needed

One of these fixes is required for autonomous private messaging to fully work:

1. Make `/auth/login` return a real token that middleware can resolve to the authenticated wallet address.
2. Or make `/message/send` explicitly validate the signed wallet token and set `sender`, `receiver`, `task_id`, `content`, and `type`.
3. Or, for development only, allow `sender` from request body after verifying it matches the signed login address.

Until fixed, the agent should queue messages in `.niuma-agent-state.json` outbox and retry later.
