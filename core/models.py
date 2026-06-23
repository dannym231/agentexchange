from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Optional
import time


CREDIT_QUANTUM = Decimal("0.01")
MIN_STAKE = Decimal("0.50")
MAX_STAKE = Decimal("5.00")


def credits(value) -> Decimal:
    """Convert a numeric value to fixed-precision credits."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("credit amount must be numeric") from None
    if not amount.is_finite():
        raise ValueError("credit amount must be finite")
    try:
        return amount.quantize(CREDIT_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError("credit amount is outside the supported range") from None


class AgentRole(str, Enum):
    TRADER = "trader"


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"


class PredictionState(str, Enum):
    PENDING = "PENDING"
    WON = "WIN"
    LOST = "LOSS"
    VOID = "VOID"


class RoundState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    SETTLED = "SETTLED"
    VOID = "VOID"


@dataclass
class Prediction:
    agent_id: str
    direction: str
    stake: Decimal
    reasoning: str
    outcome: Optional[str] = None
    pnl: Optional[Decimal] = None
    state: PredictionState = PredictionState.PENDING

    def __post_init__(self):
        self.state = PredictionState(self.state)
        self.direction = Direction(self.direction).value
        self.stake = credits(self.stake)
        if self.stake <= 0:
            raise ValueError("stake must be positive")
        if self.outcome is not None:
            self.state = PredictionState(self.outcome)
        elif self.state != PredictionState.PENDING:
            self.outcome = self.state.value
        if self.pnl is not None:
            self.pnl = credits(self.pnl)

    def mark(self, state: PredictionState, pnl) -> None:
        self.state = state
        self.outcome = state.value
        self.pnl = credits(pnl)


@dataclass
class Round:
    id: int
    open_price: float
    close_price: Optional[float] = None
    outcome: Optional[str] = None
    predictions: list[Prediction] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    state: RoundState = RoundState.OPEN

    def __post_init__(self):
        self.state = RoundState(self.state)
        if self.outcome is not None:
            self.outcome = Direction(self.outcome).value
            if self.state == RoundState.OPEN:
                self.state = RoundState.CLOSED
