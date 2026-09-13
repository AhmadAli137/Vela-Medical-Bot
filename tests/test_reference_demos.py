"""Measured new-demo behavior in actual MuJoCo, including failure cases."""
import json
import math

import mujoco
import numpy as np
import pytest

from sim.reference_demos import load_trajectories, verify_demos
from sim.reference_runtime import ReferenceSimulation


@pytest.fixture(scope="module")
def outcomes():
    # Save the same observed rollout as the reviewable evidence artifact.
    return verify_demos(commands={"bedside_demo","greeting_demo","phone_return_demo"})


def test_bedside_visits_goal_and_returns_under_real_actuation(outcomes):
    result=outcomes["results"]["bedside_demo"]
    assert result["completed"] and not result["paused"]
    final=result["final"]
    measured=final["measurements"]
    assert measured["max_base_excursion_m"]>.70
    assert measured["base_home_error_m"]<.005
    assert any(sample["demo"]["measurements"]["base_goal_error_m"]<.025 for sample in result["samples"])
    assert final["stage_index"]==final["stage_count"]-1
    assert final["elapsed_s"]>=final["duration_s"]
    assert measured["settle_dwell_s"]>=.5
    assert all(final["checks"].values())


def test_greeting_measures_high_hand_and_wrist_motion_before_rest(outcomes):
    result=outcomes["results"]["greeting_demo"]
    assert result["completed"] and not result["paused"]
    measured=result["final"]["measurements"]
    assert measured["max_hand_height_m"]>1.50
    assert measured["wave_range_rad"]>.50
    assert measured["rest_qpos_error"]<.01
    assert measured["robot_speed"]<.01
    assert all(not sample["contacts"] for sample in result["samples"])


def test_phone_returns_with_support_before_opening_and_no_attachment(outcomes):
    result=outcomes["results"]["phone_return_demo"]
    assert result["completed"] and not result["paused"]
    measured=result["final"]["measurements"]
    assert measured["confirmed_grasp_height_m"]>.15
    assert measured["confirmed_grasp_hold_s"]>=2.
    assert measured["supported_release_bilateral"]
    assert measured["supported_release_force_n"]>.05
    assert measured["supported_release_height_m"]==pytest.approx(.8135,abs=.006)
    for gate in ("bilateral_contact","grasp_confirmed","phone_supported","phone_settled"):
        assert measured[f"gate_{gate}_passed"]
    assert measured["phone_xy_error_m"]<.005
    assert measured["phone_z_error_m"]<.001
    assert measured["phone_speed_m_s"]<.001
    assert measured["riser_support_force_n"]>.05
    assert measured["hand_clearance_m"]>.7
    pickup=result["samples"][-1]["pickup"]
    assert pickup["ever_succeeded"] and pickup["released"]
    assert not pickup["success"], "The released phone is no longer being grasped"
    assert pickup["attachment_constraints"]==0
    assert all(not sample["contacts"] for sample in result["samples"])


def test_displaced_phone_cannot_count_as_grasp_or_be_teleported_back():
    sim=ReferenceSimulation()
    sim.command("phone_return_demo")
    # External test-fixture perturbation after planning. Controller must never
    # copy the phone's initial coordinates from trajectory targets into qpos.
    address=sim.model.joint("phone_free").qposadr[0]
    sim.data.qpos[address]+=.12
    mujoco.mj_forward(sim.model,sim.data)
    for _ in range(math.ceil(sim.demo["duration_s"]/2)):
        state=sim.advance(2.)
        if state["paused"]:
            break
    assert state["paused"]
    assert not state["metrics"]["demo"]["complete"]
    assert state["metrics"]["demo"]["status"]=="stopped"
    assert not state["metrics"]["pickup"]["ever_succeeded"]
    # The displaced phone meets the arm before the closing stage: the real
    # unexpected-contact stop must take precedence over the later grasp gate.
    assert state["metrics"]["stop_reason"]=="Synthetic contact stop"
    assert state["metrics"]["contacts"]
    assert state["bodies"]["phone"]["position"][0]>.70
    with pytest.raises(ValueError,match="Reset the scene after"):
        sim.command("pause")


def test_pause_reset_and_completion_revocation_on_state_fault():
    sim=ReferenceSimulation()
    sim.command("greeting_demo")
    sim.advance(2.)
    paused=sim.command("pause")
    q=sim.data.qpos.copy()
    frozen=sim.advance(2.)
    assert np.array_equal(q,sim.data.qpos)
    assert frozen["metrics"]["demo"]==paused["metrics"]["demo"]
    sim.command("pause")
    for _ in range(7):
        state=sim.advance(2.)
    assert state["metrics"]["demo"]["complete"]
    sim.data.qpos[sim.model.joint("base_x").qposadr[0]]=1.15
    mujoco.mj_forward(sim.model,sim.data)
    fault=sim.advance(.002)
    assert fault["paused"]
    assert not fault["metrics"]["demo"]["complete"]
    assert fault["metrics"]["demo"]["status"]=="stopped"
    with pytest.raises(ValueError,match="Reset the scene after"):
        sim.command("greeting_demo")
    reset=sim.command("reset")
    assert "demo" not in reset["metrics"]
    assert reset["simulation_time"]==0


def test_shared_library_is_model_bound_and_commands_require_baseline():
    sim=ReferenceSimulation()
    library=load_trajectories(sim.metadata["model_hash"])
    assert library["nq"]==sim.model.nq
    assert library["nu"]==sim.model.nu
    assert library["actuated_q_indices"]==sim.actuated_q.tolist()
    with pytest.raises(ValueError,match="model hash mismatch"):
        load_trajectories("different-model")
    sim.command("joint_demo")
    sim.advance(1.)
    before=sim.data.qpos.copy()
    for command in library["commands"]:
        with pytest.raises(ValueError,match="Reset the scene before"):
            sim.command(command)
        assert np.array_equal(before,sim.data.qpos)
    json.dumps(library,allow_nan=False)


def test_shared_demo_requires_explicit_reset_before_switching():
    sim=ReferenceSimulation()
    sim.command("bedside_demo")
    before=sim.data.qpos.copy()
    for command in ("joint_demo", "greeting_demo", "phone_return_demo"):
        with pytest.raises(ValueError,match="Reset the scene before"):
            sim.command(command)
        assert np.array_equal(before,sim.data.qpos)
    assert sim.command("pause")["paused"]
    assert sim.command("reset")["mode"]=="idle"
    assert sim.command("greeting_demo")["mode"]=="greeting_demo"


def test_demo_commands_expose_complete_metrics_through_local_api(tmp_path):
    from importlib import import_module
    from fastapi.testclient import TestClient

    app_module=import_module("services.app")
    client=TestClient(app_module.create_app(tmp_path/"demo-api.sqlite3",demo=True))
    assert client.post("/api/session",json={"role":"researcher"}).status_code==200
    for command in ("bedside_demo", "greeting_demo", "phone_return_demo"):
        client.post("/api/sim/reference/control",json={"command":"reset"})
        response=client.post("/api/sim/reference/control",json={"command":command})
        assert response.status_code==200,response.text
        state=response.json()
        metrics=state["metrics"]["demo"]
        assert metrics["command"]==command
        assert metrics["stage_index"]==0
        assert metrics["stage_count"]>1
        assert metrics["elapsed_s"]==0
        assert metrics["duration_s"]>0
        assert not metrics["complete"]
        assert metrics["status"]=="running"
        assert metrics["checks"]
        assert state["authorizes_hardware"] is False
