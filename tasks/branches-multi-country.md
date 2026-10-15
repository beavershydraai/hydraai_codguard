# One shop, a branch in each of three APAC countries, one risk model per country

Status: built (15 Oct 2026); see "Results on synthetic data" at the end.

## Decisions (owner, 15 Oct)

- The demo is one shop, `shop_demo` ("Sample Fashion Shop"), with branches; no other shops in the demo.
- Countries: Vietnam, Singapore, the Philippines.
- Real currencies (VND, SGD, PHP), not amounts converted to VND.
- One risk model per country: orders from different countries are never trained together. Branches in the same country share their country's model.
- Any number of branches per country; the demo has two in Vietnam and one each in Singapore and the Philippines.
- Before M3 (16 Oct evening): branches, per-country data and per-country models. Onboarding (import orders, a Train button) comes after M3.
- Tier cut-offs stay the same in every country (0.08 / 0.20 / 0.40).

## Branches

| `branch_id` | Country | Currency | Time zone | Phone | Ships to (generator) |
|---|---|---|---|---|---|
| `branch_VN_HCM` | VN | VND | Asia/Ho_Chi_Minh (UTC+7) | `+84`, 9–10 digits | TP Hồ Chí Minh, Cần Thơ |
| `branch_VN_HN` | VN | VND | Asia/Ho_Chi_Minh (UTC+7) | `+84`, 9–10 digits | Hà Nội, Hải Phòng, Đà Nẵng |
| `branch_SG` | SG | SGD | Asia/Singapore (UTC+8) | `+65`, 8 digits | Central, East, North, North-East, West |
| `branch_PH` | PH | PHP | Asia/Manila (UTC+8) | `+63`, 10 digits | Metro Manila, Cebu, Davao |

A second branch in a country is one more row with the same country: it uses that country's model.

Config file `backend/config/branches.yaml` holds, per branch: country, currency, time zone, phone country code, regions, and the costs the policy uses (failed delivery, link, AI call, deposit) in that currency. It replaces the VND constants in `ShopSettings` defaults for branch orders.

Synthetic phones keep the `000` prefix after the country code (`+84000…`, `+65000…`, `+63000…`): no carrier issues them, and `check_phone_numbers.py` is extended to allow exactly those.

## How an order knows its branch

Each branch has its own intake key: `INTAKE_API_KEYS` entries become `key:shop:branch[:noagents]`. Intake stores `branch_id`, `country`, `currency` and `timezone` on the order from the key, so a branch's sales tool needs no new field. An old `key:shop` entry maps to `branch_VN_HCM`.

## Currency (API contract change)

- `OrderCreate`, order views and dashboard results get `currency` (ISO 4217: `VND`, `SGD`, `PHP`).
- Amounts are integers in the currency's minor unit: VND has none, SGD and PHP use cents (`SGD 25.90` → `2590`). The field names keep their `_vnd` suffix for compatibility, like `label_vi` holding English; their descriptions say "in the order's currency".
- Intake rejects an order whose `currency` differs from its branch's (422).
- Frontend: one `formatMoney(amount, currency)` replaces `formatVnd` where amounts are shown; the API client is regenerated (`pnpm generate:api`).

## Features and time

- Hours and days come from the branch's time zone. `placed_hour_vn` becomes `placed_hour_local` (stored orders migrated once, as with the house-number rename).
- Money features (`cod_amount_vnd`, `log_cod_amount`) stay in the branch currency; each model only ever sees one currency.
- Contact hours (08:00–21:00) apply in the branch's local time.

## One model per country

- Artifacts: `models/{FIRESTORE_DATABASE}/{country}/latest/` and `/v{timestamp}/`.
- Training data for a country: the orders of all its branches.
- `codguard-train` and `codguard-monitor` take `--country` and, without it, loop over every country. The daily schedule stays one job run.
- The engine loads and caches models per country, from the order's `country`; an order of a country with no model yet is stored unscored, as today.
- The backtest (E9.1) is computed per country; `GET /dashboard/backtest` takes `country`.

## Synthetic data per country (`backend/app/demo/`)

- `world.py`: buyers, orders and delivery outcomes per country, from the sandbox generator, with a country pack: names, regions, address format, phone format, price range in the local currency, channels, buyer mix and behaviour.
- `seed.py`: writes 90 days of history per branch (about 6,000–9,000 orders each, with outcomes) to Firestore with a fixed seed, so a reset gives the same demo (E1.3).
- The simulator posts live orders per branch with that branch's key.

### Assumptions to verify (made up for the simulation, not market data)

| Item | VN | SG | PH |
|---|---|---|---|
| Orders a day (history) | 100 | 60 | 80 |
| Buyer-caused failure rate | ~13 % (as now) | lower | higher |
| Failed delivery cost | 60,000 VND | assumption | assumption |
| COD share of orders | high | low; SG buyers mostly pay online | high |
| Channel mix | Facebook, TikTok, Zalo | website, Facebook | Facebook, TikTok |

These need real numbers or a source before they go on a slide.

## Existing data

- The current `vn-synthetic` history (`shop_0`–`shop_5`) is not part of the one-shop demo. After the new seed is loaded and the models are trained, the owner decides whether to delete it.
- E2.2 (synthetic data generator, Trung) overlaps with `world.py`; agree the split with him before building.

## Order of work

1. Branch config and keys; intake stores the branch; phone normalisation for +65 and +63.
2. Currency in the contract, intake validation; frontend `formatMoney` and regenerated client.
3. Country packs and the seed script; load the history.
4. Per-country train, monitor, engine and backtest; train every country.
5. Simulator per branch; docs (`AGENTS.md`, `README.md`, `docs/data-model.md`).

Estimate: about 1.5 days, which runs past M3. Steps 1, 3 and 4 alone fit M3; the currency step is the one that needs the frontend.

## Results on synthetic data (local run, 15 Oct)

90 days, 22,128 orders. Held-out newest 20 % of each country's labelled orders; "oracle" ranks by the
true failure probability the generator used, so it is the best any model could do on this data.

| Country | Failure rate | Failures caught in the top 20 % (model) | Lift | Oracle lift |
|---|---|---|---|---|
| VN | 12.5 % | 67 % | 3.34 | 3.64 |
| SG | 3.5 % | 81 % | 4.05 | 3.81 (few failures: noisy) |
| PH | 14.1 % | 60 % | 2.99 | 3.42 |

The earlier lift of 2.8–2.9 was a measuring error: calibrated scores tie, so a "score at least the
80th percentile" cut took more than 20 % of orders. `train.py` now ranks by the raw score.
