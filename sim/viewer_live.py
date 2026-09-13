"""Native detailed scene using the same reference controller as the browser."""
from __future__ import annotations

from collections import deque
import json
import math
from pathlib import Path
import threading
import time

import mujoco
import mujoco.viewer

from sim.reference_runtime import ReferenceSimulation
from sim.reference_viewer_client import ReferenceViewerClient, apply_reference_frame

DEMO_KEYS = {
    "1": ("joint_demo", "Joint movement"), "2": ("reach_demo", "Table reach"),
    "3": ("pickup_demo", "Phone pickup"), "4": ("lift_demo", "Vertical travel"),
    "5": ("bedside_demo", "Bedside approach"), "6": ("greeting_demo", "Greeting"),
    "7": ("phone_return_demo", "Pick up + put back"),
    "8": ("deliver_phone_demo", "Deliver phone"), "9": ("deliver_meal_demo", "Deliver meal"),
    "0": ("blinds_demo", "Open blinds"),
}
SENSOR_CAMERAS = ("head_rgb", "head_stereo_right", "left_wrist", "right_wrist")


class ViewerInput:
    """GLFW's callback enqueues bounded inputs; the simulation thread applies them."""
    def __init__(self):
        self.lock = threading.Lock()
        self.keys = deque(maxlen=32)
        self.camera = -1
        self.collisions = False
        self.help = False
        self.overview_requested = False
        self.display_error = None
        self.message = "Ready"

    def key_callback(self, key):
        with self.lock:
            self.keys.append(key)

    def process(self, command):
        with self.lock:
            keys = list(self.keys)
            self.keys.clear()
        for code in keys:
            key = chr(code).upper() if 0 <= code <= 127 else ""
            try:
                if key in DEMO_KEYS:
                    action, label = DEMO_KEYS[key]
                    command("reset")
                    command(action)
                    self.message = f"Reset + run: {label}"
                elif key in {" ", "R", "F"}:
                    action = {" ": "pause", "R": "reset", "F": "release_phone"}[key]
                    command(action)
                    self.message = {" ": "Playback toggled", "R": "Simulation reset", "F": "Grippers opening under physics"}[key]
                elif key == "C":
                    self.camera = (self.camera + 2) % (len(SENSOR_CAMERAS) + 1) - 1
                elif key == "V":
                    self.collisions = not self.collisions
                elif key == "H":
                    self.help = not self.help
                elif key == "O":
                    self.camera = -1
                    self.overview_requested = True
            except Exception as error:
                self.message = str(error)


def configure_view(viewer, model, controls):
    fixed = controls.camera >= 0
    viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED if fixed else mujoco.mjtCamera.mjCAMERA_FREE
    viewer.cam.fixedcamid = model.camera(SENSOR_CAMERAS[controls.camera]).id if fixed else -1
    viewer.opt.geomgroup[2] = not controls.collisions
    viewer.opt.geomgroup[3] = controls.collisions
    viewer.opt.geomgroup[4] = fixed and not controls.collisions
    viewer.opt.sitegroup[:] = 0


def set_overview_camera(viewer, model, data):
    """Make the free/orbit camera match the authored fixed overview exactly."""
    camera = model.camera("overview").id
    forward = -data.cam_xmat[camera].reshape(3, 3)[:, 2]
    viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    viewer.cam.fixedcamid = -1
    viewer.cam.distance = 5.6
    viewer.cam.lookat[:] = data.cam_xpos[camera] + viewer.cam.distance * forward
    viewer.cam.azimuth = math.degrees(math.atan2(forward[1], forward[0]))
    viewer.cam.elevation = math.degrees(math.asin(float(forward[2])))


def initialize_view(viewer, model, data, controls):
    # The first native synchronization initializes its scene/camera. Set our
    # authored overview afterward so that initialization cannot replace it.
    viewer.sync()
    with viewer.lock():
        set_overview_camera(viewer, model, data)
        configure_view(viewer, model, controls)
    viewer.sync()


