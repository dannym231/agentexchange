import math
import time

import requests
from core.models import Round, Prediction, MIN_STAKE

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
FLAT_THRESHOLD_PCT = 0.15   # moves smaller than this % count as FLAT
ROUND_DURATION_SECS = 300   # 5 minutes
PRICE_FETCH_ATTEMPTS = 3
PRICE_RETRY_DELAY_SECS = 1


class MarketDataError(RuntimeError):
    """Raised when a valid live market price cannot be retrieved."""


def fetch_eth_price() -> float:
    last_error = None
    for attempt in range(PRICE_FETCH_ATTEMPTS):
        try:
            resp = requests.get(COINGECKO_URL, timeout=10)
            resp.raise_for_status()
            price = float(resp.json()["ethereum"]["usd"])
            if not math.isfinite(price) or price <= 0:
                raise ValueError("price must be finite and positive")
            return price
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            last_error = exc
            if attempt < PRICE_FETCH_ATTEMPTS - 1:
                time.sleep(PRICE_RETRY_DELAY_SECS * (2 ** attempt))

    raise MarketDataError(f"Unable to fetch a valid ETH price from CoinGecko: {last_error}") from None


def determine_outcome(open_price: float, close_price: float) -> str:
    pct = (close_price - open_price) / open_price * 100
    if pct > FLAT_THRESHOLD_PCT:
        return "UP"
    elif pct < -FLAT_THRESHOLD_PCT:
        return "DOWN"
    return "FLAT"


class Market:
    def __init__(self, traders: list, round_duration: int = ROUND_DURATION_SECS):
        self.traders = traders
        self.round_duration = round_duration
        self.rounds: list[Round] = []
        self._trader_map = {t.agent_id: t for t in traders}

    def open_round(self) -> Round:
        price = fetch_eth_price()
        round_ = Round(id=len(self.rounds) + 1, open_price=price)
        self.rounds.append(round_)
        return round_

    def collect_predictions(self, round_: Round) -> list[Prediction]:
        # Pass last round's result as context so agents can reason about recent moves
        context = None
        if len(self.rounds) >= 2:
            prev = self.rounds[-2]
            pct = (prev.close_price - prev.open_price) / prev.open_price * 100
            context = (
                f"Last round: ETH went from ${prev.open_price:,.2f} to ${prev.close_price:,.2f} "
                f"({pct:+.2f}%) — outcome was {prev.outcome}."
            )

        pending_predictions = []
        for trader in self.traders:
            if trader.wallet_balance < MIN_STAKE:
                continue
            try:
                pred = trader.predict(round_.open_price, context=context)
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                print(f"  WARNING: Skipping {trader.agent_id}: invalid prediction ({exc})")
                continue
            pending_predictions.append((trader, pred))

        for trader, pred in pending_predictions:
            trader.debit(pred.stake)
            round_.predictions.append(pred)

        return round_.predictions

    def close_round(self, round_: Round) -> tuple[float, str]:
        try:
            round_.close_price = fetch_eth_price()
        except MarketDataError:
            self.void_round(round_)
            raise
        round_.outcome = determine_outcome(round_.open_price, round_.close_price)
        return round_.close_price, round_.outcome

    def void_round(self, round_: Round) -> dict[str, float]:
        """Refund every unsettled prediction and record the round as a void."""
        pnl = {}
        for p in round_.predictions:
            if p.outcome is not None:
                raise ValueError("round has already been settled")
            trader = self._trader_map[p.agent_id]
            trader.credit(p.stake)
            trader.pushes += 1
            p.pnl = 0.0
            p.outcome = "VOID"
            pnl[p.agent_id] = 0.0
        return pnl

    def settle(self, round_: Round) -> dict[str, float]:
        """Zero-sum pool: losers' stakes are split among winners proportionally."""
        winners = [p for p in round_.predictions if p.direction == round_.outcome]
        losers  = [p for p in round_.predictions if p.direction != round_.outcome]

        losing_pool   = sum(p.stake for p in losers)
        winning_total = sum(p.stake for p in winners)

        if any(p.outcome is not None for p in round_.predictions):
            raise ValueError("round has already been settled")
        if not winners:
            return self.void_round(round_)

        pnl = {}
        for p in round_.predictions:
            trader = self._trader_map[p.agent_id]
            if p.direction == round_.outcome:
                profit = p.stake / winning_total * losing_pool
                p.pnl = profit
                p.outcome = "WIN"
                trader.credit(p.stake + profit)  # return stake + winnings
                trader.wins += 1
            else:
                p.pnl = -p.stake
                p.outcome = "LOSS"
                # stake was already debited at prediction time; nothing to credit back
                trader.losses += 1
            pnl[p.agent_id] = p.pnl

        return pnl
