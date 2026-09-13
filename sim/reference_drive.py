"""Wheel-contact propulsion with ideal upright guidance, not balance control."""
from __future__ import annotations

import math
import mujoco
import numpy as np

RADIUS = .13
TRACK = .40
BASE_JOINTS = ("base_x", "base_y", "base_yaw")
WHEELS = ("left_wheel_joint", "right_wheel_joint")


def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def base_indices(model):
    return np.array([model.joint(name).qposadr[0] for name in BASE_JOINTS])


def position_actuators(model):
    return np.array([i for i in range(model.nu) if not model.actuator(i).name.endswith("wheel_joint")])


def expand_navigation(model, initial, stages):
    """Replace planar translations with explicit turn, drive and final turn.

    The full qpos arrays are planning goals only. Wheel angles in them are
    irrelevant; the physical runtime sends wheel angular velocities.
    """
    indices = base_indices(model)
    previous = np.asarray(initial).copy()
    result = []
    for source in stages:
        target = np.asarray(source["target_qpos"]).copy()
        before, after = previous[indices], target[indices]
        delta = after[:2]-before[:2]
        distance = float(np.linalg.norm(delta))
        current = previous.copy()
        phase = source.get("action_phase", source["name"])

        def segment(kind, pose, seconds, reverse=False):
            result.append({"name": f"{source['name']}_{kind}", "action_phase": phase,
                           "target_qpos": pose.copy(), "duration_s": seconds,
                           "navigation": {"kind": kind, "reverse": reverse,
                                          "goal": pose[indices].tolist()}})

        if distance > 1e-7:
            heading = math.atan2(delta[1], delta[0])
            reverse = abs(wrap(heading-before[2])) > math.pi/2
            if reverse:
                heading = wrap(heading+math.pi)
            turn = abs(wrap(heading-before[2]))
            if turn > 1e-5:
                current[indices[2]] = heading
                segment("turn", current, turn/.45+2.)
            current[indices[:2]] = after[:2]
            segment("drive", current, distance/.22+4., reverse)
            turn = abs(wrap(after[2]-heading))
            if turn > 1e-5:
                current[indices[2]] = after[2]
                segment("face", current, turn/.45+2.)
        elif abs(wrap(after[2]-before[2])) > 1e-5:
            current[indices[2]] = after[2]
            segment("face", current, abs(wrap(after[2]-before[2]))/.45+2.)
        final = {**source, "target_qpos": target, "action_phase": phase}
        # Preserve the original manipulation phase and its measured gate.
        # A base-only phase needs only a short hold after navigation finishes.
        robot_q = model.jnt_qposadr[model.actuator_trnid[position_actuators(model), 0]]
        if distance > 1e-7 and np.max(np.abs(target[robot_q]-previous[robot_q])) < 1e-7:
            final["duration_s"] = 1.
        result.append(final)
        previous = target
    return result


def drive_control(model, data, target_qpos, navigation=None):
    """Bounded feedback issues only two wheel velocity motor controls."""
    indices = base_indices(model)
    x, y, yaw = data.qpos[indices]
    goal_x, goal_y, goal_yaw = np.asarray(target_qpos)[indices]
    dx, dy = goal_x-x, goal_y-y
    forward_error = math.cos(goal_yaw)*dx+math.sin(goal_yaw)*dy
    cross_error = -math.sin(goal_yaw)*dx+math.cos(goal_yaw)*dy
    heading_error = wrap(goal_yaw-yaw)
    if navigation and navigation["kind"] == "drive":
        velocity = float(np.clip(1.6*forward_error, -.25, .25))
        correction = math.atan2(2.*cross_error, max(.08, abs(forward_error)))
        heading_error += correction*(-1. if navigation.get("reverse") else 1.)
        velocity *= max(0., math.cos(heading_error))
        angular = float(np.clip(3.*heading_error, -.65, .65))
    elif navigation:
        velocity = 0.
        angular = float(np.clip(3.*heading_error, -.65, .65))
    else:
        # Hold the stopped chassis using rolling-direction/yaw feedback;
        # lateral position is never directly actuated.
        velocity = float(np.clip(2.*forward_error, -.04, .04))
        angular = float(np.clip(3.*heading_error, -.15, .15))
    left, right = (velocity-TRACK*angular/2)/RADIUS, (velocity+TRACK*angular/2)/RADIUS
    for name, desired in zip(WHEELS, (left, right)):
        actuator = model.actuator(f"ctrl_{name}").id
        # Bounded wheel acceleration reduces contact shocks during carrying.
        change = float(np.clip(desired-data.ctrl[actuator], -8.*model.opt.timestep, 8.*model.opt.timestep))
        data.ctrl[actuator] = np.clip(data.ctrl[actuator]+change, -6., 6.)


def navigation_error(model, data, target):
    actual, desired = data.qpos[base_indices(model)], np.asarray(target)[base_indices(model)]
    return float(np.linalg.norm(actual[:2]-desired[:2])), abs(wrap(actual[2]-desired[2]))


def observe_drive(model, data):
    q = data.qpos[base_indices(model)]
    velocity = [data.qvel[model.joint(name).dofadr[0]] for name in BASE_JOINTS]
    loads = {"left": 0., "right": 0.}
    for index, contact in enumerate(data.contact[:data.ncon]):
        names = {model.geom(int(contact.geom1)).name, model.geom(int(contact.geom2)).name}
        for side in loads:
            if names == {"floor", f"{side}_wheel_geom"}:
                force = np.zeros(6)
                mujoco.mj_contactForce(model, data, index, force)
                loads[side] += max(0., float(force[0]))
    return {"forward_velocity_m_s": math.cos(q[2])*velocity[0]+math.sin(q[2])*velocity[1],
            "lateral_velocity_m_s": -math.sin(q[2])*velocity[0]+math.cos(q[2])*velocity[1],
            "yaw_rate_rad_s": float(velocity[2]), "wheel_ground_contacts": {side: load>.01 for side, load in loads.items()},
            "wheel_normal_force_n": loads, "actuator_count": model.nu,
            "base_pose": {"x": float(data.xpos[model.body("robot_base").id,0]), "y": float(data.xpos[model.body("robot_base").id,1]), "z": float(data.xpos[model.body("robot_base").id,2]), "yaw": float(q[2])},
            "constraint": "upright_unvalidated"}
