from __future__ import annotations

from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Policy(StrEnum):
    SAFE_GENERAL = "SAFE_GENERAL"
    SAFE_WITH_POLICY = "SAFE_WITH_POLICY"
    STAFF_APPROVAL = "STAFF_APPROVAL"
    TELEOP_ONLY = "TELEOP_ONLY"
    CLINICAL_PROHIBITED = "CLINICAL_PROHIBITED"
    UNKNOWN_PROHIBITED = "UNKNOWN_PROHIBITED"


class Pose(StrictModel):
    x: float
    y: float
    z: float


class Step(StrictModel):
    id: str
    action: Literal["place_in_zone", "observe", "abstain"]
    object_id: str
    target_zone: str
    target_pose: Pose
    skill_id: str
    execution_type: Literal["DETERMINISTIC", "BOUNDED_VLA", "SUPERVISED_VLA", "TELEOPERATION", "OBSERVE_ONLY", "BLOCKED"]


class TaskProposal(StrictModel):
    intent: str
    target_outcome: str
    patient_context_allowed: bool
    current_room_state_id: str
    desired_room_state: str
    candidate_steps: list[Step]
    affected_objects: list[str]
    assumptions: list[str]
    uncertainties: list[str]
    required_skills: list[str]
    prohibited_interactions: list[str]
    human_approval_required: bool
    success_criteria: list[str]


class Critique(StrictModel):
    verdict: Literal["accept_candidate", "revise", "reject"]
    reasons: list[str]
    hidden_assumptions: list[str]
    clinical_boundary_violation: bool
    human_first_alternative: str
    solves_original_intent: bool


class RequestInput(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    room_id: str = "room-417"


class PlanInput(StrictModel):
    room_id: str = "room-417"
    goal: str = Field(min_length=1, max_length=1000)
    template: str | None = None
    object_id: str | None = None


class SceneInterpretation(StrictModel):
    archetype: str
    object_classes: list[str]
    relationships: list[str]
    uncertainties: list[str]
    metric_geometry_verified: Literal[False]

