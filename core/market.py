from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
import json
import math
import time
from uuid import uuid4

import requests
from core.ledger import NullLedger
from core.models import (
    CREDIT_QUANTUM,
    Direction,
    MIN_STAKE,
    Prediction,
    PredictionState,
    Round,
    RoundState,
    credits,
)
from core.treasury import MarketTreasury

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
FLAT_THRESHOLD_PCT = 0.15
ROUND_DURATION_SECS = 300
PRICE_FETCH_ATTEMPTS = 3
PRICE_RETRY_DELAY_SECS = 1
REPUTATION_EVENT_CATEGORY = "agentexchange.prediction"


class MarketDataError(RuntimeError):
    """Raised when a valid live market price cannot be retrieved."""


class MockPriceFeed:
    """Repeatable three-round UP, DOWN, FLAT price sequence."""

    PRICES = (1000.0, 1002.0, 1002.0, 999.0, 999.0, 1000.0)

    def __init__(self):
        self._index = 0

    def __call__(self) -> float:
        price = self.PRICES[self._index % len(self.PRICES)]
        self._index += 1
        return price


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
    """Pure price classification for a completed round."""
    if not all(math.isfinite(p) and p > 0 for p in (open_price, close_price)):
        raise ValueError("prices must be finite and positive")
    open_decimal = Decimal(str(open_price))
    close_decimal = Decimal(str(close_price))
    pct = (close_decimal - open_decimal) / open_decimal * 100
    threshold = Decimal(str(FLAT_THRESHOLD_PCT))
    if pct > threshold:
        return Direction.UP.value
    if pct < -threshold:
        return Direction.DOWN.value
    return Direction.FLAT.value


@dataclass(frozen=True)
class SettlementLine:
    agent_id: str
    state: PredictionState
    pnl: Decimal
    credit: Decimal


def calculate_settlement(predictions: list[Prediction], outcome: str) -> tuple[SettlementLine, ...]:
    """Pure, zero-sum settlement math. Returned credits are safe to apply once."""
    direction = Direction(outcome).value
    if any(p.state != PredictionState.PENDING for p in predictions):
        raise ValueError("prediction has already been settled")

    winner_indexes = [i for i, p in enumerate(predictions) if p.direction == direction]
    if not winner_indexes:
        return tuple(
            SettlementLine(p.agent_id, PredictionState.VOID, credits(0), p.stake)
            for p in predictions
        )

    losing_pool = sum(
        (p.stake for p in predictions if p.direction != direction), Decimal("0.00")
    )
    winning_total = sum((predictions[i].stake for i in winner_indexes), Decimal("0.00"))

    profits = {i: Decimal("0.00") for i in winner_indexes}
    remainders = []
    allocated = Decimal("0.00")
    for i in winner_indexes:
        exact = predictions[i].stake * losing_pool / winning_total
        rounded_down = exact.quantize(CREDIT_QUANTUM, rounding=ROUND_DOWN)
        profits[i] = rounded_down
        allocated += rounded_down
        remainders.append((exact - rounded_down, i))

    remaining_units = int((losing_pool - allocated) / CREDIT_QUANTUM)
    for _, i in sorted(remainders, key=lambda item: (-item[0], item[1]))[:remaining_units]:
        profits[i] += CREDIT_QUANTUM

    lines = []
    for i, prediction in enumerate(predictions):
        if i in profits:
            profit = profits[i]
            lines.append(
                SettlementLine(
                    prediction.agent_id,
                    PredictionState.WON,
                    profit,
                    prediction.stake + profit,
                )
            )
        else:
            lines.append(
                SettlementLine(
                    prediction.agent_id,
                    PredictionState.LOST,
                    -prediction.stake,
                    Decimal("0.00"),
                )
            )
    return tuple(lines)


def calculate_void(predictions: list[Prediction]) -> tuple[SettlementLine, ...]:
    """Pure refund plan for a round that cannot be settled."""
    if any(p.state != PredictionState.PENDING for p in predictions):
        raise ValueError("prediction has already been settled")
    return tuple(
        SettlementLine(p.agent_id, PredictionState.VOID, credits(0), p.stake)
        for p in predictions
    )


