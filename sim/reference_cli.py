"""Export and native rendering for the current detailed reference scene."""
from __future__ import annotations

import json
from pathlib import Path

import mujoco

from sim.viewer_live import SENSOR_CAMERAS


def _load(loader):
    if loader is None:
        from sim.reference_visual_model import load_reference_visual_model
        loader = load_reference_visual_model
    return loader()


def generate_reference_scene(output, *, loader=None):
    model, data, metadata = _load(loader)
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=True)
    binary = directory / "reference.mjb"
    mujoco.mj_saveModel(model, str(binary), None)
    result = {**metadata, "model_binary": str(binary), "model_family": "current_reference", "seeded": False,
              "initial_qpos": data.qpos.tolist(), "initial_ctrl": data.ctrl.tolist(),
              "initial_mocap_pos": data.mocap_pos.tolist(), "initial_mocap_quat": data.mocap_quat.tolist(),
              "initialization_note": "Restore these initial arrays and call mj_forward after creating MjData; raw MJB alone does not store MjData state."}
    (directory / "reference-metadata.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def render_reference_scene(path, camera="overview", *, loader=None):
    from PIL import Image
    model, data, metadata = _load(loader)
    if camera not in ("overview", *SENSOR_CAMERAS):
        raise ValueError("Camera must be overview, head_rgb, head_stereo_right, left_wrist, or right_wrist")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    sensor = camera in SENSOR_CAMERAS
    width, height = (320, 240) if sensor else (1280, 800)
    option = mujoco.MjvOption()
    option.geomgroup[2] = 1
    option.geomgroup[3] = 0
    option.geomgroup[4] = sensor
    option.sitegroup[:] = 0
    with mujoco.Renderer(model, height=height, width=width) as renderer:
        renderer.update_scene(data, camera=camera, scene_option=option)
        Image.fromarray(renderer.render()).save(output)
    return {"path": str(output), "image": str(output), "camera": camera, "width": width, "height": height,
            "model_hash": metadata["model_hash"], "visual_hash": metadata.get("visual_hash"),
            "model_family": "current_reference", "renderer": "MuJoCo native", "hardware_model_verified": False,
            "authorizes_hardware": False}
