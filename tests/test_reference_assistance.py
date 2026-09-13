"""Actual forward-dynamics delivery/control outcomes and failure gates."""
import copy

import mujoco
import numpy as np
import pytest

from sim.reference_assistance import ASSISTANCE_COMMANDS
from sim.reference_demos import load_trajectories, verify_demos
from sim.reference_runtime import ReferenceSimulation


@pytest.fixture(scope="module")
def assistance_results():
    return verify_demos("sim/outputs/reference_assistance.json",commands=ASSISTANCE_COMMANDS)


@pytest.mark.parametrize("command",["deliver_phone_demo","deliver_meal_demo"])
def test_free_object_delivery_requires_grasp_support_release_and_return(assistance_results,command):
    result=assistance_results["results"][command]
    assert result["completed"] and not result["paused"],result["final"]
    metrics=result["final"]["measurements"]
    assert metrics["confirmed_grasp_height_m"]>.15
    assert metrics["confirmed_grasp_hold_s"]>=2.
    assert metrics["supported_release_bilateral"]
    assert metrics["supported_release_force_n"]>.05
    assert metrics["object_xy_error_m"]<.005
    assert metrics["object_z_error_m"]<.001
    assert metrics["object_speed_m_s"]<.001
    assert metrics["support_force_n"]>.5
    assert metrics["fingers_clear"] and not metrics["bilateral_contact"]
    assert metrics["hand_clearance_m"]>1.
    assert metrics["patient_hand_distance_m"]<.55
    assert all(result["final"]["checks"].values())
    assert all(not sample["contacts"] for sample in result["samples"])


def test_blinds_move_by_real_hand_contact_and_remain_open(assistance_results):
    result=assistance_results["results"]["blinds_demo"]
    assert result["completed"] and not result["paused"],result["final"]
    measured=result["final"]["measurements"]
    assert measured["handle_travel_m"]>.17
    assert measured["minimum_slat_angle_rad"]>1.3
    assert measured["maximum_control_contact_force_n"]>.1
    assert measured["control_contact_force_n"]==0
    assert measured["rest_qpos_error"]<.001
    assert all(result["final"]["checks"].values())


def test_passive_blinds_have_no_actuator_or_motion_without_contact():
    sim=ReferenceSimulation()
    state=sim.advance(2.)
    assert all(sim.model.joint(int(j)).name.startswith(("base_","left_","right_")) for j in sim.model.actuator_trnid[:,0])
    assert max(abs(value)for value in state["object_joints"].values())<1e-8
    assert len(state["joints"])==25
    assert len(state["object_joints"])==17


@pytest.mark.parametrize("command,body",[("deliver_phone_demo","phone"),("deliver_meal_demo","meal_box")])
def test_lost_grasp_stops_delivery_and_never_teleports_object(command,body):
    sim=ReferenceSimulation()
    sim.command(command)
    for _ in range(10):
        state=sim.advance(2.)
    assert state["metrics"]["demo"]["measurements"]["ever_grasped"]
    address=sim.model.joint(f"{body}_free").qposadr[0]
    sim.data.qpos[address]+=.20  # External perturbation, never controller code.
    mujoco.mj_forward(sim.model,sim.data)
    state=sim.advance(.01)
    assert state["paused"] and not state["metrics"]["demo"]["complete"]
    assert "contact lost" in state["metrics"]["stop_reason"]
    assert state["bodies"][body]["position"][0]>.80
    with pytest.raises(ValueError,match="Reset the scene after"):
        sim.command("pause")


def test_camera_poses_match_mujoco_and_stereo_calibration():
    sim=ReferenceSimulation()
    state=sim.advance(.01)
    assert set(state["cameras"])=={"head_rgb","head_stereo_right","left_wrist","right_wrist"}
    for name,camera in state["cameras"].items():
        index=sim.model.camera(name).id
        assert camera["position"]==sim.data.cam_xpos[index].tolist()
        assert camera["rotation"]==sim.data.cam_xmat[index].tolist()
        matrix=np.asarray(camera["rotation"]).reshape(3,3)
        assert np.allclose(matrix.T@matrix,np.eye(3),atol=1e-9)
        assert camera["fovy_deg"]==sim.model.cam_fovy[index]
        assert camera["convention"]=="mujoco_opengl"
    baseline=np.linalg.norm(np.asarray(state["cameras"]["head_rgb"]["position"])-state["cameras"]["head_stereo_right"]["position"])
    assert baseline==pytest.approx(.054)


