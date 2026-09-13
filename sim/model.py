"""Parametric MJCF, with deliberately synthetic dimensions and dynamics."""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

SURROGATE_METADATA = {
    "name": "vela_dual_arm_surrogate_v1",
    "hardware_model_verified": False,
    "authorizes_hardware": False,
    "source": "Topology from supplied Bracket Bot summaries; all numeric geometry, inertia, calibration and control parameters below are synthetic engineering fixtures.",
    "confirmed_topology": ["mobile base", "dual seven-DOF arms", "vertical stage", "two grippers", "head stereo and wrist views"],
    "unsupported_claims": ["hardware reachability", "payload certification", "patient clearance certification", "cloth fidelity", "vendor control compatibility"],
}


def _element(parent, tag, **attrs):
    return ET.SubElement(parent, tag, {key: str(value) for key, value in attrs.items()})


def build_scene(seed: int = 7, clutter: int = 3, robot_xy=(0.0, 0.0), table_height: float = .72, **unused) -> tuple[str, dict]:
    """Create a deterministic room hypothesis. Values are simulator-only, SI units."""
    rng = np.random.default_rng(seed)
    if not 0 <= clutter <= 30 or not .45 <= table_height <= 1.1:
        raise ValueError("Scene parameters outside the synthetic generator range")
    root = ET.Element("mujoco", model="UNVERIFIED_VELA_SURROGATE")
    _element(root, "compiler", angle="radian", autolimits="true")
    _element(root, "option", timestep="0.002", gravity="0 0 -9.81", integrator="implicitfast")
    visual = _element(root, "visual")
    _element(visual, "global", offwidth="960", offheight="640")
    default = _element(root, "default")
    _element(default, "joint", damping="3", armature="0.02")
    _element(default, "geom", friction=".8 .01 .001", density="450", condim="3", solref=".01 1")
    _element(default, "position", kp="100", kv="15")
    asset = _element(root, "asset")
    _element(asset, "texture", name="tiles", type="2d", builtin="checker", rgb1=".83 .87 .88", rgb2=".91 .93 .94", width="256", height="256")
    _element(asset, "material", name="floor_material", texture="tiles", texrepeat="8 8", reflectance=".03")
    world = _element(root, "worldbody")
    _element(world, "light", name="ceiling", pos="1 0 5", dir="0 0 -1", diffuse=f"{rng.uniform(.65,.95):.3f} .85 .85")
    _element(world, "geom", name="floor", type="plane", size="4 3 .1", material="floor_material")
    _element(world, "camera", name="overview", pos="4 -5 4", xyaxes=".78 .62 0 -.35 .44 .83")
    _element(world, "geom", name="wall_back", type="box", pos="0 3 1.5", size="4 .08 1.5", rgba=".86 .9 .91 1")
    _element(world, "geom", name="wall_side", type="box", pos="-4 0 1.5", size=".08 3 1.5", rgba=".86 .9 .91 1")
    base = _element(world, "body", name="robot_base", pos=f"{robot_xy[0]} {robot_xy[1]} .20")
    for name, axis in (("base_x", "1 0 0"), ("base_y", "0 1 0")):
        _element(base, "joint", name=name, type="slide", axis=axis, range="-3 3", damping="20")
    _element(base, "joint", name="base_yaw", axis="0 0 1", range="-3.14 3.14", damping="10")
    _element(base, "geom", name="base_collision", type="box", size=".24 .25 .18", mass="28", rgba=".12 .20 .24 1")
    for sign in (-1, 1):
        _element(base, "geom", name=f"wheel_{sign}", type="cylinder", pos=f"0 {sign*.28} -.03", euler="1.5708 0 0", size=".14 .035", contype="0", conaffinity="0", rgba=".07 .08 .09 1")
    _element(base, "geom", name="mast", type="box", pos="-.1 0 .5", size=".08 .1 .5", rgba=".23 .29 .32 1")
    shoulder = _element(base, "body", name="shoulder_stage", pos="0 0 .63", gravcomp="1")
    _element(shoulder, "joint", name="lift", type="slide", axis="0 0 1", range="0 .5", damping="20")
    _element(shoulder, "geom", name="shoulder_bar", type="box", size=".1 .3 .07", mass="3", rgba=".83 .88 .9 1")
    _element(shoulder, "geom", name="head", type="box", pos="0 0 .2", size=".1 .15 .045", mass=".5", rgba=".12 .2 .24 1")
    for name, y in (("head_rgb", .035), ("head_stereo_right", -.035)):
        _element(shoulder, "camera", name=name, pos=f".12 {y} .2", xyaxes="0 -1 0 0 0 1", fovy="90")
    joint_names = ["base_x", "base_y", "base_yaw", "lift"]
    axes = ["0 0 1", "0 1 0", "1 0 0", "0 1 0", "1 0 0", "0 1 0", "0 0 1"]
    lengths = [.11, .17, .10, .16, .09, .08, .06]
    for side, sign, color in (("left", 1, ".15 .65 .65 1"), ("right", -1, ".23 .42 .68 1")):
        parent = shoulder
        for i, (axis, length) in enumerate(zip(axes, lengths)):
            position = f"0 {sign*.35} 0" if i == 0 else f"{lengths[i-1]} 0 0"
            parent = _element(parent, "body", name=f"{side}_link_{i+1}", pos=position, gravcomp="1")
            joint_name = f"{side}_joint_{i+1}"
            joint_names.append(joint_name)
            _element(parent, "joint", name=joint_name, axis=axis, range="-2.6 2.6")
            _element(parent, "geom", name=f"{side}_collision_{i+1}", type="capsule", fromto=f"0 0 0 {length} 0 0", size=".027", mass=str(.45 if i < 4 else .2), rgba=color)
        hand = _element(parent, "body", name=f"{side}_hand", pos=f"{lengths[-1]} 0 0", gravcomp="1")
        _element(hand, "geom", name=f"{side}_palm", type="box", size=".035 .045 .03", mass=".2", rgba=".18 .22 .25 1")
        _element(hand, "site", name=f"{side}_ee", pos=".09 0 0", size=".015", rgba=".95 .65 .2 1")
        _element(hand, "camera", name=f"{side}_wrist", pos="-.015 0 .06", xyaxes="0 -1 0 .4 0 .9165", fovy="80")
        for finger_sign in (-1, 1):
            finger = _element(hand, "body", name=f"{side}_finger_{finger_sign}", pos=f".015 {finger_sign*.045} 0", gravcomp="1")
            joint_name = f"{side}_gripper_{finger_sign}"
            joint_names.append(joint_name)
            _element(finger, "joint", name=joint_name, axis="0 0 1", range="-.5 .5", damping="1")
            _element(finger, "geom", name=f"{side}_finger_geom_{finger_sign}", type="box", pos=".04 0 0", size=".04 .01 .02", mass=".08", rgba=".18 .22 .25 1")
    # Every furniture item is a synthetic box/cylinder proxy, not vendor geometry.
    def box(name, pos, size, color=".65 .7 .75 1"):
        _element(world, "geom", name=name, type="box", pos=" ".join(map(str, pos)), size=" ".join(map(str, size)), rgba=color)
    box("clinical_bed_obstacle", (-1.2, 1.3, .55), (.6, 1.05, .22), ".84 .86 .88 1")
    box("bed_head", (-1.2, 2.25, .9), (.63, .05, .55))
    table_x = float(rng.uniform(1.18, 1.32))
    box("bedside_table", (table_x, 0, table_height-.04), (.33, .48, .04), ".71 .60 .46 1")
    for y in (-.4, .4):
        box(f"table_leg_{y}", (table_x, y, table_height/2), (.035, .035, table_height/2))
    box("overbed_tray", (-.15, 1.3, .96), (.38, .5, .035))
    box("visitor_chair", (2, 1.6, .46), (.28, .28, .08), ".27 .53 .58 1")
    box("visitor_chair_back", (2, 1.86, .75), (.28, .04, .3), ".27 .53 .58 1")
    box("wheelchair_proxy", (-2.7, -.4, .5), (.35, .42, .45))
    box("cart_proxy", (2.5, -.9, .5), (.34, .44, .42))
    box("cabinet", (2.8, 2.3, .8), (.45, .35, .8), ".72 .63 .5 1")
    drawer = _element(world, "body", name="safe_drawer", pos="2.8 1.91 1.0")
    _element(drawer, "joint", name="drawer_slide", type="slide", axis="0 -1 0", range="0 .3")
    _element(drawer, "geom", name="drawer_front", type="box", size=".38 .03 .13", mass="1", rgba=".6 .52 .42 1")
    _element(drawer, "geom", name="drawer_handle", type="capsule", fromto="-.12 -.05 0 .12 -.05 0", size=".015", mass=".04")
    door = _element(world, "body", name="door", pos="-3.2 -2.6 1")
    _element(door, "joint", name="door_hinge", axis="0 0 1", range="0 1.5")
    _element(door, "geom", name="door_panel", type="box", pos=".45 0 0", size=".45 .03 1", mass="8", rgba=".65 .54 .4 1")
    masses = {}
    for idx in range(clutter+1):
        name = "phone" if idx == 0 else f"clutter_{idx}"
        x, y = table_x+rng.uniform(-.2, .2), rng.uniform(-.3, .3)
        body = _element(world, "body", name=name, pos=f"{x} {y} {table_height+.025+idx*.045}")
        _element(body, "freejoint", name=f"{name}_free")
        mass = float(rng.uniform(.08, .3))
        masses[name] = mass
        _element(body, "geom", name=f"{name}_geom", type="box", size=".065 .033 .014" if idx == 0 else ".035 .035 .03", mass=str(mass), friction=f"{rng.uniform(.45,1.1)} .01 .001", rgba=".13 .17 .22 1" if idx == 0 else ".83 .57 .22 1")
    bag = _element(world, "body", name="bag_rigid_proxy", pos="1.2 -.3 .9")
    _element(bag, "freejoint", name="bag_free")
    _element(bag, "geom", name="bag_geom", type="box", size=".08 .045 .07", mass=".2", rgba=".5 .33 .25 1")
    actuator = _element(root, "actuator")
    for name in joint_names:
        limits = "0 .5" if name == "lift" else ("-.5 .5" if "gripper" in name else ("-3 3" if name.startswith("base") else "-2.6 2.6"))
        _element(actuator, "position", name=f"ctrl_{name}", joint=name, ctrlrange=limits, forcerange="-150 150", kp="500" if name in ("lift", "base_x", "base_y") else "100")
    xml = ET.tostring(root, encoding="unicode")
    metadata = {**SURROGATE_METADATA, "seed": seed, "clutter": clutter, "table_height_m": table_height, "table_x_m": table_x, "sampled_object_masses_kg": masses, "model_hash": hashlib.sha256(xml.encode()).hexdigest(), "actuated_joints": joint_names}
    return xml, metadata


def write_scene(directory: str | Path, seed: int = 7, **kwargs) -> dict:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    xml, metadata = build_scene(seed, **kwargs)
    (directory / "scene.xml").write_text(xml, encoding="utf-8")
    (directory / "model_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata
