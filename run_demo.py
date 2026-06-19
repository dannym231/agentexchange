from agents.orchestrator import OrchestratorAgent
from agents.specialist import SpecialistAgent
from core.models import AgentRole

def main():
    print("=" * 60)
    print("AGENTMARKET — Autonomous Research Negotiation Demo")
    print("=" * 60)

    # Create the orchestrator and one specialist per role
    orchestrator = OrchestratorAgent()
    search_agent = SpecialistAgent("search-01", AgentRole.SEARCH)
    summarizer_agent = SpecialistAgent("summarizer-01", AgentRole.SUMMARIZER)
    factchecker_agent = SpecialistAgent("factchecker-01", AgentRole.FACT_CHECKER)

    specialists_by_role = {
        "search": search_agent,
        "summarizer": summarizer_agent,
        "fact_checker": factchecker_agent,
    }

    query = input("\nEnter a research question: ").strip()
    if not query:
        query = "What are the most promising applications of AI agents in 2026?"
        print(f"(using default: {query})")

    print(f"\n[1] Orchestrator decomposing query into subtasks...")
    tasks = orchestrator.decompose_query(query)

    for i, task in enumerate(tasks, 1):
        print(f"\n--- Subtask {i}/3 ---")
        # crude role match based on task order (search, summarizer, fact_checker)
        role_key = ["search", "summarizer", "fact_checker"][i - 1]
        specialist = specialists_by_role[role_key]

        deal_reached = orchestrator.negotiate(task, specialist)
        if deal_reached:
            orchestrator.execute_and_pay(task, specialist)

    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    for task in tasks:
        print(f"\n[{task.status.value.upper()}] {task.description}")
        if task.result:
            print(task.result[:500])

    print("\n" + "=" * 60)
    print("FINAL WALLET BALANCES")
    print("=" * 60)
    print(orchestrator)
    for s in specialists_by_role.values():
        print(s)

if __name__ == "__main__":
    main()
