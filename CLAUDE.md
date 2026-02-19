# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_early_entry.py -v

# Run a single test
pytest tests/test_early_entry.py::TestShouldEnter::test_all_conditions_met -v

# Install dependencies
pip install fastapi "uvicorn[standard]" pydantic pydantic-settings pyyaml sse-starlette aiofiles pytest pytest-asyncio httpx

# Start server (DRYRUN mode)
BOT_CONFIG=config.example.yaml uvicorn bot.main:app --host 0.0.0.0 --port 8080
```

Note: `pythonpath = ["."]` is set in pyproject.toml, so `PYTHONPATH=.` is not needed for pytest.

## Architecture

DRYRUN-mode trading bot that polls a TA JSON file every second, evaluates 3 pluggable strategies, simulates order fills, and pushes state to a web dashboard via SSE.

### Data Flow (per tick)

```
TA JSON file → TAReader → TASignal
  ├→ MarketManager.check_market_change() → reset all if slug changed
  ├→ OrderTracker.update_prices() → simulate fills (BUYs first, then SELLs)
  └→ StrategyEngine.tick()
       ├─ Tick active strategy (state transitions)
       └─ If none active: evaluate S1→S2→S3 entry (first match wins)
            └→ BotState snapshot → SSE /api/stream → Browser EventSource
```

### Key Design Decisions

- **All prices are integers (cents)** — avoids float rounding. P&L converted to dollars only for display.
- **`paired_buy_id` on SELL orders** — DryRunOrderTracker skips SELL fill check until the paired BUY is filled. BUYs are processed before SELLs in `update_prices()`.
- **Mutual exclusion** — only one strategy can be in ENTERING/RUNNING/EXITING at a time. StrategyEngine enforces this.
- **Entry vs tick separation** — `should_enter()` is called by StrategyEngine (controls mutual exclusion); `tick()` handles state transitions within the strategy.
- **BotState is a full snapshot** — every SSE message contains complete state, no deltas.
- **Bot loop as asyncio task** — launched in FastAPI's `lifespan`, runs alongside the web server.

### Strategy State Machine

Strategies 1 & 2: `PENDING → ENTERING → EXITING → COMPLETED` (SELL submitted alongside BUY)
Strategy 3: `PENDING → ENTERING → RUNNING → EXITING → COMPLETED` (SELL submitted after BUY fills and price dips)

`BaseStrategy` in `bot/strategies/base.py` implements the state machine dispatch. Subclasses override `should_enter()`, `_do_enter()`, and `_do_expire()`. Strategy 3 also overrides `_on_buy_filled()` and `_tick_running()`.

### OrderTracker Abstraction

`bot/order_tracker/interface.py` defines the ABC. `DryRunOrderTracker` simulates fills locally; `LiveOrderTracker` is a stub for future Polymarket CLOB API integration. Strategies interact only with the interface.

### Testing Pattern

Tests use `make_signal(**overrides)` from `tests/conftest.py` to create TASignal instances with sensible defaults. Strategy tests instantiate `DryRunOrderTracker` directly and call `tracker.update_prices()` to simulate market conditions. `BotLoop.tick_with_signal()` enables integration tests without async or file I/O.

## Spec Reference

Full specification is in `docs/specs.md`. Key clarifications applied during implementation:
- SELL base price = BUY order's limit price (not market price)
- DOWN BUY at −5% is intentional (patient entry)
- Strategy 3 has no TA threshold by design
- Unfilled BUY at expiry = no trade (cancel both, no P&L)
