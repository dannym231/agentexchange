# AgentExchange

AgentExchange is a command-line competition app where autonomous AI trader agents predict short-term ETH price movement and stake AgentCred credits on each call.

It is the first demo app built on **AgentCred**. AgentCred provides local agent identity, wallet transfers, and reputation events. AgentExchange uses those primitives to run an auditable prediction market: agents stake credits, the market settles outcomes, wallets move funds, and reputation events record prediction performance.

## Product Layers

- **AgentCred** is the infrastructure layer: identity, wallets, local credit transfers, and reputation events for autonomous agents.
- **AgentExchange** is the first competition app: a live/mock ETH prediction market that turns agent decisions into economic outcomes.
- **AgentMarket** is the future platform: a broader marketplace for agent work, payments, reputation, and discovery. It is not part of this v1 repository.

## What Happens In A Round

1. AgentExchange opens a round with an ETH/USD price.
2. Trader agents predict `UP`, `DOWN`, or `FLAT`.
3. Accepted predictions stake AgentCred wallet credits.
4. The round closes with a second ETH/USD price.
5. The market settles winners, losers, or refunds.
6. AgentCred wallet transactions and reputation events complete the audit chain.

Mock mode uses deterministic traders and prices, so it is the best demo path. Live mode uses CoinGecko prices and Claude-generated trader predictions.

## Demo Commands

Run the full test suite:

```bash
venv/bin/python -m unittest discover -v
```

Run a deterministic three-round mock exchange:

```bash
venv/bin/python run_exchange.py --mock --rounds=3
```

Run the same demo with a SQLite ledger:

```bash
venv/bin/python run_exchange.py --mock --rounds=3 --ledger=/tmp/agentexchange-ledger.sqlite3
```

## SQLite Ledger

When `--ledger=PATH` is provided, AgentExchange writes an audit ledger to SQLite.

The v1 ledger records:

- runs
- rounds
- open and close price observations
- accepted predictions
- stake amounts and stake wallet transaction IDs
- final prediction state and PnL
- settlement lines
- settlement payout/refund wallet transaction IDs when credits move
- AgentCred reputation event IDs
- wallet balance after settlement

Decimal credit values are stored as strings to preserve fixed-precision accounting.

## Mock Mode

Mock mode requires no API key and no network access:

```bash
venv/bin/python run_exchange.py --mock --rounds=3
```

It runs immediately and repeats a three-round sequence: `UP`, `DOWN`, then `FLAT`. This is the recommended founder/demo flow because it exercises prediction collection, stake transfers, settlement, reputation events, leaderboard updates, and optional ledger persistence.

## Live Mode

Live mode requires an Anthropic API key and network access for CoinGecko:

```bash
venv/bin/python run_exchange.py --fast --rounds=1
```

Without `--fast`, rounds use the standard five-minute duration:

```bash
venv/bin/python run_exchange.py --rounds=3
```

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
```

For live mode, create `.env`:

```text
ANTHROPIC_API_KEY=your_api_key_here
```

## Not Included In v1

AgentExchange v1 is intentionally narrow. It does not include:

- dashboard
- API server
- real on-chain wallets
- AgentMarket
- deployment
- external worker system
- Coinbase/Base integration

The current goal is a clear local demo: agents compete, credits move, reputation changes, and the SQLite ledger preserves the audit trail.
