"""Orientation-constrained trajectory tools for the contact-only phone demo."""
from __future__ import annotations

import math
import mujoco
import numpy as np

GRASP_ROTATION = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])


def rotation_error(target, current):
    relative = target @ current.T
    angle = math.acos(float(np.clip((np.trace(relative)-1)/2, -1., 1.)))
    vector = np.array([relative[2, 1]-relative[1, 2], relative[0, 2]-relative[2, 0], relative[1, 0]-relative[0, 1]])
    if angle < 1e-7:
        return vector/2
    if abs(math.sin(angle)) < 1e-6:
        # SO(3) logarithm near pi: use quaternion axis to avoid zero skew.
        quaternion = np.zeros(4)
        mujoco.mju_mat2Quat(quaternion, relative.reshape(-1))
        axis = quaternion[1:]
        return angle*axis/max(float(np.linalg.norm(axis)), 1e-9)
    return vector*(angle/(2*math.sin(angle)))


def solve_pose(model, initial_qpos, target, rotation=GRASP_ROTATION, base_x=.78, base_y=0., lift=0., side="left"):
    candidate = mujoco.MjData(model)
    candidate.qpos[:] = initial_qpos
    candidate.qpos[model.joint("base_x").qposadr[0]] = base_x
    candidate.qpos[model.joint("base_y").qposadr[0]] = base_y
    candidate.qpos[model.joint(f"{side}_lift").qposadr[0]] = lift
    joints = [model.joint(f"{side}_joint_{i}").id for i in range(1, 8)]
    qindices = np.array([model.jnt_qposadr[j] for j in joints])
    dofs = np.array([model.jnt_dofadr[j] for j in joints])
    site = model.site(f"{side}_grasp_center").id
    target = np.asarray(target)
    for _ in range(600):
        mujoco.mj_forward(model, candidate)
        position_error = target-candidate.site_xpos[site]
        angle_error = rotation_error(rotation, candidate.site_xmat[site].reshape(3, 3))
        if np.linalg.norm(position_error) < .0003 and np.linalg.norm(angle_error) < .003:
            break
        jacp, jacr = np.zeros((3, model.nv)), np.zeros((3, model.nv))
        mujoco.mj_jacSite(model, candidate, jacp, jacr, site)
        jac = np.vstack([jacp[:, dofs], .25*jacr[:, dofs]])
        error = np.concatenate([position_error, .25*angle_error])
        delta = jac.T @ np.linalg.solve(jac@jac.T+.0005*np.eye(6), error)
        candidate.qpos[qindices] = np.clip(candidate.qpos[qindices]+np.clip(delta, -.08, .08), -2.65, 2.65)
    mujoco.mj_forward(model, candidate)
    return candidate.qpos.copy(), {"position_error_m": float(np.linalg.norm(target-candidate.site_xpos[site])), "orientation_error_rad": float(np.linalg.norm(rotation_error(rotation, candidate.site_xmat[site].reshape(3, 3))))}


def pickup_stages(model, initial_qpos):
    """Plan a fixed, synthetic pickup fixture; execution never writes qpos.

    The 35 mm physical riser provides room below the phone for rotary pads.
    The phone remains a gravity-driven free body, including during release.
    """
    def setq(q, name, value):
        q[model.joint(name).qposadr[0]] = value
    phases = []
    park = initial_qpos.copy()
    setq(park, "right_joint_1", -.70)
    for finger in (-1, 1):
        setq(park, f"left_gripper_{finger}", finger*.60)
    phases.append({"name": "park", "target_qpos": park, "duration_s": 2.})
    drive = park.copy()
    setq(drive, "base_x", .78)
    for side in ("left", "right"):
        setq(drive, f"{side}_wheel_joint", .78/.13)
    phases.append({"name": "approach_base", "target_qpos": drive, "duration_s": 4.})
    hover, hover_error = solve_pose(model, drive, [.63, -.72, .96])
    phases.append({"name": "hover", "target_qpos": hover, "duration_s": 3.})
    grasp, grasp_error = solve_pose(model, hover, [.63, -.72, .8135])
    phases.append({"name": "descend", "target_qpos": grasp, "duration_s": 3.})
    closed = grasp.copy()
    for finger in (-1, 1):
        setq(closed, f"left_gripper_{finger}", -finger*.25)
    phases.append({"name": "close", "target_qpos": closed, "duration_s": 1.5})
    lifted, lift_error = solve_pose(model, closed, [.63, -.72, 1.05])
    phases.append({"name": "lift", "target_qpos": lifted, "duration_s": 4.})
    # This stage completes after the validation dwell. The same actuator
    # target persists indefinitely until the explicit release command.
    phases.append({"name": "hold", "target_qpos": lifted, "duration_s": 2.})
    return phases, {"hover": hover_error, "grasp": grasp_error, "lift": lift_error}


def lift_stages(model, initial_qpos):
    folded = initial_qpos.copy()
    for side, sign in (("left", 1), ("right", -1)):
        for joint, value in ((1, sign*.25), (2, -.8), (4, -.5), (6, -.15)):
            folded[model.joint(f"{side}_joint_{joint}").qposadr[0]] = value
    phases = [{"name": "clear_mast", "target_qpos": folded.copy(), "duration_s": 2.}]
    for name, left, right, duration in (("lower_stages", -.66, -.66, 5.), ("raise_left", .18, -.66, 5.), ("raise_right", .18, .18, 5.), ("return_stages", 0., 0., 3.)):
        if name == "return_stages":
            continue
        target = folded.copy()
        target[model.joint("left_lift").qposadr[0]] = left
        target[model.joint("right_lift").qposadr[0]] = right
        phases.append({"name": name, "target_qpos": target, "duration_s": duration})
    high = phases[-1]["target_qpos"].copy()
    for side in ("left", "right"):
        high[model.joint(f"{side}_joint_2").qposadr[0]] = -2.1
        high[model.joint(f"{side}_joint_4").qposadr[0]] = -.3
    phases.append({"name": "reach_high", "target_qpos": high, "duration_s": 3.})
    phases.append({"name": "fold_arms", "target_qpos": phases[3]["target_qpos"].copy(), "duration_s": 3.})
    phases.append({"name": "return_stages", "target_qpos": initial_qpos.copy(), "duration_s": 3.})
    return phases