class Market:
    def __init__(
        self,
        traders: list,
        round_duration: int = ROUND_DURATION_SECS,
        price_provider=None,
        treasury=None,
        ledger=None,
        run_id=None,
        price_source=None,
    ):
        self.traders = traders
        self.round_duration = round_duration
        self.price_provider = price_provider or fetch_eth_price
        self.price_source = price_source or self._infer_price_source(price_provider)
        self.treasury = treasury if treasury is not None else MarketTreasury()
        self.ledger = ledger if ledger is not None else NullLedger()
        self.run_id = run_id or uuid4().hex
        self.rounds: list[Round] = []
        self._trader_map = {t.agent_id: t for t in traders}
        self.ledger.record_run(
            run_id=self.run_id,
            price_source=self.price_source,
            round_duration=self.round_duration,
        )

    def open_round(self) -> Round:
        price = self.price_provider()
        round_ = Round(id=len(self.rounds) + 1, open_price=price)
        self.rounds.append(round_)
        self.ledger.record_round(run_id=self.run_id, round_=round_)
        self.ledger.record_price_observation(
            run_id=self.run_id,
            round_id=round_.id,
            kind="open",
            price=price,
            source=self.price_source,
        )
        return round_

    def collect_predictions(self, round_: Round) -> list[Prediction]:
        if round_.state != RoundState.OPEN:
            raise ValueError("predictions can only be collected for an open round")
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
            if trader.wallet_credits < MIN_STAKE:
                continue
            try:
                pred = trader.predict(round_.open_price, context=context)
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                print(f"  WARNING: Skipping {trader.agent_id}: invalid prediction ({exc})")
                continue
            pending_predictions.append((trader, pred))

        for trader, pred in pending_predictions:
            self.treasury.collect(
                trader,
                pred.stake,
                memo=f"AgentExchange round {round_.id} stake",
            )
            round_.predictions.append(pred)

        return round_.predictions

    def close_round(self, round_: Round) -> tuple[float, str]:
        if round_.state != RoundState.OPEN:
            raise ValueError("only an open round can be closed")
        try:
            round_.close_price = self.price_provider()
        except MarketDataError:
            self.void_round(round_)
            raise
        round_.outcome = determine_outcome(round_.open_price, round_.close_price)
        round_.state = RoundState.CLOSED
        self.ledger.update_round(run_id=self.run_id, round_=round_)
        self.ledger.record_price_observation(
            run_id=self.run_id,
            round_id=round_.id,
            kind="close",
            price=round_.close_price,
            source=self.price_source,
        )
        return round_.close_price, round_.outcome

    def void_round(self, round_: Round) -> dict[str, Decimal]:
        if round_.state in (RoundState.SETTLED, RoundState.VOID):
            raise ValueError("round has already been settled")
        lines = calculate_void(round_.predictions)
        self._apply(round_, lines, RoundState.VOID)
        self.ledger.update_round(run_id=self.run_id, round_=round_)
        return {line.agent_id: line.pnl for line in lines}

    def settle(self, round_: Round) -> dict[str, Decimal]:
        if round_.state != RoundState.CLOSED or round_.outcome is None:
            raise ValueError("only a closed round can be settled")
        lines = calculate_settlement(round_.predictions, round_.outcome)
        final_state = RoundState.VOID if not lines or all(
            line.state == PredictionState.VOID for line in lines
        ) else RoundState.SETTLED
        self._apply(round_, lines, final_state)
        self.ledger.update_round(run_id=self.run_id, round_=round_)
        return {line.agent_id: line.pnl for line in lines}

    def _infer_price_source(self, price_provider) -> str:
        return "mock" if isinstance(price_provider, MockPriceFeed) else "coingecko"

    def _apply(self, round_: Round, lines: tuple[SettlementLine, ...], state: RoundState) -> None:
        if len(lines) != len(round_.predictions):
            raise ValueError("invalid settlement plan")
        if any(p.agent_id not in self._trader_map for p in round_.predictions):
            raise ValueError("settlement references an unknown trader")
        for prediction, line in zip(round_.predictions, lines):
            trader = self._trader_map[prediction.agent_id]
            if line.credit > 0:
                self.treasury.pay(
                    trader,
                    line.credit,
                    memo=f"AgentExchange round {round_.id} {line.state.value.lower()}",
                )
            prediction.mark(line.state, line.pnl)
            if line.state == PredictionState.WON:
                trader.wins += 1
            elif line.state == PredictionState.LOST:
                trader.losses += 1
            else:
                trader.pushes += 1
            self._record_reputation_event(round_, trader, prediction, line)
        round_.state = state

    def _record_reputation_event(self, round_: Round, trader, prediction: Prediction, line: SettlementLine) -> None:
        result_by_state = {
            PredictionState.WON: "win",
            PredictionState.LOST: "loss",
            PredictionState.VOID: "void",
        }
        details = json.dumps(
            {
                "round_id": round_.id,
                "prediction_direction": prediction.direction,
                "actual_outcome": round_.outcome,
                "stake": str(prediction.stake),
                "pnl": str(prediction.pnl),
                "result": result_by_state[line.state],
                "wallet_balance_after": str(trader.wallet_credits),
            },
            separators=(",", ":"),
        )
        if line.state == PredictionState.WON:
            trader.cred.reputation.record_completed(REPUTATION_EVENT_CATEGORY, details=details)
        elif line.state == PredictionState.LOST:
            trader.cred.reputation.record_failed(REPUTATION_EVENT_CATEGORY, details=details)
        else:
            trader.cred.reputation.record_void(REPUTATION_EVENT_CATEGORY, details=details)
