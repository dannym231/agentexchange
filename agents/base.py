import os
import json
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


class BaseAgent:
    def __init__(self, agent_id: str, role, wallet_balance: float = 10.0):
        self.agent_id = agent_id
        self.role = role
        self.wallet_balance = wallet_balance
        self.conversation_history = []

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

    def think_with_tools(self, system_prompt: str, user_message: str, tools: list) -> str:
        """Run a request with server-side tools, looping on pause_turn."""
        messages = [{"role": "user", "content": user_message}]
        response = None
        for _ in range(5):
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "pause_turn":
                break
        if response is None:
            return ""
        return " ".join(b.text for b in response.content if b.type == "text")

    def think_json(self, system_prompt: str, user_message: str) -> dict:
        raw = self.think(system_prompt, user_message).strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    def debit(self, amount: float):
        self.wallet_balance -= amount

    def credit(self, amount: float):
        self.wallet_balance += amount

    def __repr__(self):
        return f"[{self.role.value.upper()} {self.agent_id}] balance={self.wallet_balance:.2f}"
