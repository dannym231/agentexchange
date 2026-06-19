from agents.base import BaseAgent
from core.models import AgentRole, Bid


SPECIALIST_PROMPTS = {
    AgentRole.SEARCH: """You are a Search Agent in an AI agent marketplace.
You find information on the web for a fee. You are efficient and fairly priced.
When given a task, respond ONLY with JSON: {"price": <number>, "reasoning": "<short reason>"}
Price in range 0.5 to 3.0 credits depending on task complexity.""",

    AgentRole.SUMMARIZER: """You are a Summarizer Agent in an AI agent marketplace.
You condense research findings into clear summaries for a fee.
When given a task, respond ONLY with JSON: {"price": <number>, "reasoning": "<short reason>"}
Price in range 0.5 to 2.5 credits depending on task complexity.""",

    AgentRole.FACT_CHECKER: """You are a Fact-Checker Agent in an AI agent marketplace.
You verify claims and flag inaccuracies for a fee.
When given a task, respond ONLY with JSON: {"price": <number>, "reasoning": "<short reason>"}
Price in range 0.5 to 2.0 credits depending on task complexity.""",
}


class SpecialistAgent(BaseAgent):
    def __init__(self, agent_id: str, role: AgentRole, wallet_balance: float = 10.0):
        super().__init__(agent_id, role, wallet_balance)
        self.system_prompt = SPECIALIST_PROMPTS[role]

    def submit_bid(self, task_description: str, round_num: int = 1, feedback: str = None) -> Bid:
        user_msg = f"Task: {task_description}\nSubmit your bid for this task (round {round_num})."
        if feedback:
            user_msg += f"\n\nFeedback from previous round: {feedback}"
        result = self.think_json(self.system_prompt, user_msg)
        return Bid(
            agent_id=self.agent_id,
            task_id="",
            price=float(result["price"]),
            reasoning=result["reasoning"],
            round=round_num
        )

    def execute_task(self, task_description: str, context: str = None) -> str:
        """Actually perform the work this agent was hired for."""
        user_msg = task_description
        if context:
            user_msg = f"Context from previous step:\n{context}\n\nTask: {task_description}"
        return self.think(
            f"You are a {self.role.value} agent. Complete the task thoroughly and concisely.",
            user_msg
        )
