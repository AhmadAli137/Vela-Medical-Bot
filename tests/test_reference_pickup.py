"""Physical pickup regressions: free phone, bilateral friction, then gravity."""
import mujoco
import math
import numpy as np
import pytest

from sim.reference_runtime import ReferenceSimulation


def test_free_phone_is_lifted_held_and_released_by_friction_only():
    sim = ReferenceSimulation()
    assert not any(kind in {mujoco.mjtEq.mjEQ_WELD,mujoco.mjtEq.mjEQ_CONNECT} for kind in sim.model.eq_type)
    assert all(sim.model.joint(int(joint)).name.startswith("blinds_") for joint in [*sim.model.eq_obj1id,*sim.model.eq_obj2id])
    phone = sim.model.body("phone").id
    assert sim.model.body_gravcomp[phone] == 0
    assert sim.model.joint("phone_free").type[0] == mujoco.mjtJoint.mjJNT_FREE
    planned = sim.command("pickup_demo")
    assert planned["metrics"]["pickup"]["collision_samples"] >= 240
    for _ in range(math.ceil(sum(stage["duration_s"] for stage in sim.stages)/2)+1):
        state = sim.advance(2.)
        assert not state["paused"], state["metrics"]
        assert not state["metrics"]["contacts"]
    pickup = state["metrics"]["pickup"]
    assert pickup["success"] and pickup["bilateral_contact"]
    assert pickup["height_gain_m"] > .20
    assert set(pickup["finger_contacts"]) == {"left_finger_-1", "left_finger_1"}
    assert all(value > 1. for value in pickup["normal_forces_n"].values())
    assert state["metrics"]["object_attached"] is False
    held_height = state["bodies"]["phone"]["position"][2]
    for _ in range(5):
        state = sim.advance(2.)
        assert state["metrics"]["pickup"]["success"]
        assert abs(state["bodies"]["phone"]["position"][2]-held_height) < .003
    with pytest.raises(ValueError, match="Release the phone"):
        sim.command("joint_demo")
    sim.command("pause")
    frozen = sim.data.qpos.copy()
    sim.advance(1.)
    assert np.array_equal(frozen, sim.data.qpos)
    releasing = sim.command("release_phone")
    assert releasing["metrics"]["grasp_success"] is False
    assert releasing["metrics"]["pickup"]["bilateral_hold_s"] == 0.
    released = sim.advance(2.)
    assert released["metrics"]["pickup"]["released"]
    assert released["metrics"]["pickup"]["ever_succeeded"]
    assert not released["metrics"]["grasp_success"]
    assert not released["metrics"]["pickup"]["bilateral_contact"]
    assert released["bodies"]["phone"]["position"][2] < held_height-.20
    assert released["bodies"]["phone"]["position"][2] == pytest.approx(.8135, abs=.002)
    assert not released["paused"]


def test_carriages_and_arm_reach_cover_measured_low_to_high_workspace():
    sim = ReferenceSimulation()
    sim.command("lift_demo")
    for _ in range(14):
        state = sim.advance(2.)
        assert not state["paused"], state["metrics"]
    lift = state["metrics"]["lift"]
    assert lift["complete"]
    for side in ("left", "right"):
        assert lift["travel_m"][side] > .83
        assert .10 < lift["min_hand_height_m"][side] < .15
        assert lift["max_hand_height_m"][side] > 1.70
        assert abs(lift["positions_m"][side]) < .001
    assert state["bodies"]["head"]["position"][2]-state["bodies"]["robot_base"]["position"][2] == pytest.approx(1.54)
    assert not state["metrics"]["contacts"]


def test_fixture_guards_do_not_reset_or_teleport_a_displaced_scene():
    sim = ReferenceSimulation()
    sim.data.qpos[sim.model.joint("phone_free").qposadr[0]] += .04
    mujoco.mj_forward(sim.model, sim.data)
    previous = sim.data.qpos.copy()
    with pytest.raises(ValueError, match="Reset the scene"):
        sim.command("pickup_demo")
    assert np.array_equal(previous, sim.data.qpos)
    with pytest.raises(ValueError, match="confirmed bilateral pickup"):
        sim.command("release_phone")


def test_intended_finger_allowance_does_not_mask_phone_palm_collision():
    sim = ReferenceSimulation()
    sample = mujoco.MjData(sim.model)
    sample.qpos[:] = sim.data.qpos
    address = sim.model.joint("phone_free").qposadr[0]
    sample.qpos[address:address+3] = sim.data.xpos[sim.model.body("left_hand").id]
    mujoco.mj_forward(sim.model, sample)
    collisions = sim._contacts(sample, allow_phone_grasp=True)
    assert any(set(contact["geoms"]) == {"phone_geom", "left_hand_geom"} for contact in collisions)


def test_collision_invalidates_pickup_success_and_requires_reset():
    sim = ReferenceSimulation()
    sim.command("pickup_demo")
    for _ in range(math.ceil(sum(stage["duration_s"] for stage in sim.stages)/2)+1):
        held = sim.advance(2.)
    assert held["metrics"]["grasp_success"] is True
    # Perturb only the unused arm into the mast. The phone stays under physics.
    sim.data.qpos[sim.model.joint("right_joint_1").qposadr[0]] = -2.
    sim.data.qpos[sim.model.joint("right_joint_2").qposadr[0]] = 1/3
    mujoco.mj_forward(sim.model, sim.data)
    stopped = sim.advance(.002)
    assert stopped["paused"]
    assert stopped["metrics"]["contacts"]
    assert stopped["metrics"]["grasp_success"] is False
    assert stopped["metrics"]["pickup"]["status"] == "stopped"
    assert stopped["metrics"]["pickup"]["ever_succeeded"] is True
    with pytest.raises(ValueError, match="Reset the scene"):
        sim.command("pause")
    reset = sim.command("reset")
    assert reset["metrics"]["stop_reason"] is None
    assert reset["metrics"]["grasp_success"] is None
