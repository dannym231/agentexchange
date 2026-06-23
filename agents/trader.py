import math

from agents.base import BaseAgent
from core.models import AgentRole, Prediction, MIN_STAKE, MAX_STAKE, credits


TRADER_PERSONALITIES = {
    "momentum": {
        "name": "Momentum",
        "prompt": """You are a Momentum Trader in a crypto prediction market.
Your strategy: follow the trend. If the price has been rising, bet UP. If falling, bet DOWN.
You believe markets trend and that recent price action predicts near-term direction.
You stake aggressively (2.0–4.0 credits) when you see a clear trend, modestly (1.0–1.5) when uncertain.
You almost never pick FLAT — you're always looking for a move to ride.

Given the current ETH price and any recent context, respond ONLY with JSON:
{"direction": "UP" | "DOWN" | "FLAT", "stake": <number>, "reasoning": "<one sentence>"}""",
    },

    "contrarian": {
        "name": "Contrarian",
        "prompt": """You are a Contrarian Trader in a crypto prediction market.
Your strategy: fade the move. If ETH just pumped, you expect a pullback — bet DOWN.
If it just dumped, you expect a bounce — bet UP. You distrust momentum and look for overextension.
You stake heavily (2.5–4.0 credits) when you sense the market is overextended, lighter (1.0–1.5) otherwise.
You pick FLAT only when price action is genuinely directionless.

Given the current ETH price and any recent context, respond ONLY with JSON:
{"direction": "UP" | "DOWN" | "FLAT", "stake": <number>, "reasoning": "<one sentence>"}""",
    },

    "conservative": {
        "name": "Conservative",
        "prompt": """You are a Conservative Trader in a crypto prediction market.
Your strategy: capital preservation. Crypto is volatile and short 5-minute windows are nearly random.
You prefer FLAT whenever the price looks stable. When you do pick a direction, you stake small (0.5–1.5 credits).
You never stake more than 1.5 credits on a single prediction — protecting your bankroll matters more than big wins.
You pick UP or DOWN only when you have a clear, low-risk reason.

Given the current ETH price and any recent context, respond ONLY with JSON:
{"direction": "UP" | "DOWN" | "FLAT", "stake": <number>, "reasoning": "<one sentence>"}""",
    },

    "degen": {
        "name": "Degen",
        "prompt": """You are a Degen Trader in a crypto prediction market.
Your strategy: max size, high conviction, no fear. ETH is volatile — you embrace that.
You almost always pick UP or DOWN (never FLAT — that's for cowards). You stake big: 3.0–5.0 credits per call.
You trust your gut. You love volatility. Losses are just the cost of doing business.
If you're uncertain, you pick a direction anyway and size up — hesitation is weakness.

Given the current ETH price and any recent context, respond ONLY with JSON:
{"direction": "UP" | "DOWN" | "FLAT", "stake": <number>, "reasoning": "<one sentence>"}""",
    },
}


class TraderAgent(BaseAgent):
    def __init__(self, agent_id: str, personality: str, wallet_balance: float = 20.0):
        if personality not in TRADER_PERSONALITIES:
            raise ValueError(f"Unknown personality '{personality}'. Choose from: {list(TRADER_PERSONALITIES)}")
        super().__init__(agent_id, AgentRole.TRADER, wallet_balance)
        self.personality = personality
        self.personality_name = TRADER_PERSONALITIES[personality]["name"]
        self.system_prompt = TRADER_PERSONALITIES[personality]["prompt"]
        self.wins = 0
        self.losses = 0
        self.pushes = 0  # voided/refunded predictions

    def predict(self, current_price: float, context: str = None) -> "Prediction":
        user_msg = f"Current ETH price: ${current_price:,.2f}"
        if context:
            user_msg += f"\n{context}"
        result = self.think_json(self.system_prompt, user_msg)
        direction = result["direction"].upper()
        if direction not in ("UP", "DOWN", "FLAT"):
            direction = "FLAT"
        raw_stake = float(result["stake"])
        if not math.isfinite(raw_stake) or raw_stake <= 0:
            raise ValueError("stake must be finite and positive")
        stake = credits(raw_stake)
        if self.wallet_credits < MIN_STAKE:
            raise ValueError("wallet balance is below the minimum stake")
        stake = min(max(stake, MIN_STAKE), self.wallet_credits, MAX_STAKE)
        return Prediction(
            agent_id=self.agent_id,
            direction=direction,
            stake=stake,
            reasoning=result.get("reasoning", ""),
        )

    @property
    def win_rate(self) -> float:
        total = self.wins + self.losses + self.pushes
        return self.wins / total if total > 0 else 0.0

    @property
    def total_rounds(self) -> int:
        return self.wins + self.losses + self.pushes

    def __repr__(self) -> str:
        return (
            f"[{self.personality_name:>12}] {self.agent_id}"
            f"  balance={self.wallet_balance:>7.2f}"
            f"  W{self.wins}/L{self.losses}/P{self.pushes}"
            f"  ({self.win_rate:.0%} win rate)"
        )


MOCK_PREDICTIONS = {
    "momentum": [("UP", 3.0), ("DOWN", 3.0), ("UP", 3.0)],
    "contrarian": [("DOWN", 2.5), ("UP", 2.5), ("DOWN", 2.5)],
    "conservative": [("FLAT", 0.5), ("FLAT", 0.5), ("FLAT", 0.5)],
    "degen": [("UP", 5.0), ("DOWN", 5.0), ("UP", 5.0)],
}


class MockTraderAgent(TraderAgent):
    """Deterministic trader used by local mock mode without model calls."""

    def __init__(self, agent_id: str, personality: str, wallet_balance: float = 20.0):
        super().__init__(agent_id, personality, wallet_balance)
        self._prediction_index = 0

    def predict(self, current_price: float, context: str = None) -> Prediction:
        choices = MOCK_PREDICTIONS[self.personality]
        direction, requested_stake = choices[self._prediction_index % len(choices)]
        self._prediction_index += 1
        stake = min(credits(requested_stake), self.wallet_credits, MAX_STAKE)
        if stake < MIN_STAKE:
            raise ValueError("wallet balance is below the minimum stake")
        return Prediction(
            agent_id=self.agent_id,
            direction=direction,
            stake=stake,
            reasoning=f"Deterministic {self.personality} mock prediction.",
        )
