import os
import json
from anthropic import Anthropic
from agentcred import AgentCredAgent
from dotenv import load_dotenv
from core.models import credits

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


class BaseAgent:
    def __init__(self, agent_id: str, role, wallet_balance: float = 10.0):
        wallet_balance = credits(wallet_balance)
        if wallet_balance < 0:
            raise ValueError("wallet balance must be finite and non-negative")
        self._agent_id = agent_id
        self.cred = AgentCredAgent(agent_id, initial_balance=wallet_balance)
        self.role = role
        self.conversation_history = []

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def think(self, system_prompt: str, user_message: str) -> str:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=self.conversation_history + [{"role": "user", "content": user_message}],
        )
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": response.content})
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

    def think_json(self, system_prompt: str, user_message: str) -> dict:
        raw = self.think(system_prompt, user_message).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    def debit(self, amount, recipient_wallet=None, memo=None):
        """Compatibility transfer to an explicit market or treasury wallet."""
        amount = credits(amount)
        if amount <= 0:
            raise ValueError("debit amount must be finite and positive")
        if amount > self.wallet_credits:
            raise ValueError("debit amount exceeds wallet balance")
        if recipient_wallet is None:
            raise ValueError("recipient wallet is required for debit")
        return self.cred.wallet.send(recipient_wallet, amount, memo=memo)

    def credit(self, amount, source_wallet=None, memo=None):
        """Compatibility transfer from an explicit market or treasury wallet."""
        amount = credits(amount)
        if amount <= 0:
            raise ValueError("credit amount must be finite and positive")
        if source_wallet is None:
            raise ValueError("source wallet is required for credit")
        return source_wallet.send(self.cred.wallet, amount, memo=memo)

    @property
    def wallet_balance(self) -> float:
        """Backward-compatible display/API value; arithmetic uses wallet_credits."""
        return float(self.wallet_credits)

    @property
    def wallet_credits(self):
        return credits(self.cred.wallet.balance)

    def __repr__(self):
        return f"[{self.role.value.upper()} {self.agent_id}] balance={self.wallet_balance:.2f}"
