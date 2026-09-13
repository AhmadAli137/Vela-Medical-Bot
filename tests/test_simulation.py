import copy
import json

import mujoco
import numpy as np
import pytest

from sim.engine import ABSTENTION_CASES, abstention_gate, inverse_kinematics, load_scene, replay_trajectory, robot_contacts, run_benchmark, validate_plan
from sim.hypotheses import generate_hypotheses
from sim.model import build_scene


def test_mjcf_loads_with_full_surrogate_topology():
    model, data, metadata = load_scene(19)
    for side in ("left", "right"):
        assert len([model.joint(f"{side}_joint_{i}") for i in range(1, 8)]) == 7
        assert model.camera(f"{side}_wrist").id >= 0
        assert model.site(f"{side}_ee").id >= 0
    assert model.joint("lift").type[0] == mujoco.mjtJoint.mjJNT_SLIDE
    assert model.camera("head_rgb").id >= 0
    assert model.camera("head_stereo_right").id >= 0
    assert model.nu == 22  # base(3), lift(1), arms(14), gripper fingers(4)
    assert model.body("safe_drawer").id >= 0
    assert model.body("bag_rigid_proxy").id >= 0
    assert metadata["hardware_model_verified"] is False
    assert not robot_contacts(model, data)


def test_seeded_scene_generation_is_reproducible_and_variable():
    xml, metadata = build_scene(12)
    assert build_scene(12) == (xml, metadata)
    assert build_scene(13)[1]["model_hash"] != metadata["model_hash"]
    assert build_scene(13)[1]["sampled_object_masses_kg"] != metadata["sampled_object_masses_kg"]


def test_forward_dynamics_moves_both_arms_and_lift_without_suppressed_contacts():
    model, data, _ = load_scene(3, clutter=0)
    for side, sign in (("left", 1), ("right", -1)):
        data.ctrl[model.actuator(f"ctrl_{side}_joint_1").id] = sign*.1
    data.ctrl[model.actuator("ctrl_lift").id] = .1
    for _ in range(300):
        mujoco.mj_step(model, data)
        assert not robot_contacts(model, data)
    assert np.isfinite(data.qpos).all()
    assert data.qpos[model.joint("lift").qposadr[0]] > .04
    assert data.qpos[model.joint("left_joint_1").qposadr[0]] > .03
    assert data.qpos[model.joint("right_joint_1").qposadr[0]] < -.03


def test_collision_regression_detects_robot_furniture_overlap():
    model, data, _ = load_scene(3, clutter=0)
    data.qpos[model.joint("base_x").qposadr[0]] = 1.05
    mujoco.mj_forward(model, data)
    assert robot_contacts(model, data), "Collision checking must not silently disable robot/environment contact"


def test_ik_reaches_nearby_endpoint_and_refuses_far_target():
    model, data, _ = load_scene(3, clutter=0)
    site = data.site_xpos[model.site("left_ee").id].copy()
    assert inverse_kinematics(model, data, "left", site+[-.035, .02, .03])["reachable"]
    assert not inverse_kinematics(model, data, "right", [20, 20, 20])["reachable"]
    with pytest.raises(ValueError):
        inverse_kinematics(model, data, "left", [float("nan"), 0, 0])


def room_and_plan():
    room = {"version": 1, "geometry": {"width": 6, "depth": 5, "height": 3}, "objects": [{"id": "phone", "pose": {"x": 1, "y": 1, "z": .8}, "dimensions": {"x": .15, "y": .08, "z": .015}}], "zones": [], "persons": []}
    plan = {"candidate_steps": [{"id": "step1", "action": "place_in_zone", "object_id": "phone", "target_pose": {"x": 1.5, "y": 1.2, "z": .8}}]}
    return room, plan


def test_semantic_surrogate_validation_cannot_authorize_hardware():
    room, plan = room_and_plan()
    report = validate_plan(plan, room)
    assert report["passed"]
    assert report["metrics"]["physics_steps"] == 50
    assert not report["authorizes_hardware"]
    assert not report["hardware_model_verified"]
    assert not report["metrics"]["trajectory_validated"]
    assert not report["metrics"]["grasp_validated"]


def test_person_enters_swept_path_rejects_plan():
    room, plan = room_and_plan()
    room["persons"] = [{"id": "anonymous", "pose": {"x": 1.25, "y": 1.1, "z": 1}, "radius": .3}]
    report = validate_plan(plan, room)
    assert not report["passed"]
    assert report["metrics"]["minimum_person_clearance_m"] < 0


def test_keepout_intersection_and_missing_pose_fail_closed():
    room, plan = room_and_plan()
    room["zones"] = [{"id": "tubes", "type": "keep_out", "bounds": {"min": {"x": 1.2, "y": .8, "z": 0}, "max": {"x": 1.4, "y": 1.3, "z": 2}}}]
    assert not validate_plan(plan, room)["passed"]
    del plan["candidate_steps"][0]["target_pose"]
    assert not validate_plan(plan, room)["passed"]


@pytest.mark.parametrize("case", ABSTENTION_CASES, ids=[case["name"] for case in ABSTENTION_CASES])
def test_abstention_challenge_cases(case):
    result = abstention_gate(case)
    assert result["abstain"] == (case["name"] != "permitted_phone")
    assert not result["authorizes_hardware"]


def test_benchmark_reports_measured_physics_and_unknown_task_success():
    report = run_benchmark(3, 111)
    assert report["summary"]["physics_steps"] == 900
    assert report["summary"]["finite_dynamics_rate"] == 1
    assert report["summary"]["episodes_with_robot_contacts"] == 0
    assert report["summary"]["task_success_rate"] is None
    assert report["summary"]["sim_to_real_gap"] is None
    assert all(row["grasp_success"] is None for row in report["results"])
    json.dumps(report, allow_nan=False)


def test_surrogate_replay_is_bounded_and_vendor_data_is_blocked():
    frames = [{"timestamp_s": i*.05, "left_arm_q": [0, -.3, 0, .6, 0, 0, 0], "right_arm_q": [0, -.3, 0, .6, 0, 0, 0], "vertical_stage_state": [.05, 0]} for i in range(3)]
    report = replay_trajectory(frames)
    assert report["frames_replayed"] == 3
    assert not report["stopped"]
    assert not report["authorizes_hardware"]
    with pytest.raises(ValueError, match="Vendor"):
        replay_trajectory(frames, robot_revision="new_bracket_bot")
    frames[-1]["timestamp_s"] = 2
    with pytest.raises(ValueError, match="100 ms"):
        replay_trajectory(frames)


def test_uncertain_photo_hypotheses_need_review_and_preserve_provenance(tmp_path):
    annotation = {"source_id": "reviewed-fixture", "source_url": "synthetic://not-a-real-photo", "privacy_reviewed": True, "rights_reviewed": True, "objects": [{"class": "bed"}, {"class": "table"}]}
    report = generate_hypotheses(annotation, tmp_path / "hypotheses", count=3)
    assert len({r["model_hash"] for r in report["hypotheses"]}) == 3
    assert report["single_image_is_not_metric_ground_truth"]
    for idx, row in enumerate(report["hypotheses"]):
        assert row["source_id"] == annotation["source_id"]
        assert row["uncertainty"]["metric_reconstruction"] is False
        mujoco.MjModel.from_xml_path(str(tmp_path / "hypotheses" / f"hypothesis_{idx:03}" / "scene.xml"))
    annotation["privacy_reviewed"] = False
    with pytest.raises(ValueError, match="review"):
        generate_hypotheses(annotation, tmp_path / "blocked")
