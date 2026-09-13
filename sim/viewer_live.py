"""Interactive native MuJoCo viewer for the explicitly synthetic Vela robot."""
from __future__ import annotations

import json
import math
from pathlib import Path
import threading
import time

import mujoco
import mujoco.viewer
import numpy as np

from sim.engine import load_scene, robot_contacts


def apply_demo_controls(model, data, seconds):
    """Small repeatable arm/lift motion; not a retrieval or learned policy."""
    phase = (1 - math.cos(seconds*.65))/2
    for side, sign in (("left",1),("right",-1)):
        data.ctrl[model.actuator(f"ctrl_{side}_joint_1").id] = sign*.12*phase
    data.ctrl[model.actuator("ctrl_lift").id] = .12*phase


def run_viewer(seed=7, ready_path=None):
    model,data,metadata = load_scene(seed=seed)
    initial_qpos = data.qpos.copy()
    initial_ctrl = data.ctrl.copy()
    state = {"paused":False,"motion":True,"reset":False,"camera":-1,"changed_camera":False,"stop_reason":None}
    state_lock = threading.Lock()

    def key_callback(key):
        with state_lock:
            if key == 32:
                state["paused"] = not state["paused"]
            elif key in (ord("M"),ord("m")):
                state["motion"] = not state["motion"]
            elif key in (ord("R"),ord("r")):
                state["reset"] = True
            elif key in (ord("C"),ord("c")):
                state["camera"] = (state["camera"]+2) % (model.ncam+1)-1
                state["changed_camera"] = True

    with mujoco.viewer.launch_passive(model,data,key_callback=key_callback,show_left_ui=True,show_right_ui=False) as viewer:
        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        viewer.cam.lookat[:] = [.3,.3,.75]
        viewer.cam.distance = 7
        viewer.cam.azimuth = 135
        viewer.cam.elevation = -28
        if ready_path:
            Path(ready_path).write_text(json.dumps({"status":"opened","model_hash":metadata["model_hash"],"hardware_model_verified":False}),encoding="utf-8")
        while viewer.is_running():
            started = time.monotonic()
            with viewer.lock(),state_lock:
                if state["reset"]:
                    mujoco.mj_resetData(model,data)
                    data.qpos[:] = initial_qpos
                    data.ctrl[:] = initial_ctrl
                    mujoco.mj_forward(model,data)
                    state.update(reset=False,paused=False,stop_reason=None)
                if state["changed_camera"]:
                    viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE if state["camera"] < 0 else mujoco.mjtCamera.mjCAMERA_FIXED
                    viewer.cam.fixedcamid = state["camera"]
                    state["changed_camera"] = False
                if not state["paused"]:
                    # Run eight actual 2-ms physics steps per display frame.
                    for _ in range(8):
                        if state["motion"]:
                            apply_demo_controls(model,data,data.time)
                        mujoco.mj_step(model,data)
                        if robot_contacts(model,data) or not np.isfinite(data.qpos).all():
                            state["paused"] = True
                            state["stop_reason"] = "Contact/nonfinite state detected; press R to reset"
                            break
                label = "PAUSED" if state["paused"] else "RUNNING"
                camera_label = "Orbit view" if state["camera"] < 0 else model.camera(state["camera"]).name
                message = state["stop_reason"] or "Small arm + lift motion; no grasp/VLA demonstration"
                simulation_time = float(data.time)
            viewer.set_texts((mujoco.mjtFontScale.mjFONTSCALE_100,mujoco.mjtGridPos.mjGRID_TOPRIGHT,
                "VELA | 3D MuJoCo simulation\nUNVERIFIED synthetic robot\n"+label+f" | {simulation_time:.1f}s | "+camera_label+"\n"+message+"\n\nMouse drag: orbit | Wheel: zoom\nSpace: pause | M: motion on/off\nR: reset | C: cycle head/wrist views", ""))
            viewer.sync()
            time.sleep(max(0,.016-(time.monotonic()-started)))

