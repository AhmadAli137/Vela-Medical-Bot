"""Reference-informed visual/kinematic surrogate, isolated from vendor hardware.

The supplied original handout and video frames establish morphology/topology.
Metric dimensions, joint axes/ranges, dynamics and calibration here are visual
estimates, deliberately exposed in one editable descriptor list.
"""
from __future__ import annotations

import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco

BASE_POSITION = [-.6, -.7, .13]
LINK_LENGTHS = [.085, .19, .08, .18, .065, .065, .035]
LINK_RADII = [.041, .041, .032, .036, .030, .026, .023]
JOINT_AXES = [[0, 0, 1], [0, 1, 0], [0, 0, 1], [0, 1, 0], [0, 0, 1], [0, 1, 0], [0, 0, 1]]
INITIAL_ARM_Q = [0., -.30, 0., -1.50, 0., -.15, 0.]
PHONE_POSITION = [.63, -.72, .814]
PHONE_DIMENSIONS = [.082, .158, .012]
MEAL_POSITION = [.63, -.45, .828]
MEAL_DIMENSIONS = [.082, .130, .040]
TRAY_POSITION = [.85, 1.40, .99]
TRAY_DIMENSIONS = [.60, .64, .045]
DELIVERY_TARGETS = {"phone": [.85, 1.48, 1.0535], "meal_box": [.85, 1.22, 1.0675]}
BLINDS_HANDLE_POSITION = [-3.14, -.40, 1.18]
BLINDS_TRAVEL = .18
LIFT_RANGE = [-.72, .20]
ROOM_COLLIDERS = [
    {"name": "wall_right", "pos": [3.55,0.,1.5], "size": [.05,3.05,1.5]},
    {"name": "wall_front", "pos": [0.,-3.05,1.5], "size": [3.5,.05,1.5]},
    {"name": "ceiling", "pos": [0.,0.,3.05], "size": [3.5,3.,.05]},
    {"name": "work_table", "pos": [.75, -.7, .75], "size": [.40, .40, .0225]},
    {"name": "phone_riser", "pos": [.63, -.72, .790], "size": [.025, .060, .0175]},
    {"name": "meal_riser", "pos": [.63, -.45, .790], "size": [.025, .045, .0175]},
    {"name": "bedside_tray", "pos": TRAY_POSITION, "size": [v/2 for v in TRAY_DIMENSIONS]},
    {"name": "bedside_tray_column", "pos": [.61,1.40,.45], "size": [.0325,.0375,.375]},
    {"name": "bedside_tray_telescope", "pos": [.61,1.40,.865], "size": [.0215,.026,.105]},
    {"name": "bedside_tray_foot_front", "pos": [.85,1.15,.10], "size": [.27,.025,.025]},
    {"name": "bedside_tray_foot_back", "pos": [.85,1.65,.10], "size": [.27,.025,.025]},
    {"name": "phone_delivery_riser", "pos": [.85, 1.48, 1.03], "size": [.025, .060, .0175]},
    {"name": "meal_delivery_riser", "pos": [.85, 1.22, 1.03], "size": [.025, .045, .0175]},
    {"name": "bed", "pos": [1.4, 1.43, .67], "size": [.525, 1.08, .075]},
    {"name": "bed_mattress", "pos": [1.4, 1.43, .81], "size": [.495, 1.04, .075]},
    {"name": "cabinet", "pos": [2.62, 2.30, .39], "size": [.26, .26, .375]},
    {"name": "wardrobe", "pos": [-2.435, 2.60, 1.12], "size": [.625, .36, 1.12]},
    {"name": "visitor_chair", "pos": [-1.60, 1.30, .49], "size": [.385, .365, .09]},
    {"name": "visitor_chair_back", "pos": [-1.60, 1.64, .84], "size": [.385, .10, .33]},
    # Fixed conservative occupancy shapes for the resting visual patient.
    # No physiological simulation or clinical interaction is represented.
    {"name": "patient_head", "type": "ellipsoid", "pos": [1.4, 2.11, 1.15], "size": [.115, .14, .14]},
    {"name": "patient_torso", "type": "ellipsoid", "pos": [1.4, 1.70, 1.035], "size": [.24, .35, .17]},
    {"name": "patient_covered_legs", "pos": [1.4, 1.025, .99], "size": [.24, .465, .13]},
]