def viewer_text(state, controls, attached):
    metrics = state["metrics"]
    status = "DISPLAY FROZEN" if controls.display_error else "STOPPED" if metrics.get("stop_reason") else "PAUSED" if state["paused"] else "RUNNING" if state["mode"] != "idle" else "READY"
    camera = "Orbit" if controls.camera < 0 else SENSOR_CAMERAS[controls.camera]
    message = controls.display_error or metrics.get("stop_reason") or controls.message
    demo = metrics.get("demo")
    if demo and not (metrics.get("stop_reason") or controls.display_error):
        message = f"{demo['name']}: {demo['stage']} | {demo['status']} | {demo['progress']:.0%}"
    source = "SHARED browser session" if attached else "STANDALONE session"
    result = ("VELA | MuJoCo | unverified model, no hardware\n"
              + f"{source} | {status} | {state['simulation_time']:.2f} s\n"
              + f"{camera}{' / collisions' if controls.collisions else ''} | {message}\n"
              + "Space pause | R reset | C cameras | O room | H help")
    if controls.help:
        result += ("\n\nMouse: orbit/zoom | V: visual/collision geometry | F: release held phone\n"
                   + "RESET + RUN: 1 joints | 2 reach | 3 pickup | 4 vertical travel\n"
                   + "5 bedside | 6 greeting | 7 put back | 8 phone delivery | 9 meal | 0 blinds\n"
                   + "Estimated robot/physics; synthetic patient. No hardware connected.\n"
                   + ("Attached to the same local API session as browser.\n" if attached else "Independent local simulation; no shared browser clock.\n")
                   + "Native RGB renderer; visual SLAM runs in the browser panel.")
    return result


def run_viewer(seed=7, ready_path=None, *, connect=None, loader=None):
    # Keep seed in the launcher signature, but this reference fixture is fixed.
    if loader is None:
        from sim.reference_visual_model import load_reference_visual_model
        loader = load_reference_visual_model
    simulation = ReferenceSimulation(loader=loader)
    model, data = simulation.model, simulation.data
    client = ReferenceViewerClient(connect) if connect else None
    controls = ViewerInput()
    initial_frame = client.frame() if client else None
    if initial_frame is not None:
        state = apply_reference_frame(model, data, simulation.metadata, initial_frame)
    else:
        state = simulation.advance(0.)
    with mujoco.viewer.launch_passive(model, data, key_callback=controls.key_callback, show_left_ui=False, show_right_ui=False) as viewer:
        initialize_view(viewer, model, data, controls)
        if ready_path:
            path = Path(ready_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"status": "opened", "mode": "native_mujoco", "session": "attached" if client else "standalone", "model_hash": simulation.metadata["model_hash"], "visual_hash": simulation.metadata.get("visual_hash"), "camera": {"lookat": viewer.cam.lookat.tolist(), "distance": viewer.cam.distance, "azimuth": viewer.cam.azimuth, "elevation": viewer.cam.elevation}, "hardware_model_verified": False}), encoding="utf-8")
        while viewer.is_running():
            started = time.monotonic()
            frame = None
            if client:
                controls.process(client.command)
                try:
                    frame = client.frame()
                except Exception as error:
                    controls.display_error = f"API disconnected: {error}. No local physics is running."
            with viewer.lock():
                if client:
                    if frame is not None:
                        try:
                            state = apply_reference_frame(model, data, simulation.metadata, frame)
                            controls.display_error = None
                        except ValueError as error:
                            controls.display_error = f"Frame rejected: {error}"
                else:
                    controls.process(simulation.command)
                    state = simulation.advance(.016)
                if controls.overview_requested:
                    set_overview_camera(viewer, model, data)
                    controls.overview_requested = False
                configure_view(viewer, model, controls)
                text = viewer_text(state, controls, bool(client))
            viewer.set_texts((mujoco.mjtFontScale.mjFONTSCALE_100, mujoco.mjtGridPos.mjGRID_BOTTOMLEFT, text, ""))
            viewer.sync()
            time.sleep(max(0., .016 - (time.monotonic() - started)))
    return {"status": "closed", "mode": "native_mujoco", "session": "attached" if client else "standalone", "model_hash": simulation.metadata["model_hash"], "visual_hash": simulation.metadata.get("visual_hash"), "hardware_model_verified": False}

