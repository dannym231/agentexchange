from agentcred import AgentCredAgent
from uuid import uuid4

from core.models import credits


class MarketTreasury:
    """Market-owned wallet that holds stakes until settlement or refund."""

    def __init__(self, treasury_id=None):
        treasury_id = treasury_id or f"agentexchange-market-treasury-{uuid4().hex}"
        self.cred = AgentCredAgent(treasury_id, initial_balance=0)

    @property
    def wallet_credits(self):
        return credits(self.cred.wallet.balance)

    def collect(self, trader, amount, memo=None):
        amount = credits(amount)
        if amount <= 0:
            raise ValueError("collection amount must be finite and positive")
        return trader.cred.wallet.send(self.cred.wallet, amount, memo=memo)

    def pay(self, trader, amount, memo=None):
        amount = credits(amount)
        if amount <= 0:
            raise ValueError("payment amount must be finite and positive")
        return self.cred.wallet.send(trader.cred.wallet, amount, memo=memo)
