import json

import numpy as np
import pytest
from pydantic import ValidationError

from ml.pipeline import LearningPipeline, TeleopFrame, list_skills, synthetic_frame
from sim.engine import ABSTENTION_CASES


@pytest.fixture
def pipeline(tmp_path):
    return LearningPipeline(tmp_path / "learning")


def session_with_frames(pipeline, seed=1):
    session = pipeline.create_session({"instruction": "Move approved synthetic phone proxy", "consent": True})
    ident = session["id"]
    pipeline.start_session(ident)
    rng = np.random.default_rng(seed)
    for i in range(6):
        pipeline.record_frame(ident, synthetic_frame(i*.05, rng.uniform(-.1, .1, 3), intervention=i == 5))
    pipeline.stop_session(ident)
    pipeline.label_session(ident, {"success": True, "correction_notes": "synthetic fixture"})
    return ident


def reviewed_sessions(pipeline):
    ids = [session_with_frames(pipeline, seed) for seed in (1, 2, 3)]
    for ident in ids:
        pipeline.review_session(ident, {"approved": True, "privacy_cleared": True, "safety_cleared": True, "reviewer_id": "test_reviewer"})
    return ids


def trained(pipeline):
    return pipeline.train_policy({"session_ids": reviewed_sessions(pipeline)})


def evaluated(pipeline):
    policy = trained(pipeline)
    return pipeline.evaluate_policy(policy["id"], {"episodes": 8})


def test_skill_registry_does_not_invent_validation():
    skills = list_skills()
    assert {s["benchmark"] for s in skills} == set("ABCDEF")
    assert all(s["success_rate"] is None and s["real_results"] is None for s in skills)
    assert next(s for s in skills if s["id"] == "clean_fabric")["approval_status"] == "research_definition_only"


@pytest.mark.parametrize("payload", [{"consent": False}, {"consent": True, "environment": "patient_room"}, {"consent": True, "contains_patient_data": True}])
def test_capture_requires_consent_and_excludes_patient_environments(pipeline, payload):
    with pytest.raises(ValueError):
        pipeline.create_session({"instruction": "fixture", **payload})
    assert not pipeline.list_sessions()


def test_stream_synchronization_and_finite_values():
    frame = synthetic_frame()
    frame["left_wrist_rgb"]["timestamp_s"] = .031
    with pytest.raises(ValidationError, match="skew"):
        TeleopFrame.model_validate(frame)
    frame = synthetic_frame()
    frame["left_arm_q"][0] = float("nan")
    with pytest.raises(ValidationError):
        TeleopFrame.model_validate(frame)
    frame = synthetic_frame()
    frame["actions"][0] = .1
    with pytest.raises(ValidationError, match="envelope"):
        TeleopFrame.model_validate(frame)


def test_monotonic_recording_and_immutable_reviewed_episodes(pipeline):
    ident = pipeline.create_session({"instruction": "fixture", "consent": True})["id"]
    with pytest.raises(ValueError, match="not recording"):
        pipeline.record_frame(ident, synthetic_frame())
    pipeline.start_session(ident)
    pipeline.record_frame(ident, synthetic_frame())
    with pytest.raises(ValueError, match="increasing"):
        pipeline.record_frame(ident, synthetic_frame())
    pipeline.stop_session(ident)
    pipeline.label_session(ident, {"success": False, "failure_category": "abstained"})
    pipeline.review_session(ident, {"approved": True, "privacy_cleared": True, "safety_cleared": True, "reviewer_id": "reviewer"})
    with pytest.raises(ValueError):
        pipeline.label_session(ident, {"success": True})
    assert pipeline.get_session(ident)["frame_count"] == 1
    assert pipeline.get_session(ident)["labels"]["success"] is False


def test_review_requires_nonempty_labeled_data_and_named_clearance(pipeline):
    ident = session_with_frames(pipeline)
    with pytest.raises(ValueError, match="Named reviewer"):
        pipeline.review_session(ident, {"approved": True})
    result = pipeline.review_session(ident, {"approved": False})
    assert result["status"] == "rejected"
    with pytest.raises(ValueError):
        pipeline.train_policy({"session_ids": [ident]*3})


def test_export_requires_review_and_explicit_human_approval(pipeline):
    ident = session_with_frames(pipeline)
    with pytest.raises(ValueError, match="export requires"):
        pipeline.export_dataset([ident], "researcher")
    with pytest.raises(ValueError, match="reviewed"):
        pipeline.export_dataset([ident], "researcher", True)
    pipeline.review_session(ident, {"approved": True, "privacy_cleared": True, "safety_cleared": True, "reviewer_id": "researcher"})
    assert pipeline.export_dataset([ident], "researcher", True)["episode_count"] == 1


