# Polymarket Up & Down Bot — Technical Specification

## Overview

An automated trading bot that places BUY and SELL limit orders on the Polymarket **BTC Up & Down 15 minutes** prediction market. The bot evaluates multiple configurable strategies on each poll cycle and submits orders via the Polymarket CLOB API. A companion web UI provides real-time monitoring.

The bot consumes a JSON file produced by an external TA tool ([PolymarketBTC15mAssistant](https://github.com/lliwog/PolymarketBTC15mAssistant)), which computes a technical-analysis weighted directional score. This score is the primary signal used by the strategies.

---

## Technology Stack

- **Backend**: Python
- **Frontend**: Plain HTML/JS served by a Python web server (FastAPI or Flask)
- **Frontend updates**: Server-Sent Events (SSE) for live data push
- **Polymarket integration**: CLOB API authenticated with a private key / wallet

---

## TA Signal JSON

The bot polls a JSON file from a configurable directory **every second**. The file is written by PolymarketBTC15mAssistant and has the following schema:

```json
{
  "timestamp": "2026-02-18T14:32:01.123Z",
  "marketSlug": "will-btc-go-up-or-down-in-the-next-15-minutes-02-18-2026-2-30-pm",
  "timeLeftMin": 8.32,
  "currentPrice": 96432.17,
  "priceToBeat": 96410.50,
  "spotPrice": 96445,
  "upScore": 7,
  "downScore": 3,
  "rawUp": 0.7,
  "adjustedUp": 0.6107,
  "adjustedDown": 0.3893,
  "timeDecay": 0.5547,
  "regime": "TREND_UP",
  "signal": "BUY UP",
  "recommendation": "UP:MID:strong",
  "edgeUp": 0.1207,
  "edgeDown": -0.1207,
  "marketUp": 49,
  "marketDown": 51,
  "rsi": 58.3,
  "vwapSlope": 1.24,
  "macdHist": 0.47
}
```

**Key fields used by the bot:**

| Field | Description |
|---|---|
| `marketSlug` | Identifies the current active market. When this value changes, all strategies reset to PENDING. |
| `timeLeftMin` | Minutes remaining in the current 15-minute market period. |
| `adjustedUp` / `adjustedDown` | Normalized TA probabilities (0–1). Used as the TA score in strategy conditions (e.g. `adjustedUp > 0.65` = "TA > 65%"). |
| `signal` | `"BUY UP"` or `"BUY DOWN"` — determines the side for BUY orders. |
| `marketUp` / `marketDown` | Current Polymarket token prices in cents for the UP and DOWN tokens respectively. |
| `upScore` / `downScore` | Integer directional scores (0–10), displayed in the UI. |
| `recommendation` | Human-readable signal string, displayed in the UI. |
| `currentPrice` / `priceToBeat` | BTC spot price and the reference price to beat, displayed in the UI. |

---

## Business Rules

- **Limit orders only**: The bot submits limit orders exclusively to minimize fees. Market orders are never used.
- **Market auto-switching**: When a market expires, the bot detects the new `marketSlug` in the JSON file and automatically switches to the new market. All strategies are reset to PENDING.
- **Operation mode**: The bot runs in **DRYRUN mode by default**. LIVE mode must be explicitly enabled via configuration.
- **DRYRUN mode behavior**: Orders are not submitted to Polymarket. Fill simulation is handled by the Order Tracker abstraction (see below): an order is considered filled when the relevant token price (`marketUp` or `marketDown` from the JSON file) crosses the order's limit price on a subsequent poll. P&L is computed accordingly.

---

## Strategy Engine

### Architecture

Each strategy is implemented as an independent, pluggable module. Strategies can be enabled or disabled via configuration without code changes.

### Strategy Lifecycle

Each strategy has one of the following states:

| State | Description |
|---|---|
| `PENDING` | Entry conditions not yet met. No orders submitted. |
| `ENTERING` | BUY order submitted to Polymarket; waiting for it to be filled. |
| `RUNNING` | BUY order filled; monitoring for the exit condition before submitting the SELL order. Used by Strategy 3 only (waiting for the price dip to 50¢). |
| `EXITING` | SELL order submitted to Polymarket; waiting for it to be filled. |
| `COMPLETED` | Terminal state: SELL order filled, or market expired with a known win/loss outcome. |

**State flow per strategy type:**
- **Strategies 1 & 2**: `PENDING → ENTERING → EXITING → COMPLETED`
  The SELL order is submitted immediately alongside the BUY order, so the `RUNNING` state is skipped.
- **Strategy 3**: `PENDING → ENTERING → RUNNING → EXITING → COMPLETED`
  After the BUY fills, the bot monitors for the price dip before submitting the SELL.

**Rules:**
- Only one strategy may be in `ENTERING`, `RUNNING`, or `EXITING` state at a time. All others remain `PENDING`.
- A strategy transitions to `ENTERING` when its BUY order is submitted.
- A strategy transitions to `RUNNING` when its BUY order is filled and a SELL order has not yet been submitted (Strategy 3 only).
- A strategy transitions to `EXITING` when its SELL order is submitted.
- A strategy transitions to `COMPLETED` when its SELL order is filled, or when the market expires.
- When a new market starts, all strategies reset to `PENDING`.

### Price convention

All share prices referenced in strategy conditions and order parameters are **Polymarket token prices in cents** (e.g. 40¢ = $0.40). All percentage adjustments (e.g. +5%, +30%) are applied to the token price in cents.

---

### Order Tracking Abstraction

Order fill detection must be fully abstracted behind an `OrderTracker` interface so that strategies are decoupled from the execution mode. The strategy engine calls the same interface regardless of whether the bot is in DRYRUN or LIVE mode.

#### Interface contract

```
OrderTracker
  submit_buy(side, size, price) → order_id
  submit_sell(side, size, price) → order_id
  is_filled(order_id) → bool
  get_fill_price(order_id) → float | None
  cancel(order_id) → void
```

#### LIVE mode — `LiveOrderTracker`

- **Order submission**: Orders are submitted via the Polymarket CLOB API.
- **Fill detection (primary)**: Subscribe to the Polymarket **WebSocket user channel** on startup. Listen for `order_matched` / `order_filled` events keyed by `order_id`. Transition strategy state as soon as the event is received.
- **Fill detection (fallback)**: If the WebSocket connection is unavailable or drops, fall back to polling `GET /order/{order_id}` on every bot cycle (every second). Reconnect the WebSocket in the background with exponential backoff.
- **Order cancellation**: Call `DELETE /order/{order_id}` when an open order needs to be cancelled (e.g. on market expiry).

#### DRYRUN mode — `DryRunOrderTracker`

- **Order submission**: Orders are not sent to Polymarket. A local record is created with a generated `order_id`, storing the side, size, and limit price.
- **Fill simulation**: On every poll cycle, the tracker checks the relevant token price from the TA JSON file (`marketUp` for UP orders, `marketDown` for DOWN orders):
  - A **BUY** order is considered filled when `token_price <= order_limit_price`
  - A **SELL** order is considered filled when `token_price >= order_limit_price`
- **Fill price**: The simulated fill price is the order's limit price (not the current market price).
- **Order cancellation**: The local record is simply marked as cancelled.

#### Market expiry handling (both modes)

When a market expires (`timeLeftMin <= 0` or `marketSlug` changes), the bot must cancel all open orders via `OrderTracker.cancel()` and resolve any `ENTERING` or `EXITING` strategies to `COMPLETED` with the appropriate win/loss outcome as defined per strategy.

---

## Strategies

### Strategy 1 — Early Entry

**Activation window:** More than 10 minutes remaining.

**Entry conditions:**
- `timeLeftMin > 10`
- `adjustedUp > 0.65` OR `adjustedDown > 0.65` (i.e. TA score > 65% in either direction)
- The favored side's token price (`marketUp` or `marketDown`) is less than **40¢**

**BUY order (submitted when all conditions are met):**
- Side: determined by `signal` field (UP or DOWN)
- Size: 10 shares
- Price: token price + 5% if buying UP; token price − 5% if buying DOWN

**SELL order (submitted immediately after the BUY order is submitted):**
- Side: same token as BUY
- Size: 10 shares
- Price: BUY token price + 30%, capped at 99¢

**Expiry behavior:** If the market expires before the SELL order fills → **loss**.

---

### Strategy 2 — Mid-Game Entry

**Activation window:** Between 5 and 10 minutes remaining.

**Entry conditions:**
- `5 <= timeLeftMin <= 10`
- TA score > 70% (`adjustedUp > 0.70` or `adjustedDown > 0.70`)
- The favored side's token price is less than **45¢**

**BUY order:**
- Side: determined by `signal` field
- Size: 10 shares
- Price: token price + 5% if buying UP; token price − 5% if buying DOWN

**SELL order (submitted immediately after the BUY order is submitted):**
- Side: same token as BUY
- Size: 10 shares
- Price: BUY token price + 40%, capped at 99¢

**Expiry behavior:** If the market expires before the SELL order fills → **loss**.

---

### Strategy 3 — Late Scalp (two-phase)

**Activation window:** Less than 2 minutes remaining.

This strategy operates in two sequential phases. Phase 2 only activates after Phase 1 BUY is filled.

#### Phase 1 — Entry

**Entry conditions:**
- `timeLeftMin < 2`
- The favored side's token price is above **94¢**

**BUY order:**
- Side: determined by `signal` field
- Size: 100 shares
- Price: **93¢** (intentionally below market — waits for a momentary dip)
- If the price never dips to 93¢ before market expiry, the BUY does not fill and Phase 2 is never triggered.

#### Phase 2 — Exit (only activated after Phase 1 BUY fills)

**Condition:** The same token's price dips to 50¢ or below.

**SELL order:**
- Side: same token as Phase 1 BUY (UP→sell UP, DOWN→sell DOWN)
- Size: 100 shares
- Price: **50¢**

**Expiry behavior:**
- If the market expires and the SELL was **not** filled (price never dipped to 50¢):
  - **Win** if the market resolves in the same direction as the BUY (shares resolve at 100¢ each)
  - **Loss** if the market resolves against the BUY
- If the SELL **was** filled at 50¢ before expiry → outcome is recorded immediately.

---

## Web Frontend

The frontend is served by the Python backend and updated in real time via **Server-Sent Events (SSE)**.

### Dashboard display

**Market data** (sourced from the TA JSON file):

| Field | Description |
|---|---|
| `marketSlug` | Current market identifier |
| `timeLeftMin` | Time remaining in the current period |
| `upScore` / `downScore` | TA directional scores |
| `recommendation` | TA signal recommendation string |
| `currentPrice` | BTC spot price |
| `priceToBeat` | BTC reference price to beat |

**Bot status:**

| Field | Description |
|---|---|
| Mode | `DRYRUN` or `LIVE` |
| Strategy status | `PENDING`, `RUNNING`, or `COMPLETED` for each strategy |
| Global P&L | Combined P&L across all strategies and markets |

**Per strategy (shown when RUNNING or COMPLETED):**
- P&L for that strategy
- Submitted limit orders — displayed in **blue**
- Executed limit orders — displayed in **green**

---

## Configuration

The following parameters must be configurable (e.g. via a config file or environment variables):

- Path to the TA JSON file directory
- Operation mode: `DRYRUN` or `LIVE`
- Polymarket private key / wallet credentials
- Enabled/disabled flag per strategy

---

## Out of Scope (Future Versions)

The following features are explicitly **not** part of the initial implementation:

- P&L breakdown by time window (hour / day / week / month)
- Execution reports and P&L summaries via Telegram
- Persistent trade storage in a SQL database
- Per-minute market data snapshots for backtesting
- Manual SELL order creation for human intervention