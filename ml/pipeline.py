"""Local, versioned teleoperation and policy lifecycle.

Quest/Bracket Bot transport and production action semantics remain unavailable.
No method connects to hardware. The tiny learned policy is state-feature behavior
cloning, not a pretrained VLA or evidence of autonomous hospital manipulation.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from sim.engine import ABSTENTION_CASES, abstention_gate, run_benchmark


def now():
    return datetime.now(timezone.utc).isoformat()


class StreamReference(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    timestamp_s: float = Field(ge=0)
    uri: str = Field(min_length=1, max_length=500)
    sha256: str | None = None
    synthetic: bool = True


class TeleopFrame(BaseModel):
    """Synchronized SI-unit research contract; never a vendor control schema."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    timestamp_s: float = Field(ge=0)
    head_rgb: StreamReference
    head_depth: StreamReference
    left_wrist_rgb: StreamReference
    right_wrist_rgb: StreamReference
    base_pose: list[float] = Field(min_length=3, max_length=3)
    base_velocity: list[float] = Field(min_length=3, max_length=3)
    localization_confidence: float = Field(ge=0, le=1)
    left_arm_q: list[float] = Field(min_length=7, max_length=7)
    left_arm_qd: list[float] = Field(min_length=7, max_length=7)
    right_arm_q: list[float] = Field(min_length=7, max_length=7)
    right_arm_qd: list[float] = Field(min_length=7, max_length=7)
    vertical_stage_state: list[float] = Field(min_length=2, max_length=2)
    gripper_state: list[float] = Field(min_length=2, max_length=2)
    action_schema: Literal["surrogate_delta_xyz_v1"] = "surrogate_delta_xyz_v1"
    actions: list[float] = Field(min_length=3, max_length=3)
    state_features: list[float] = Field(min_length=3, max_length=3)
    intervention: bool = False
    failure_category: str | None = None
    safety_events: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def synchronized_and_bounded(self):
        for name in ("head_rgb", "head_depth", "left_wrist_rgb", "right_wrist_rgb"):
            if abs(getattr(self, name).timestamp_s-self.timestamp_s) > .03:
                raise ValueError("Sensor skew exceeds the 30 ms synthetic dataset contract")
        if max(map(abs, self.actions)) > .020001:
            raise ValueError("Action exceeds the 2 cm synthetic action envelope")
        if not all(math.isfinite(v) for key, values in self.model_dump().items() if isinstance(values, list) and key not in {"safety_events"} for v in values):
            raise ValueError("All numeric observation/action values must be finite")
        return self


BENCHMARKS = [
    ("A", "cluttered_retrieval", "Cluttered personal-item retrieval", ["phone", "glasses_case", "remote", "small_bag"], "TELEOPERATION"),
    ("B", "drawer_family", "Approved drawer and handle family", ["safe_drawer"], "TELEOPERATION"),
    ("C", "bimanual_bag", "Bimanual bag stabilization", ["clean_bag"], "TELEOPERATION"),
    ("D", "clean_fabric", "Clean fabric on an empty surface", ["clean_fabric"], "OBSERVE_ONLY"),
    ("E", "room_reset", "Restore allowlisted room objects", ["phone", "remote", "visitor_chair_proxy"], "DETERMINISTIC"),
    ("F", "abstention", "Unknown, prohibited and out-of-distribution abstention", [], "DETERMINISTIC"),
]


def list_skills():
    return [{"id": ident, "benchmark": code, "name": name, "version": "0.1.0", "execution_type": mode, "observation_schema": "synchronized_multiview_proprioception_v1", "action_schema": "vendor_unknown; surrogate_delta_xyz_v1 for synthetic research only", "training_dataset": None, "training_environment": "mock_room_only", "object_classes": classes, "environmental_constraints": {"no_patients": True, "approved_mock_room": True}, "patient_distance_constraints": {"live_patient_execution": "blocked"}, "validated_distribution": [], "success_rate": None, "intervention_rate": None, "collision_rate": None, "unsafe_attempt_rate": None, "abstention_rate": None, "sim_results": None, "real_results": None, "approval_status": "research_definition_only", "rollback_version": None} for code, ident, name, classes, mode in BENCHMARKS]


