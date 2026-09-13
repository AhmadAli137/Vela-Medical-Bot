"""Reference-model regressions use actual MuJoCo, without filesystem fixtures."""
import json

import mujoco
import numpy as np
import pytest

from sim.reference_model import body_descriptors, load_reference_model
from sim.reference_runtime import ReferenceSimulation


def test_reference_topology_geometry_and_artifact_provenance():
    model, data, metadata = load_reference_model()
    assert model.njnt == 26 and model.nu == 25
    assert model.nq == 32 and model.nv == 31
    assert len(body_descriptors()) == 28
    assert model.joint("phone_free").type[0] == mujoco.mjtJoint.mjJNT_FREE
    assert model.neq == 0, "Grasp must not use a weld or attachment constraint"
    assert metadata["hardware_model_verified"] is False
    assert "handout-page-1.png" in metadata["reference_files"][0]
    for side in ("left", "right"):
        assert model.joint(f"{side}_lift").type[0] == mujoco.mjtJoint.mjJNT_SLIDE
        assert all(model.joint(f"{side}_joint_{i}").id >= 0 for i in range(1, 8))
        assert model.camera(f"{side}_wrist").id >= 0
    assert data.xpos[model.body("head").id][2] == pytest.approx(1.67)
    assert model.camera("head_stereo_right").id >= 0


def test_body_playback_contract_is_actual_mujoco_world_state():
    sim = ReferenceSimulation()
    state = sim.state()
    for name, pose in state["bodies"].items():
        index = sim.model.body(name).id
        assert pose["position"] == sim.data.xpos[index].tolist()
        assert pose["quaternion"] == sim.data.xquat[index].tolist()
        assert np.linalg.norm(pose["quaternion"]) == pytest.approx(1.)
    assert state["mode"] == "idle"
    assert not state["authorizes_hardware"]
    json.dumps(state, allow_nan=False)


def test_joint_demonstration_actuates_every_synthetic_dof():
    sim = ReferenceSimulation()
    initial = sim.initial_q.copy()
    sim.command("joint_demo")
    state = sim.advance(2.)
    changed = np.abs(sim.data.qpos[sim.actuated_q]-initial[sim.actuated_q])
    assert np.all(changed > .0001), dict(zip(state["joints"], changed.tolist()))
    assert state["simulation_time"] == pytest.approx(2.)
    assert state["metrics"]["physics_steps"] == 1000
    assert state["metrics"]["finite_dynamics"]
    assert not state["paused"]
    assert not state["metrics"]["contacts"]


def test_demo_remains_contact_free_across_a_full_motion_cycle():
    sim = ReferenceSimulation()
    sim.command("joint_demo")
    for _ in range(8):
        state = sim.advance(2.)
        assert not state["paused"], state["metrics"]
        assert not state["metrics"]["contacts"]
    assert state["metrics"]["physics_steps"] == 8000


def test_reach_uses_ik_servo_dynamics_and_reports_measured_error():
    sim = ReferenceSimulation()
    planned = sim.command("reach_demo")
    assert planned["metrics"]["reach"]["sampled_collision_gate_passed"]
    assert not planned["metrics"]["reach"]["endpoint_reached"]
    assert planned["metrics"]["reach"]["actual_endpoint_error_m"] > .25
    for _ in range(3):
        result = sim.advance(2.)
    reach = result["metrics"]["reach"]
    assert reach["endpoint_reached"]
    assert reach["actual_endpoint_error_m"] < .01
    assert reach["ik_residual_m"] < .015
    assert not result["metrics"]["contacts"]
    assert result["metrics"]["object_attached"] is False
    assert result["metrics"]["grasp_success"] is None
    assert result["joints"]["base_x"] > .15


def test_unreachable_cartesian_goal_is_not_represented_as_reached():
    sim = ReferenceSimulation()
    initial = sim.data.qpos.copy()
    report = sim.solve_reach([8, 8, 8])
    assert not report["reachable"]
    assert report["residual_m"] > 5
    assert not report["authorizes_hardware"]
    assert np.array_equal(initial, sim.data.qpos), "Planning must not teleport the live robot"


def test_collision_gate_detects_robot_environment_overlap_and_stops():
    sim = ReferenceSimulation()
    sim.data.qpos[sim.model.joint("base_x").qposadr[0]] = 1.15
    mujoco.mj_forward(sim.model, sim.data)
    assert sim._contacts(), "Environment collision masks must not hide arm/table contact"
    result = sim.advance(.002)
    assert result["paused"]
    assert result["metrics"]["stop_reason"] == "Synthetic contact stop"
    assert result["metrics"]["contacts"]


def test_pause_toggle_reset_and_bounded_input():
    sim = ReferenceSimulation()
    sim.command({"command": "joint_demo"})
    sim.advance(.4)
    state = sim.command("pause")
    assert state["paused"]
    q = sim.data.qpos.copy()
    sim.advance(1.)
    assert np.array_equal(q, sim.data.qpos)
    assert not sim.command("pause")["paused"]
    reset = sim.command("reset")
    assert reset["mode"] == "idle"
    assert reset["simulation_time"] == 0
    assert reset["metrics"]["physics_steps"] == 0
    assert np.array_equal(sim.initial_q, sim.data.qpos)
    with pytest.raises(ValueError):
        sim.command("hardware_execute")
    with pytest.raises(ValueError):
        sim.advance(float("nan"))
    with pytest.raises(ValueError):
        sim.advance(3.)


def test_state_catches_up_by_at_most_fifty_milliseconds():
    sim = ReferenceSimulation()
    sim.last_clock -= 10.
    state = sim.state()
    assert state["simulation_time"] <= .05000001
    assert state["metrics"]["physics_steps"] <= 25
