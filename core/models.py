from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import time
import uuid


class TaskStatus(Enum):
    OPEN = "open"
    BIDDING = "bidding"
    NEGOTIATING = "negotiating"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRole(Enum):
    ORCHESTRATOR = "orchestrator"
    SEARCH = "search"
    SUMMARIZER = "summarizer"
    FACT_CHECKER = "fact_checker"


@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    max_budget: float = 0.0
    status: TaskStatus = TaskStatus.OPEN
    assigned_to: Optional[str] = None
    final_price: Optional[float] = None
    result: Optional[str] = None
    context: Optional[str] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class Bid:
    agent_id: str
    task_id: str
    price: float
    reasoning: str
    round: int = 1


@dataclass
class NegotiationMessage:
    sender_id: str
    receiver_id: str
    task_id: str
    message_type: str
    price: Optional[float]
    content: str
    round: int
    timestamp: float = field(default_factory=time.time)