class LearningPipeline:
    def __init__(self, root_dir: Path | str = "data/runtime/learning"):
        self.root = Path(root_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "registry.json"
        self.lock = threading.RLock()
        if self.path.exists():
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.state = {"sessions": {}, "policies": {}, "events": [], "active_policy": None}
            self._save()

    def _save(self):
        staging = self.path.with_suffix(".tmp")
        staging.write_text(json.dumps(self.state, indent=2, allow_nan=False), encoding="utf-8")
        staging.replace(self.path)

    def _event(self, action, entity, **details):
        self.state["events"].append({"id": uuid.uuid4().hex, "at": now(), "action": action, "entity_id": entity, **details})
        self._save()

    def _session(self, ident):
        if ident not in self.state["sessions"]:
            raise KeyError("Unknown teleoperation session")
        return self.state["sessions"][ident]

    def _policy(self, ident):
        if ident not in self.state["policies"]:
            raise KeyError("Unknown policy")
        return self.state["policies"][ident]

    def list_skills(self):
        return list_skills()

    def list_sessions(self):
        with self.lock:
            return [self.get_session(ident) for ident in self.state["sessions"]]

    def get_session(self, ident):
        with self.lock:
            session = copy.deepcopy(self._session(ident))
            session["frame_count"] = len(session.pop("frames"))
            session["hardware_connected"] = False
            return session

    def create_session(self, payload):
        with self.lock:
            environment = payload.get("environment", "synthetic_mock_room")
            if environment not in {"synthetic_mock_room", "simulation", "approved_mock_room"}:
                raise ValueError("Only synthetic/approved mock environments are supported; live patient capture is blocked")
            if payload.get("consent") is not True:
                raise ValueError("Explicit recording consent is required")
            if payload.get("contains_patient_data", False):
                raise ValueError("Patient data cannot enter this learning pipeline")
            instruction = payload.get("instruction", payload.get("task_text", ""))
            if not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= 500:
                raise ValueError("A nonempty instruction of at most 500 characters is required")
            ident = "episode_"+uuid.uuid4().hex[:12]
            session = {"id": ident, "episode_id": ident, "task_id": payload.get("task_id"), "task_class": payload.get("task_class", "cluttered_retrieval"), "policy_version": payload.get("policy_version"), "robot_revision": "surrogate_v1", "instruction": instruction.strip(), "operator_id": payload.get("operator_id", "local_research_operator"), "environment": environment, "environment_metadata": payload.get("environment_metadata", {}), "status": "created", "created_at": now(), "privacy_status": "quarantined", "redaction_status": "pending_review", "consent": True, "frames": [], "labels": None, "takeover_reason": payload.get("takeover_reason"), "transport": "local_recording_contract; Quest transport not connected"}
            self.state["sessions"][ident] = session
            self._event("session_created", ident)
            return self.get_session(ident)

    def start_session(self, ident):
        with self.lock:
            session = self._session(ident)
            if session["status"] != "created":
                raise ValueError("Session can only start once, from created")
            session.update(status="recording", started_at=now())
            self._event("recording_started", ident, robot_stopped=True, hardware_connected=False)
            return self.get_session(ident)

    def record_frame(self, ident, payload):
        frame = TeleopFrame.model_validate(payload).model_dump()
        with self.lock:
            session = self._session(ident)
            if session["status"] != "recording":
                raise ValueError("Session is not recording")
            if len(session["frames"]) >= 10000:
                raise ValueError("Local episode frame budget exceeded")
            if session["frames"] and frame["timestamp_s"] <= session["frames"][-1]["timestamp_s"]:
                raise ValueError("Frame timestamps must be strictly increasing")
            # Media URIs are opaque references; no network fetch and no raw media copy.
            for name in ("head_rgb", "head_depth", "left_wrist_rgb", "right_wrist_rgb"):
                stream = frame[name]
                if session["environment"] in {"simulation", "synthetic_mock_room"} and not stream["synthetic"]:
                    raise ValueError("Synthetic sessions cannot contain real imagery")
            session["frames"].append(frame)
            self._event("frame_recorded", ident, timestamp_s=frame["timestamp_s"], intervention=frame["intervention"])
            return {"session_id": ident, "frame_count": len(session["frames"]), "timestamp_s": frame["timestamp_s"]}

    def stop_session(self, ident):
        with self.lock:
            session = self._session(ident)
            if session["status"] != "recording":
                raise ValueError("Only a recording session can stop")
            session.update(status="stopped", stopped_at=now())
            self._event("recording_stopped", ident)
            return self.get_session(ident)

    def label_session(self, ident, payload):
        with self.lock:
            session = self._session(ident)
            if session["status"] != "stopped":
                raise ValueError("Stop the session before labeling; reviewed data is immutable")
            if type(payload.get("success")) is not bool:
                raise ValueError("An explicit boolean success label is required")
            category = payload.get("failure_category")
            if not payload["success"] and not category:
                raise ValueError("Failure/abstention episodes require a failure category")
            session["labels"] = {"success": payload["success"], "failure_category": category, "correction_notes": str(payload.get("correction_notes", ""))[:1000], "intervention_count": sum(f["intervention"] for f in session["frames"])}
            self._event("episode_labeled", ident)
            return self.get_session(ident)

    def review_session(self, ident, payload):
        with self.lock:
            session = self._session(ident)
            if session["status"] != "stopped" or not session["labels"] or not session["frames"]:
                raise ValueError("Review requires stopped, nonempty, labeled data")
            approved = payload.get("approved") is True
            if approved and (payload.get("privacy_cleared") is not True or payload.get("safety_cleared") is not True or not payload.get("reviewer_id")):
                raise ValueError("Named reviewer plus explicit privacy and safety clearance are required")
            session.update(status="reviewed" if approved else "rejected", privacy_status="cleared_synthetic" if approved and session["environment"] != "approved_mock_room" else ("cleared_mock" if approved else "quarantined"), redaction_status="reviewed", review={"reviewer_id": payload.get("reviewer_id"), "at": now(), "approved": approved})
            self._event("episode_reviewed", ident, approved=approved)
            return self.get_session(ident)

    def export_dataset(self, session_ids, reviewer_id, export_approved=False):
        if export_approved is not True or not reviewer_id:
            raise ValueError("Dataset export requires explicit human approval and reviewer identity")
        with self.lock:
            sessions = [self._session(i) for i in session_ids]
            if not sessions or any(s["status"] != "reviewed" for s in sessions):
                raise ValueError("Only reviewed episodes can be exported")
            dataset_id = "dataset_"+uuid.uuid4().hex[:12]
            path = self.root / f"{dataset_id}.jsonl"
            with path.open("w", encoding="utf-8") as stream:
                for session in sessions:
                    stream.write(json.dumps(session, allow_nan=False)+"\n")
            self._event("dataset_exported", dataset_id, reviewer_id=reviewer_id, session_ids=session_ids)
            return {"id": dataset_id, "path": str(path), "episode_count": len(sessions), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def list_policies(self):
        with self.lock:
            return copy.deepcopy(list(self.state["policies"].values()))

    def get_policy(self, ident):
        with self.lock:
            return copy.deepcopy(self._policy(ident))

    def register_policy(self, payload):
        with self.lock:
            ident = "policy_"+uuid.uuid4().hex[:12]
            task = payload.get("task_class", "cluttered_retrieval")
            if task not in {b[1] for b in BENCHMARKS}:
                raise ValueError("Unknown research task class")
            policy = {"id": ident, "name": str(payload.get("name", "Research candidate"))[:100], "version": str(payload.get("version", "0.1.0"))[:40], "task_class": task, "status": "draft", "approval_status": "draft", "execution_type": "BOUNDED_VLA_RESEARCH", "observation_schema": "synchronized_multiview_proprioception_v1", "action_schema": "vendor_unknown", "training_dataset": None, "training_environment": None, "object_classes": list(next(b[3] for b in BENCHMARKS if b[1] == task)), "environmental_constraints": {"synthetic_only": True, "no_patients": True}, "patient_distance_constraints": {"minimum_synthetic_clearance_m": .75}, "validated_distribution": [], "success_rate": None, "intervention_rate": None, "collision_rate": None, "unsafe_attempt_rate": None, "abstention_rate": None, "sim_results": None, "real_results": None, "evaluation": None, "artifact": None, "rollback_version": None, "created_at": now(), "hardware_approved": False}
            self.state["policies"][ident] = policy
            self._event("policy_registered", ident)
            return self.get_policy(ident)

    def train_policy(self, payload):
        """Fit an actual ridge BC model from reviewed synthetic episode actions."""
        session_ids = payload.get("session_ids", [])
        with self.lock:
            sessions = [self._session(i) for i in session_ids]
            if len(sessions) < 3 or len(set(session_ids)) != len(session_ids) or any(s["status"] != "reviewed" or s["environment"] not in {"synthetic_mock_room", "simulation"} for s in sessions):
                raise ValueError("Tiny training requires at least three distinct reviewed synthetic episodes")
            # Episode-level split prevents adjacent frame leakage across train/test.
            training = [f for s in sessions[:-1] for f in s["frames"]]
            heldout = sessions[-1]["frames"]
            if len(training) < 8 or len(heldout) < 2:
                raise ValueError("Insufficient training/heldout samples")
            if any(max(map(abs, f["state_features"])) > .1 for f in training+heldout):
                raise ValueError("Training features exceed the explicit synthetic [-0.1,0.1] metre distribution")
            x = np.array([f["state_features"]+[1.] for f in training])
            y = np.array([f["actions"] for f in training])
            weights = np.linalg.solve(x.T@x+1e-6*np.eye(4), x.T@y)
            policy = self.register_policy({"name": payload.get("name", "Tiny synthetic behavior cloning"), "version": payload.get("version", "0.1.0"), "task_class": "cluttered_retrieval"})
            record = self._policy(policy["id"])
            artifact = {"format": "tiny_ridge_bc_v1", "weights": weights.tolist(), "training_episode_ids": session_ids[:-1], "heldout_episode_id": session_ids[-1], "training_samples": len(training), "heldout_samples": [{"features": f["state_features"], "action": f["actions"]} for f in heldout], "surrogate_only": True}
            artifact_path = self.root / f"{policy['id']}.json"
            artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
            record.update(artifact=artifact_path.name, artifact_hash=hashlib.sha256(artifact_path.read_bytes()).hexdigest(), action_schema="surrogate_delta_xyz_v1", execution_type="SYNTHETIC_FEATURE_BC", training_dataset=session_ids, training_environment="synthetic_mock_room", status="trained", approval_status="trained", validated_distribution=["synthetic state-feature offset [-0.1,0.1] metres", "not trained on RGB or language"])
            self._event("tiny_policy_trained", policy["id"], training_samples=len(training))
            return self.get_policy(policy["id"])

    def _artifact(self, policy):
        artifact_name = policy.get("artifact")
        if not artifact_name or not re.fullmatch(r"policy_[a-f0-9]{12}\.json", artifact_name):
            raise ValueError("No locally trained supported policy artifact; imported metadata is not executable")
        path = self.root / artifact_name
        if hashlib.sha256(path.read_bytes()).hexdigest() != policy["artifact_hash"]:
            raise ValueError("Policy artifact integrity mismatch")
        return json.loads(path.read_text(encoding="utf-8"))

    def evaluate_policy(self, ident, payload=None):
        payload = payload or {}
        with self.lock:
            policy = self._policy(ident)
            if policy["status"] in {"retired", "research_active"}:
                raise ValueError("Evaluate a trained candidate; retired or active versions are immutable")
            artifact = self._artifact(policy)
            weights = np.asarray(artifact["weights"])
            samples = artifact["heldout_samples"]
            predicted = np.array([s["features"]+[1.] for s in samples]) @ weights
            actual = np.array([s["action"] for s in samples])
            rmse = float(np.sqrt(np.mean((predicted-actual)**2)))
            unsafe = int(np.sum(np.any(np.abs(predicted) > .020001, axis=1)))
            abstention_results = [abstention_gate(case) for case in ABSTENTION_CASES]
            expected = [False]+[True]*(len(ABSTENTION_CASES)-1)
            abstention_accuracy = sum(r["abstain"] == e for r, e in zip(abstention_results, expected))/len(expected)
            simulation = run_benchmark(episodes=min(24, max(8, int(payload.get("episodes", 8)))), seed=int(payload.get("seed", 107)))
            evaluation = {"id": "eval_"+uuid.uuid4().hex[:12], "at": now(), "source": "computed_locally_from_artifact_and_heldout_episode", "artifact_hash": policy["artifact_hash"], "heldout_episode_id": artifact["heldout_episode_id"], "heldout_samples": len(samples), "action_rmse_m": rmse, "unsafe_action_count": unsafe, "abstention_gate_accuracy": abstention_accuracy, "simulation": simulation["summary"], "sim_scope": simulation["benchmark"], "hardware_evidence": False, "task_success_rate": None, "bimanual_success_rate": None, "sim_real_gap": None, "passed": rmse < .003 and unsafe == 0 and abstention_accuracy == 1 and simulation["summary"]["finite_dynamics_rate"] == 1 and simulation["summary"]["episodes_with_robot_contacts"] == 0}
            policy.update(evaluation=evaluation, sim_results=simulation["summary"], status="simulator_evaluated", approval_status="simulator_evaluated", unsafe_attempt_rate=unsafe/len(samples), abstention_rate=sum(r["abstain"] for r in abstention_results)/len(expected))
            self._event("policy_evaluated", ident, evaluation_id=evaluation["id"], passed=evaluation["passed"])
            return self.get_policy(ident)

    def promote_policy(self, ident, payload):
        with self.lock:
            policy = self._policy(ident)
            if payload.get("target", "research") not in {"research", "simulation"}:
                raise ValueError("Hardware promotion is blocked: no verified vendor action model, calibrated robot, lab evidence or institutional approval")
            if policy["status"] != "simulator_evaluated" or not policy.get("evaluation", {}).get("passed"):
                raise ValueError("Computed offline and simulator evaluation gates must pass")
            self._artifact(policy)
            if payload.get("safety_signoff") is not True or not payload.get("reviewer_id"):
                raise ValueError("Research activation requires explicit safety signoff and named reviewer")
            previous = self.state["active_policy"]
            if previous:
                self._policy(previous).update(status="superseded", approval_status="superseded")
            policy.update(status="research_active", approval_status="research_active", rollback_version=previous, promoted_at=now(), reviewer_id=payload["reviewer_id"])
            self.state["active_policy"] = ident
            self._event("policy_promoted_research_only", ident, previous=previous)
            return self.get_policy(ident)

    def retire_policy(self, ident):
        with self.lock:
            policy = self._policy(ident)
            policy.update(status="retired", approval_status="retired")
            if self.state["active_policy"] == ident:
                self.state["active_policy"] = None
            self._event("policy_retired", ident)
            return self.get_policy(ident)

    def rollback_policy(self, ident):
        with self.lock:
            policy = self._policy(ident)
            if self.state["active_policy"] != ident:
                raise ValueError("Only the active policy may roll back")
            previous = policy.get("rollback_version")
            if previous:
                candidate = self._policy(previous)
                if candidate["status"] == "retired" or not candidate.get("evaluation", {}).get("passed"):
                    raise ValueError("Previous version is not eligible for rollback")
                self._artifact(candidate)
                candidate.update(status="research_active", approval_status="research_active")
            policy.update(status="retired", approval_status="retired")
            self.state["active_policy"] = previous
            self._event("policy_rolled_back", ident, active_policy=previous)
            return {"retired_policy": ident, "active_policy": previous, "hardware_approved": False}

    def route_skill(self, payload):
        task = payload.get("task_class", "cluttered_retrieval")
        if task in {"scan", "observe", "state_diff"}:
            return {"execution_type": "OBSERVE_ONLY", "skill_id": task, "reason": "Non-manipulation inspection uses deterministic observation; no object actuation is proposed", "authorizes_hardware": False}
        decision = abstention_gate(payload)
        if decision["abstain"]:
            return {"execution_type": "BLOCKED", "skill_id": "abstention", **decision}
        if task in {"scan", "navigate", "room_reset"}:
            return {"execution_type": "DETERMINISTIC", "skill_id": task, "reason": "Known mock geometry permits a classical candidate; execution still requires the safety supervisor", "authorizes_hardware": False}
        active = self.state["active_policy"]
        if active and self._policy(active)["task_class"] == task and payload.get("environment") == "synthetic_mock_room":
            return {"execution_type": "SYNTHETIC_FEATURE_BC", "policy_id": active, "skill_id": task, "supervision_required": True, "authorizes_hardware": False}
        return {"execution_type": "TELEOPERATION", "skill_id": task, "reason": "No approved VLA for this task/observation/action embodiment; Quest transport is not connected", "authorizes_hardware": False}

    def propose_action(self, policy_id, payload):
        with self.lock:
            policy = self._policy(policy_id)
            if policy["status"] != "research_active" or payload.get("environment") != "synthetic_mock_room":
                raise ValueError("Only an activated synthetic policy can propose mock actions")
            decision = abstention_gate(payload)
            if payload.get("task_class", policy["task_class"]) != policy["task_class"] or payload.get("object_class") not in policy["object_classes"]:
                decision = {"abstain": True, "reasons": decision["reasons"]+["policy_task_or_object_mismatch"], "authorizes_hardware": False}
            if decision["abstain"]:
                return {"action": [0., 0., 0.], "stopped": True, **decision}
            horizon = payload.get("horizon_s", .1)
            if not isinstance(horizon, (int, float)) or not 0 < horizon <= .1:
                raise ValueError("Maximum synthetic action horizon is 100 ms")
            features = np.asarray(payload.get("state_features"), dtype=float)
            if features.shape != (3,) or not np.isfinite(features).all() or np.max(np.abs(features)) > .1:
                return {"action": [0., 0., 0.], "abstain": True, "stopped": True, "reasons": ["state_features_out_of_distribution"], "authorizes_hardware": False}
            artifact = self._artifact(policy)
            action = np.append(features, 1) @ np.asarray(artifact["weights"])
            if not np.isfinite(action).all() or np.max(np.abs(action)) > .020001:
                return {"action": [0., 0., 0.], "abstain": True, "stopped": True, "reasons": ["learned_action_exceeds_envelope"], "authorizes_hardware": False}
            return {"action": action.tolist(), "action_schema": "surrogate_delta_xyz_v1", "horizon_s": horizon, "abstain": False, "stopped": False, "authorizes_hardware": False, "requires_external_safety_approval": True}


def synthetic_frame(timestamp_s=0., features=None, intervention=False):
    """Explicitly synthetic references; no image files or robot samples are implied."""
    features = [.03, -.02, .01] if features is None else list(features)
    streams = {name: {"timestamp_s": timestamp_s, "uri": f"synthetic://no-media/{name}/{timestamp_s:.3f}", "synthetic": True} for name in ("head_rgb", "head_depth", "left_wrist_rgb", "right_wrist_rgb")}
    return {"timestamp_s": timestamp_s, **streams, "base_pose": [0., 0., 0.], "base_velocity": [0., 0., 0.], "localization_confidence": 1., "left_arm_q": [0.]*7, "left_arm_qd": [0.]*7, "right_arm_q": [0.]*7, "right_arm_qd": [0.]*7, "vertical_stage_state": [.1, 0.], "gripper_state": [0., 0.], "action_schema": "surrogate_delta_xyz_v1", "actions": (.18*np.array(features)).tolist(), "state_features": features, "intervention": intervention, "failure_category": "safe_correction" if intervention else None, "safety_events": ["autonomy_stopped_before_synthetic_takeover"] if intervention else []}


def run_learning_demo(directory="data/runtime/learning-demo", seed=17):
    """An executed synthetic teaching/training/evaluation lifecycle, not VLA competence."""
    pipeline = LearningPipeline(directory)
    rng = np.random.default_rng(seed)
    ids = []
    for episode in range(5):
        session = pipeline.create_session({"instruction": "Move a synthetic point toward an approved phone proxy", "consent": True, "environment": "synthetic_mock_room", "operator_id": "synthetic_fixture_generator", "takeover_reason": "synthetic low confidence correction"})
        ident = session["id"]
        pipeline.start_session(ident)
        for frame in range(12):
            pipeline.record_frame(ident, synthetic_frame(frame*.05, rng.uniform(-.1, .1, 3), intervention=episode == 1 and frame > 7))
        pipeline.stop_session(ident)
        pipeline.label_session(ident, {"success": True, "correction_notes": "Synthetic label for point-action regression only"})
        pipeline.review_session(ident, {"approved": True, "privacy_cleared": True, "safety_cleared": True, "reviewer_id": "synthetic_fixture_review_not_human_signoff"})
        ids.append(ident)
    policy = pipeline.train_policy({"session_ids": ids})
    policy = pipeline.evaluate_policy(policy["id"], {"episodes": 8, "seed": seed+100})
    result = {"synthetic_only": True, "not_vla_competence": True, "sessions": len(ids), "frames": 60, "policy": policy, "activation": "pending_explicit_human_research_signoff", "robot_actions_executed": 0}
    (pipeline.root / "demo_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