def test_failed_preflight_cannot_leave_contact_allowances_enabled(monkeypatch):
    import sim.reference_runtime as runtime
    sim=ReferenceSimulation()
    library=copy.deepcopy(load_trajectories(sim.metadata["model_hash"]))
    definition=library["commands"]["deliver_meal_demo"]
    definition["stages"][0]["target_qpos"][0]=1.05
    monkeypatch.setattr(runtime,"load_trajectories",lambda _:library)
    with pytest.raises(ValueError,match="Fixture path rejected"):
        sim.command("deliver_meal_demo")
    assert sim.intentional_contacts==set()
    assert sim.mode=="idle"


def test_fixture_start_checks_meal_and_passive_blinds():
    sim=ReferenceSimulation()
    for joint in ("meal_box_free","blinds_slide"):
        sim.command("reset")
        sim.data.qpos[sim.model.joint(joint).qposadr[0]]+=.10
        mujoco.mj_forward(sim.model,sim.data)
        with pytest.raises(ValueError,match="Reset the scene before"):
            sim.command("deliver_phone_demo")


def test_visual_tracking_pause_is_idempotent_and_preserves_grasp_control():
    sim=ReferenceSimulation()
    sim.command("deliver_phone_demo")
    for _ in range(10):
        state=sim.advance(2.)
    assert state["metrics"]["demo"]["measurements"]["bilateral_contact"]
    controls=sim.data.ctrl.copy()
    positions=sim.data.qpos.copy()
    velocity=sim.data.qvel.copy()
    for _ in range(2):
        paused=sim.command("pause_for_tracking")
        assert paused["paused"]
        assert paused["metrics"]["visual_tracking_pause_reason"]=="Visual tracking lost"
    sim.advance(2.)
    assert np.array_equal(controls,sim.data.ctrl)
    assert np.array_equal(positions,sim.data.qpos)
    assert np.array_equal(velocity,sim.data.qvel)
    resumed=sim.command("pause")
    assert not resumed["paused"]
    assert resumed["metrics"]["visual_tracking_pause_reason"] is None
    assert sim.advance(.01)["metrics"]["demo"]["measurements"]["bilateral_contact"]
    sim.command("pause_for_tracking")
    assert sim.command("reset")["metrics"]["visual_tracking_pause_reason"] is None


def test_assistance_and_tracking_pause_commands_are_available_via_local_api(tmp_path):
    from importlib import import_module
    from fastapi.testclient import TestClient
    app=import_module("services.app")
    client=TestClient(app.create_app(tmp_path/"assistance.sqlite3",demo=True))
    client.post("/api/session",json={"role":"researcher"})
    for command in sorted(ASSISTANCE_COMMANDS):
        client.post("/api/sim/reference/control",json={"command":"reset"})
        result=client.post("/api/sim/reference/control",json={"command":command})
        assert result.status_code==200,result.text
        assert result.json()["metrics"]["demo"]["command"]==command
        paused=client.post("/api/sim/reference/control",json={"command":"pause_for_tracking"})
        assert paused.status_code==200
        assert paused.json()["paused"]
        assert paused.json()["metrics"]["visual_tracking_pause_reason"]=="Visual tracking lost"


def test_carried_object_contact_with_patient_occupancy_stops_motion():
    sim=ReferenceSimulation()
    sim.command("deliver_phone_demo")
    address=sim.model.joint("phone_free").qposadr[0]
    sim.data.qpos[address:address+3]=[1.19,1.70,1.06]
    mujoco.mj_forward(sim.model,sim.data)
    contacts=sim._contacts()
    assert any(contact.get("carried_object_collision") and "patient_torso" in contact["geoms"] for contact in contacts)
    state=sim.advance(.002)
    assert state["paused"]
    assert state["metrics"]["stop_reason"]=="Synthetic contact stop"
    assert not state["metrics"]["demo"]["complete"]
