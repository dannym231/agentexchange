import time
import sys

from anthropic import APIError

from agents.trader import MockTraderAgent, TraderAgent
from core.market import Market, MarketDataError, MockPriceFeed, ROUND_DURATION_SECS
from core.models import Round

# ── Agents ───────────────────────────────────────────────────────────────────

def build_traders(mock: bool = False) -> list[TraderAgent]:
    trader_class = MockTraderAgent if mock else TraderAgent
    return [
        trader_class("momentum-01",     "momentum",     wallet_balance=20.0),
        trader_class("contrarian-01",   "contrarian",   wallet_balance=20.0),
        trader_class("conservative-01", "conservative", wallet_balance=20.0),
        trader_class("degen-01",        "degen",        wallet_balance=20.0),
    ]


# ── Display helpers ───────────────────────────────────────────────────────────

def divider(char="─", width=70):
    print(char * width)

def print_predictions(round_: Round):
    divider()
    print(f"  {'AGENT':>14}   {'DIR':4}  {'STAKE':>5}   REASONING")
    divider()
    for p in round_.predictions:
        print(f"  {p.agent_id:>14}   {p.direction:4}  {p.stake:>5.1f}   {p.reasoning}")

def print_results(round_: Round):
    pct = (round_.close_price - round_.open_price) / round_.open_price * 100
    divider()
    print(f"  Close price : ${round_.close_price:>10,.2f}   ({pct:+.3f}%)")
    print(f"  Outcome     : {round_.outcome}")
    divider()
    print(f"  {'AGENT':>14}   {'PRED':4}  {'STAKE':>5}   {'PNL':>7}   RESULT")
    divider()
    for p in round_.predictions:
        sign = "+" if p.pnl >= 0 else ""
        marker = {"WIN": "WIN ", "LOSS": "loss", "VOID": "void"}[p.outcome]
        print(f"  {p.agent_id:>14}   {p.direction:4}  {p.stake:>5.1f}   {sign}{p.pnl:>6.2f}   {marker}")

def print_leaderboard(traders: list):
    divider("═")
    print("  LEADERBOARD")
    divider("═")
    ranked = sorted(traders, key=lambda t: t.wallet_balance, reverse=True)
    print(f"  {'RANK':>4}  {'AGENT':>14}  {'PERSONALITY':>12}  {'BAL':>8}  {'W':>3}  {'L':>3}  {'P':>3}  WIN%")
    divider()
    for i, t in enumerate(ranked, 1):
        winpct = f"{t.win_rate:.0%}" if t.total_rounds > 0 else " —"
        print(
            f"  {i:>4}  {t.agent_id:>14}  {t.personality_name:>12}"
            f"  {t.wallet_balance:>8.2f}  {t.wins:>3}  {t.losses:>3}  {t.pushes:>3}  {winpct:>4}"
        )
    divider("═")

def countdown(seconds: int):
    for remaining in range(seconds, 0, -1):
        mins, secs = divmod(remaining, 60)
        sys.stdout.write(f"\r  Waiting {mins:02d}:{secs:02d} for round to close...")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r" + " " * 50 + "\r")
    sys.stdout.flush()


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    mock_mode = "--mock" in sys.argv
    duration = ROUND_DURATION_SECS
    if mock_mode:
        duration = 0
        print("  [mock mode: deterministic prices and predictions]\n")
    elif "--fast" in sys.argv:
        duration = 30
        print("  [fast mode: 30-second rounds]\n")

    max_rounds = None
    for arg in sys.argv:
        if arg.startswith("--rounds="):
            max_rounds = int(arg.split("=")[1])

    traders = build_traders(mock=mock_mode)
    price_provider = MockPriceFeed() if mock_mode else None
    market = Market(traders, round_duration=duration, price_provider=price_provider)
    round_num = 0

    print("=" * 70)
    mode = "Mock" if mock_mode else "Live"
    print(f"  AGENTEXCHANGE — {mode} ETH Prediction Market")
    print("=" * 70)
    print("  Press Ctrl-C at any time to stop.\n")

    try:
        while max_rounds is None or round_num < max_rounds:
            round_num += 1
            print(f"\n  Round {round_num}")
            divider("═")

            # Open
            print("  Getting mock ETH price..." if mock_mode else "  Fetching live ETH price...")
            try:
                round_ = market.open_round()
            except MarketDataError as exc:
                print(f"  ERROR: {exc}")
                print("  No stakes were collected. Stopping.")
                break
            print(f"  Open price: ${round_.open_price:>10,.2f}\n")

            # Predictions
            print("  Collecting agent predictions...")
            try:
                predictions = market.collect_predictions(round_)
            except APIError as exc:
                print(f"  ERROR: Unable to collect predictions: {exc}")
                print("  No stakes were collected. Stopping.")
                break
            if not predictions:
                print("  No eligible traders produced valid predictions. Stopping.")
                break
            print_predictions(round_)

            # Wait
            print()
            if duration > 0:
                countdown(duration)

            # Close + settle
            print("  Getting mock close price..." if mock_mode else "  Fetching close price...")
            try:
                market.close_round(round_)
            except MarketDataError as exc:
                print(f"  ERROR: {exc}")
                print("  Round voided; all stakes were refunded. Stopping.")
                break
            market.settle(round_)
            print_results(round_)

            # Leaderboard
            print()
            print_leaderboard(traders)
            print()

    except KeyboardInterrupt:
        print("\n\n  Stopped.")

    print_leaderboard(traders)


if __name__ == "__main__":
    main()
