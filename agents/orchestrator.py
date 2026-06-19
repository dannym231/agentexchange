import json
from agents.base import BaseAgent
from agents.specialist import SpecialistAgent
from core.models import AgentRole, Task, TaskStatus

ORCHESTRATOR_PROMPT = """You are the Orchestrator Agent in an AI research marketplace.
You receive a research question and break it into exactly 3 subtasks for these specialists:
1. SEARCH - find relevant information on the web
2. SUMMARIZER - condense findings into a clear summary
3. FACT_CHECKER - verify key claims

Respond ONLY with JSON in this exact format:
{
  "subtasks": [
    {"role": "search", "description": "<specific task>", "max_budget": <number>},
    {"role": "summarizer", "description": "<specific task>", "max_budget": <number>},
    {"role": "fact_checker", "description": "<specific task>", "max_budget": <number>}
  ]
}
Budgets should be between 1.0 and 4.0 credits each, based on task complexity."""


class OrchestratorAgent(BaseAgent):
    def __init__(self, agent_id: str = "orchestrator-01", wallet_balance: float = 20.0):
        super().__init__(agent_id, AgentRole.ORCHESTRATOR, wallet_balance)

    def decompose_query(self, user_query: str) -> list[Task]:
        result = self.think_json(ORCHESTRATOR_PROMPT, f"Research question: {user_query}")
        tasks = []
        for sub in result["subtasks"]:
            tasks.append(Task(
                description=sub["description"],
                max_budget=float(sub["max_budget"]),
                status=TaskStatus.OPEN
            ))
        return tasks

    def negotiate(self, task: Task, specialist: SpecialistAgent, max_rounds: int = 3) -> bool:
        """Run a negotiation loop between orchestrator and one specialist. Returns True if deal reached."""
        print(f"\n  Negotiating task with {specialist.agent_id} (budget: {task.max_budget:.2f})")
        print(f"  Task: {task.description}")

        for round_num in range(1, max_rounds + 1):
            bid = specialist.submit_bid(task.description, round_num)
            print(f"  Round {round_num}: {specialist.agent_id} bids {bid.price:.2f} — \"{bid.reasoning}\"")

            if bid.price <= task.max_budget:
                task.assigned_to = specialist.agent_id
                task.final_price = bid.price
                task.status = TaskStatus.ACCEPTED
                print(f"  ACCEPTED at {bid.price:.2f} credits")
                return True
            else:
                print(f"  Over budget ({task.max_budget:.2f}), requesting better offer...")

        print(f"  FAILED to reach a deal after {max_rounds} rounds")
        task.status = TaskStatus.FAILED
        return False

    def execute_and_pay(self, task: Task, specialist: SpecialistAgent):
        """Specialist does the work, orchestrator pays them."""
        result = specialist.execute_task(task.description)
        task.result = result
        task.status = TaskStatus.COMPLETED

        self.debit(task.final_price)
        specialist.credit(task.final_price)
        print(f"  PAID {task.final_price:.2f} credits to {specialist.agent_id}")
        print(f"  {self.agent_id} balance: {self.wallet_balance:.2f} | {specialist.agent_id} balance: {specialist.wallet_balance:.2f}")