def test_imported_metadata_and_forged_metrics_cannot_promote(pipeline):
    policy = pipeline.register_policy({"name": "untrusted", "status": "approved", "success_rate": 1, "evaluation": {"passed": True}})
    assert policy["status"] == "draft"
    assert policy["success_rate"] is None
    with pytest.raises(ValueError, match="artifact"):
        pipeline.evaluate_policy(policy["id"], {"passed": True, "success_rate": 1})
    with pytest.raises(ValueError, match="gates"):
        pipeline.promote_policy(policy["id"], {"target": "research", "safety_signoff": True, "reviewer_id": "r"})


def test_training_rejects_duplicate_episodes_that_leak_holdout(pipeline):
    ids = reviewed_sessions(pipeline)
    with pytest.raises(ValueError, match="distinct"):
        pipeline.train_policy({"session_ids": [ids[0], ids[1], ids[0]]})


def test_actual_tiny_learning_heldout_evaluation_and_no_hardware_authority(pipeline):
    policy = evaluated(pipeline)
    evaluation = policy["evaluation"]
    assert evaluation["passed"]
    assert evaluation["heldout_samples"] == 6
    assert evaluation["action_rmse_m"] < .003
    assert evaluation["unsafe_action_count"] == 0
    assert evaluation["abstention_gate_accuracy"] == 1
    assert evaluation["simulation"]["physics_steps"] >= 2400
    assert not policy["hardware_approved"]
    assert policy["success_rate"] is None
    with pytest.raises(ValueError, match="Hardware promotion is blocked"):
        pipeline.promote_policy(policy["id"], {"target": "hardware", "safety_signoff": True, "reviewer_id": "r"})
    with pytest.raises(ValueError, match="signoff"):
        pipeline.promote_policy(policy["id"], {"target": "research"})


def test_activated_policy_proposal_abstains_and_stays_inside_action_envelope(pipeline):
    policy = evaluated(pipeline)
    pipeline.promote_policy(policy["id"], {"target": "research", "safety_signoff": True, "reviewer_id": "test_reviewer"})
    payload = {**ABSTENTION_CASES[0], "environment": "synthetic_mock_room", "state_features": [.08, -.07, .05], "horizon_s": .1}
    action = pipeline.propose_action(policy["id"], payload)
    assert not action["abstain"]
    assert max(map(abs, action["action"])) <= .02
    assert not action["authorizes_hardware"]
    assert pipeline.propose_action(policy["id"], {**payload, "object_class": "medication"})["stopped"]
    assert pipeline.propose_action(policy["id"], {**payload, "object_class": "book"})["stopped"]
    assert pipeline.propose_action(policy["id"], {**payload, "task_class": "drawer_family"})["stopped"]
    assert pipeline.propose_action(policy["id"], {**payload, "state_features": [2, 0, 0]})["abstain"]
    with pytest.raises(ValueError, match="100 ms"):
        pipeline.propose_action(policy["id"], {**payload, "horizon_s": 2})
    with pytest.raises(ValueError, match="synthetic"):
        pipeline.propose_action(policy["id"], {**payload, "environment": "hospital"})


def test_artifact_tamper_is_rejected(pipeline):
    policy = trained(pipeline)
    (pipeline.root / policy["artifact"]).write_text('{"weights": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        pipeline.evaluate_policy(policy["id"])


def test_policy_rollback_and_registry_persistence(pipeline):
    first = evaluated(pipeline)
    signoff = {"target": "research", "safety_signoff": True, "reviewer_id": "test_reviewer"}
    pipeline.promote_policy(first["id"], signoff)
    second = evaluated(pipeline)
    pipeline.promote_policy(second["id"], signoff)
    assert pipeline.get_policy(first["id"])["status"] == "superseded"
    result = pipeline.rollback_policy(second["id"])
    assert result["active_policy"] == first["id"]
    reloaded = LearningPipeline(pipeline.root)
    assert reloaded.get_policy(first["id"])["status"] == "research_active"
    assert reloaded.get_policy(second["id"])["status"] == "retired"
    assert not reloaded.get_policy(first["id"])["hardware_approved"]


def test_observation_does_not_require_a_manipulation_permission(pipeline):
    assert pipeline.route_skill({"task_class": "scan"})["execution_type"] == "OBSERVE_ONLY"
    assert pipeline.route_skill({"task_class": "cluttered_retrieval"})["execution_type"] == "BLOCKED"
