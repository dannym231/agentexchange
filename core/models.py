from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import time

MIN_STAKE = 0.5
MAX_STAKE = 5.0


class AgentRole(Enum):
    TRADER = "trader"


@dataclass
class Prediction:
    agent_id: str
    direction: str       # "UP", "DOWN", or "FLAT"
    stake: float
    reasoning: str
    outcome: Optional[str] = None   # filled in after settlement
    pnl: Optional[float] = None     # credits won (+) or lost (-)


@dataclass
class Round:
    id: int
    open_price: float
    close_price: Optional[float] = None
    outcome: Optional[str] = None   # "UP", "DOWN", or "FLAT"
    predictions: list = None
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.predictions is None:
            self.predictions = []
