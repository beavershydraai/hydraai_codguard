# COD Guard API contract

`openapi.yaml` is the contract between the backend and its clients: the shop web app, the buyer
confirmation page and external sales tools. It is OpenAPI 3.1, generated from the backend code
(`backend/app/schemas/` and `backend/app/api/v1/`). Do not edit it by hand.

## Use it from the frontend

The frontend calls the API through a client generated with [Hey API](https://heyapi.dev)
(`frontend/openapi-ts.config.ts`): typed SDK functions plus TanStack Query options.

```bash
cd frontend && pnpm generate:api      # writes frontend/src/api/gen/
```

```ts
import { useQuery } from "@tanstack/react-query";
import { listOrdersOptions } from "@/api/gen/@tanstack/react-query.gen";

const { data } = useQuery(listOrdersOptions({ query: { status: ["pending_review"], limit: 50 } }));
```

## Mock server

The frontend has its own stateful mock (`frontend/src/mocks/`) that answers endpoints the
backend still returns 501 for; see `frontend/README.md`. Prism below serves the contract's fixed
examples, which is useful to check the contract itself.

### Prism

The backend returns `501 not_implemented` for endpoints that are not built yet. Until then, run
a mock server that answers with the examples in the contract:

```bash
npx @stoplight/prism-cli mock api/openapi.yaml        # http://127.0.0.1:4010
```

- Send any `Authorization: Bearer <token>` header; without it the mock answers 401.
- Force an error response with the `Prefer` header, e.g. `Prefer: code=409` on
  `POST /api/v1/orders/{order_id}/calls` returns the `contact_blocked` example.
- Add `-d` to generate random data from the schemas instead of the fixed examples.

## Conventions

- Money: integer VND in fields ending `_vnd`.
- Time: ISO 8601 with offset. Shops operate in Vietnam time (`+07:00`).
- Enums: English `snake_case`. Each enum's description lists the Vietnamese UI labels.
- Errors: `application/problem+json` (RFC 9457) with a machine-readable `code`, plus `errors`
  for validation and `block_reasons` for `contact_blocked`.
- Lists: cursor pagination. Pass `next_cursor` back as `cursor`.
- Auth: the shop app signs in with `POST /api/v1/auth/login` and sends the returned token as
  `Authorization: Bearer` (Firebase ID tokens will replace it, E7.1); `X-Api-Key` for the
  intake API; the buyer confirmation page uses the token in its URL.
- Phone numbers in examples use the invalid prefix `+84000…` on purpose. Never put a real
  phone number in examples, fixtures or tests.

## Changing the contract

1. Edit the Pydantic models or routes in `backend/`.
2. Run `uv run python -m app.openapi_export` in `backend/`.
3. Run `pnpm generate:api` in `frontend/` to regenerate the client.
4. Commit all three. `uv run pytest` fails if `openapi.yaml` is out of date or an example does not
   match its schema; the frontend CI job fails if `frontend/src/api/gen/` is out of date.

Mention breaking changes (removed or renamed fields, new required fields) in the PR description
so the frontend can follow.
