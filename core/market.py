import requests
from core.models import Round, Prediction

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
FLAT_THRESHOLD_PCT = 0.15   # moves smaller than this % count as FLAT
ROUND_DURATION_SECS = 300   # 5 minutes


def fetch_eth_price() -> float:
    resp = requests.get(COINGECKO_URL, timeout=10)
    resp.raise_for_status()
    return float(resp.json()["ethereum"]["usd"])


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

        for trader in self.traders:
            pred = trader.predict(round_.open_price, context=context)
            trader.debit(pred.stake)
            round_.predictions.append(pred)

        return round_.predictions

    def close_round(self, round_: Round) -> tuple[float, str]:
        round_.close_price = fetch_eth_price()
        round_.outcome = determine_outcome(round_.open_price, round_.close_price)
        return round_.close_price, round_.outcome

    def settle(self, round_: Round) -> dict[str, float]:
        """Zero-sum pool: losers' stakes are split among winners proportionally."""
        winners = [p for p in round_.predictions if p.direction == round_.outcome]
        losers  = [p for p in round_.predictions if p.direction != round_.outcome]

        losing_pool   = sum(p.stake for p in losers)
        winning_total = sum(p.stake for p in winners)

        pnl = {}
        for p in round_.predictions:
            trader = self._trader_map[p.agent_id]
            if p.direction == round_.outcome:
                profit = (p.stake / winning_total * losing_pool) if winning_total > 0 else 0.0
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
