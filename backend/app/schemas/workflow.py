from datetime import datetime

from pydantic import BaseModel


class StatusNode(BaseModel):
    key: str
    label: str
    count: int = 0
    terminal: bool = False


class WorkflowEntity(BaseModel):
    """One state machine: every state it can be in, plus how they connect."""

    key: str
    label: str
    hint: str | None = None
    statuses: list[StatusNode]
    # The happy path, in order. Anything not on it is reached via `branches`.
    main_path: list[str] = []
    branches: list[dict] = []
    # Edges that lead back to the happy path. Without these a diagram reads as
    # a one-way trip - a machine that breaks down and is never repaired.
    returns: list[dict] = []


class FlowStage(BaseModel):
    key: str
    label: str
    detail: str | None = None
    count: int = 0
    unit: str = ""
    secondary: float | None = None
    kind: str = "process"  # store | gate | process | reject


class WorkflowMap(BaseModel):
    generated_at: datetime
    flow: list[FlowStage]
    reject_branch: list[FlowStage]
    entities: list[WorkflowEntity]