def _vec(values):
    return " ".join(str(v) for v in values)


def _add(parent, tag, **attrs):
    return ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})


def body_descriptors():
    """Body-local geometry contract for Blender/Three.js world-pose playback."""
    specs = [
        {"name": "robot_base", "parent": "world", "pos": BASE_POSITION, "geometry": "transverse_barrel", "radius": .10, "half_width": .155, "mass": 12.},
        {"name": "left_wheel", "parent": "robot_base", "pos": [0., .20, 0.], "geometry": "wheel", "radius": .13, "width": .055, "axis": [0, 1, 0], "joint": "left_wheel_joint", "range": [-40, 40], "mass": .9},
        {"name": "right_wheel", "parent": "robot_base", "pos": [0., -.20, 0.], "geometry": "wheel", "radius": .13, "width": .055, "axis": [0, 1, 0], "joint": "right_wheel_joint", "range": [-40, 40], "mass": .9},
        {"name": "mast", "parent": "robot_base", "pos": [-.025, 0., .82], "geometry": "slim_mast", "dimensions": [.075, .085, 1.36], "mass": 3.0},
        {"name": "head", "parent": "robot_base", "pos": [.005, 0., 1.54], "geometry": "stereo_head", "dimensions": [.09, .15, .075], "mass": .3},
    ]
    for side, sign in (("left", 1), ("right", -1)):
        specs.append({"name": f"{side}_shoulder", "parent": "robot_base", "pos": [0., sign*.145, 1.15], "geometry": "shoulder_stage", "dimensions": [.083, .08, .23], "joint": f"{side}_lift", "joint_type": "slide", "axis": [0, 0, 1], "range": LIFT_RANGE, "mass": .8})
        for i, (length, radius, axis) in enumerate(zip(LINK_LENGTHS, LINK_RADII, JOINT_AXES), 1):
            specs.append({"name": f"{side}_link_{i}", "parent": f"{side}_shoulder" if i == 1 else f"{side}_link_{i-1}", "pos": [0., 0., -.125] if i == 1 else [0., 0., -LINK_LENGTHS[i-2]], "geometry": "arm_link", "length": length, "radius": radius, "direction": [0, 0, -1], "joint": f"{side}_joint_{i}", "joint_type": "hinge", "axis": axis, "range": [-2.7, 2.7], "initial_q": INITIAL_ARM_Q[i-1], "mass": .28 if i < 5 else .12})
        specs.append({"name": f"{side}_hand", "parent": f"{side}_link_7", "pos": [0., 0., -LINK_LENGTHS[-1]], "geometry": "gripper_palm", "dimensions": [.07, .09, .047], "mass": .17})
        for sign in (-1, 1):
            specs.append({"name": f"{side}_finger_{sign}", "parent": f"{side}_hand", "pos": [0., sign*.040, -.018], "geometry": "rotary_finger", "dimensions": [.026, .015, .067], "joint": f"{side}_gripper_{sign}", "joint_type": "hinge", "axis": [1, 0, 0], "range": [-.65, .65], "initial_q": -sign*.15, "mass": .035})
    for spec in specs:
        spec["robot_body"] = True
    specs.append({"name": "phone", "parent": "world", "pos": PHONE_POSITION, "geometry": "phone", "dimensions": PHONE_DIMENSIONS, "joint": "phone_free", "joint_type": "free", "mass": .18, "dynamic_object": True, "robot_body": False})
    specs.append({"name": "meal_box", "parent": "world", "pos": MEAL_POSITION, "geometry": "meal_container", "dimensions": MEAL_DIMENSIONS, "joint": "meal_box_free", "joint_type": "free", "mass": .12, "dynamic_object": True, "robot_body": False})
    specs.append({"name": "blinds_handle", "parent": "world", "pos": BLINDS_HANDLE_POSITION, "geometry": "blinds_handle", "dimensions": [.11,.10,.05], "joint": "blinds_slide", "joint_type": "slide", "axis": [0,0,-1], "range": [0,BLINDS_TRAVEL], "mass": .08, "robot_body": False, "passive_joint": True})
    for index in range(16):
        specs.append({"name": f"blinds_slat_{index:02}", "parent": "world", "pos": [-3.43,.05,.95+index*.10], "geometry": "blinds_slat", "dimensions": [.018,2.80,.095], "joint": f"blinds_tilt_{index:02}", "joint_type": "hinge", "axis": [0,1,0], "range": [0,1.4], "mass": .025, "robot_body": False, "passive_joint": True})
    return specs


