"""Reproduce native visual verification without modifying source scene assets.

    python -m sim.reference_visual_check
    python -m sim.reference_visual_check --render
    python -m sim.reference_visual_check --dynamics

Rendering needs an OpenGL context. Full dynamics runs three complete physical
demonstrations; the default only verifies the compiled scene and initial state.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time

import mujoco
import numpy as np

from sim.reference_model import load_reference_model
from sim.reference_visual_model import (
    COLLISION_GROUP, ENCLOSURE_GROUP, VISUAL_GROUP,
    _assert_physics_parity, load_reference_visual_model,
)

CAMERAS = ("head_rgb", "head_stereo_right", "left_wrist", "right_wrist")
DYNAMICS = {"phone_return_demo": None, "deliver_meal_demo": None, "blinds_demo": None}


def check_static(model, data, metadata):
    reference, reference_data, reference_metadata = load_reference_model()
    _assert_physics_parity(reference, model)
    errors = {}
    for field in ("qpos", "qvel", "ctrl", "mocap_pos", "mocap_quat", "xpos", "xquat", "cam_xpos", "cam_xmat"):
        delta = np.abs(getattr(data, field)-getattr(reference_data, field))
        errors[field] = float(np.max(delta, initial=0.))
    passed = metadata["model_hash"] == reference_metadata["model_hash"] and max(errors.values()) <= 1e-12
    return {"passed": passed, "physics_model_hash": metadata["model_hash"],
            "visual_hash": metadata["visual_hash"], "initial_state_max_errors": errors,
            "reference_geoms": reference.ngeom, "detailed_geoms": model.ngeom,
            "detailed_meshes": model.nmesh, "physics_parity_verified": True,
            "visual_source_regeneration_verified": False,
            "visual_limitations": metadata["visual_limitations"]}


def render_report(model, data, metadata, directory):
    """Render the same overview, face and four optical views used for review."""
    from PIL import Image

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {}
    option = mujoco.MjvOption()
    option.geomgroup[VISUAL_GROUP] = 1
    option.geomgroup[COLLISION_GROUP] = 0
    option.sitegroup[:] = 0
    with mujoco.Renderer(model, width=1280, height=800) as renderer:
        for name in ("overview", "patient", *CAMERAS):
            option.geomgroup[ENCLOSURE_GROUP] = int(name in CAMERAS)
            camera = name
            if name in {"overview", "patient"}:
                camera = mujoco.MjvCamera()
                camera.type = mujoco.mjtCamera.mjCAMERA_FREE
                if name == "overview":
                    camera.lookat[:] = [.2, .6, 1.]
                    camera.distance, camera.azimuth, camera.elevation = 7., 135., -22.
                else:
                    camera.lookat[:] = [1.4, 2.04, 1.16]
                    camera.distance, camera.azimuth, camera.elevation = .75, 90., -50.
            renderer.update_scene(data, camera=camera, scene_option=option)
            path = directory/f"native-detailed-{name}.png"
            Image.fromarray(renderer.render()).save(path)
            paths[name] = str(path)
    report = {"model_hash": metadata["model_hash"], "visual_hash": metadata["visual_hash"],
              "visual_assets": metadata["visual_assets"], "renders": paths,
              "renderer": "MuJoCo native OpenGL", "width": 1280, "height": 800,
              "limitations": metadata["visual_limitations"], "authorizes_hardware": False}
    (directory/"native-detailed-render.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def check_dynamics(directory, *, tolerance=1e-12):
    """Compare independently stepped runtimes at fixed 0.5 s intervals."""
    from sim.reference_runtime import ReferenceSimulation

    started = time.perf_counter()
    comparisons = {}
    metadata = None
    for command, duration in DYNAMICS.items():
        reference = ReferenceSimulation()
        detailed = ReferenceSimulation(loader=load_reference_visual_model)
        metadata = detailed.metadata
        initial_state = reference.command(command)
        detailed.command(command)
        if duration is None:
            duration = (math.ceil(initial_state["metrics"]["demo"]["duration_s"]*2)+1)/2
        qpos_error = qvel_error = 0.
        sample_count = 0
        elapsed = 0.
        states = None
        while elapsed < duration-1e-9:
            increment = min(.5, duration-elapsed)
            states = reference.advance(increment), detailed.advance(increment)
            qpos_error = max(qpos_error, float(np.max(np.abs(reference.data.qpos-detailed.data.qpos))))
            qvel_error = max(qvel_error, float(np.max(np.abs(reference.data.qvel-detailed.data.qvel))))
            sample_count += 1
            elapsed += increment
            if reference.stop_reason or detailed.stop_reason:
                break
        original, visual = states
        original_complete = bool(original["metrics"].get("demo", {}).get("complete"))
        visual_complete = bool(visual["metrics"].get("demo", {}).get("complete"))
        comparisons[command] = {
            "passed": original_complete and visual_complete and not reference.stop_reason and not detailed.stop_reason and qpos_error <= tolerance and qvel_error <= tolerance,
            "max_qpos_error": qpos_error, "max_qvel_error": qvel_error,
            "physics_steps": detailed.step_count, "samples": sample_count,
            "simulation_time_s": float(detailed.data.time),
            "reference_complete": original_complete, "detailed_complete": visual_complete,
            "reference_stop": reference.stop_reason, "detailed_stop": detailed.stop_reason,
            "detailed_outcomes": visual["metrics"].get("demo", {}).get("measurements", {}),
        }
    report = {"passed": all(item["passed"] for item in comparisons.values()),
              "physics_model_hash": metadata["model_hash"], "visual_hash": metadata["visual_hash"],
              "elapsed_s": time.perf_counter()-started, "comparison_interval_s": .5,
              "numeric_tolerance": tolerance, "comparisons": comparisons,
              "authorizes_hardware": False}
    path = Path(directory)/"native-detailed-dynamics-parity.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--render", action="store_true", help="Save six native OpenGL reference views")
    parser.add_argument("--dynamics", action="store_true", help="Run complete phone return, meal delivery and blinds comparisons")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    args = parser.parse_args(argv)
    model, data, metadata = load_reference_visual_model()
    report = check_static(model, data, metadata)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.render:
        report["render_report"] = render_report(model, data, metadata, args.output_dir)
    if args.dynamics:
        report["dynamics"] = check_dynamics(args.output_dir)
        report["passed"] = report["passed"] and report["dynamics"]["passed"]
    path = args.output_dir/"native-detailed-check.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "report": str(path), "visual_hash": metadata["visual_hash"]}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