def build_reference_model():
    specs = body_descriptors()
    root = ET.Element("mujoco", model="REFERENCE_INFORMED_UNVERIFIED_BRACKETBOT")
    _add(root, "compiler", angle="radian", autolimits="true")
    _add(root, "option", timestep="0.002", gravity="0 0 -9.81", integrator="implicitfast", iterations="70", noslip_iterations="10", cone="elliptic")
    defaults = _add(root, "default")
    _add(defaults, "joint", damping="2.5", armature=".015")
    _add(defaults, "geom", friction=".7 .015 .001", density="500", solref=".015 1")
    _add(defaults, "position", kp="90", kv="12", forcerange="-45 45")
    visual = _add(root, "visual")
    _add(visual, "global", offwidth="1280", offheight="800")
    world = _add(root, "worldbody")
    _add(world, "light", pos="0 0 3.5", dir="0 0 -1", diffuse=".9 .9 .9")
    _add(world, "geom", name="floor", type="plane", size="3.5 3 .05", rgba=".83 .86 .84 1")
    for collider in ROOM_COLLIDERS:
        _add(world, "geom", name=collider["name"], type=collider.get("type", "box"), pos=_vec(collider["pos"]), size=_vec(collider["size"]), rgba=".65 .69 .7 1")
    _add(world, "geom", name="wall_back", type="box", pos="0 3.05 1.5", size="3.55 .05 1.5", rgba=".88 .9 .88 1")
    _add(world, "camera", name="overview", pos="3 -4 2.5", xyaxes=".75 .66 0 -.27 .31 .91")
    target = _add(world, "body", name="reach_target", mocap="true", pos=".0 -.53 1.07")
    _add(target, "geom", name="reach_target_geom", type="sphere", size=".018", contype="0", conaffinity="0", rgba=".1 .9 .65 .7")
    bodies = {"world": world}
    actuators = []
    for spec in specs:
        node = _add(bodies[spec["parent"]], "body", name=spec["name"], pos=_vec(spec["pos"]), gravcomp="0" if spec.get("dynamic_object") else "1")
        bodies[spec["name"]] = node
        shape = spec["geometry"]
        if spec["name"] == "robot_base":
            for name, axis, limits in (("base_x", "1 0 0", "-2.35 1.1"), ("base_y", "0 1 0", "-.5 2.3"), ("base_yaw", "0 0 1", "-3.2 3.2")):
                _add(node, "joint", name=name, type="hinge" if name.endswith("yaw") else "slide", axis=axis, range=limits, damping="20")
                actuators.append((name, limits, 300, 35, 150))
        if spec.get("joint_type") == "free":
            _add(node, "freejoint", name=spec["joint"])
        elif "joint" in spec:
            joint_attrs = {"damping": ".04", "armature": ".0001"} if "gripper" in spec["joint"] else {}
            if spec.get("passive_joint"):
                joint_attrs = {"damping": ".05", "armature": ".00001", "frictionloss": ".3" if spec["joint"] == "blinds_slide" else ".0001"}
            _add(node, "joint", name=spec["joint"], type=spec.get("joint_type", "hinge"), axis=_vec(spec["axis"]), range=_vec(spec["range"]), **joint_attrs)
            is_lift = spec["joint"].endswith("lift")
            is_gripper = "gripper" in spec["joint"]
            if not spec.get("passive_joint"):
                actuators.append((spec["joint"], _vec(spec["range"]), 350 if is_lift else (3 if is_gripper else 140), 28 if is_lift else (.12 if is_gripper else 14), 100 if is_lift else (.22 if is_gripper else 45)))
        attrs = {"name": f"{spec['name']}_geom", "mass": spec["mass"], "rgba": ".86 .88 .87 1"}
        if shape in {"phone", "meal_container", "rotary_finger"}:
            attrs.update(friction="1.4 .02 .01", condim="6", solref=".006 1", solimp=".95 .99 .001")
        if shape in {"transverse_barrel", "wheel"}:
            _add(node, "geom", type="cylinder", euler=f"{math.pi/2} 0 0", size=_vec([spec["radius"], spec.get("half_width", spec.get("width", .055)/2)]), **{**attrs, **({"contype": "0", "conaffinity": "0", "rgba": ".09 .10 .11 1"} if shape == "wheel" else {})})
        elif shape == "arm_link":
            _add(node, "geom", type="capsule", fromto=f"0 0 0 0 0 {-spec['length']}", size=spec["radius"], **attrs)
        else:
            dims = [v/2 for v in spec["dimensions"]]
            _add(node, "geom", type="box", size=_vec(dims), pos="0 0 -.030" if shape == "rotary_finger" else "0 0 0", **attrs)
        if shape == "gripper_palm":
            side = spec["name"].split("_")[0]
            _add(node, "site", name=f"{side}_ee", pos="0 0 -.09", size=".007", rgba=".2 1 .7 1")
            _add(node, "site", name=f"{side}_grasp_center", pos="0 0 -.048", size=".005", rgba=".2 .6 1 1")
            _add(node, "camera", name=f"{side}_wrist", pos=".046 0 -.008", fovy="75")
        if shape == "stereo_head":
            for name, y in (("head_rgb", .027), ("head_stereo_right", -.027)):
                _add(node, "camera", name=name, pos=f".067 {y} .008", xyaxes="0 -1 0 0 0 1", fovy="90")
    equality = _add(root, "equality")
    for index in range(16):
        _add(equality, "joint", name=f"blinds_linkage_{index:02}", joint1=f"blinds_tilt_{index:02}", joint2="blinds_slide", polycoef=f"0 {1.4/BLINDS_TRAVEL} 0 0 0", solref=".004 1")
    actuator = _add(root, "actuator")
    for name, limits, kp, kv, force in actuators:
        _add(actuator, "position", name=f"ctrl_{name}", joint=name, ctrlrange=limits, kp=kp, kv=kv, forcerange=f"{-force} {force}")
    xml = ET.tostring(root, encoding="unicode")
    metadata = {"name": "reference_informed_bracketbot_surrogate_v2", "reference_files": ["artifacts/references/handout-page-1.png", "artifacts/references/platform-contact-sheet.jpg", "artifacts/references/teleop-contact-sheet.jpg"], "hardware_model_verified": False, "authorizes_hardware": False, "dimensions_status": "visually inferred, adjustable; no vendor CAD/metric calibration", "joint_axes_status": "inferred surrogate; not vendor verified", "coordinate_system": {"up": "+Z", "forward": "+X", "left": "+Y", "quaternion": "wxyz"}, "base_position": BASE_POSITION, "base_motion_model": "constrained planar sliders, separately actuated decorative wheel hinges; not balancing/wheel odometry validation", "body_specs": specs, "room_colliders": ROOM_COLLIDERS, "model_hash": hashlib.sha256(xml.encode()).hexdigest()}
    return xml, metadata


def load_reference_model():
    xml, metadata = build_reference_model()
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    for spec in metadata["body_specs"]:
        if "joint" in spec and spec.get("joint_type") != "free":
            data.qpos[model.joint(spec["joint"]).qposadr[0]] = spec.get("initial_q", 0.)
    for index in range(model.nu):
        data.ctrl[index] = data.qpos[model.jnt_qposadr[model.actuator_trnid[index, 0]]]
    mujoco.mj_forward(model, data)
    return model, data, metadata


def export_reference_descriptors(path="sim/reference_body_descriptors.json"):
    model, data, metadata = load_reference_model()
    metadata["initial_world_poses"] = {spec["name"]: {"position": data.xpos[model.body(spec["name"]).id].tolist(), "quaternion": data.xquat[model.body(spec["name"]).id].tolist()} for spec in metadata["body_specs"]}
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    xml, _ = build_reference_model()
    output.with_suffix(".xml").write_text(xml, encoding="utf-8")
    return metadata


if __name__ == "__main__":
    result = export_reference_descriptors()
    print(json.dumps({"output": "sim/reference_body_descriptors.json", "bodies": len(result["body_specs"]), "model_hash": result["model_hash"]}))
