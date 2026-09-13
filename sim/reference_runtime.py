"""Bounded local MuJoCo actuation and body-pose playback for the reference model.

No hardware or robot SDK transport exists here. Every displayed moving robot
body pose comes from MuJoCo forward dynamics, never a browser animation curve.
"""
from __future__ import annotations

import math
import threading
import time

import mujoco
import numpy as np

from sim.reference_model import INITIAL_ARM_Q, load_reference_model


class ReferenceSimulation:
    def __init__(self):
        self.lock = threading.RLock()
        self.model, self.data, self.metadata = load_reference_model()
        self.initial_q = self.data.qpos.copy()
        self.initial_ctrl = self.data.ctrl.copy()
        self.body_names = [spec["name"] for spec in self.metadata["body_specs"]]
        self.body_ids = {self.model.body(name).id for name in self.body_names}
        self.mode = "idle"
        self.paused = False
        self.last_clock = time.monotonic()
        self.mode_started = 0.
        self.last_contacts = []
        self.stop_reason = None
        self.reach_plan = None
        self.step_count = 0
        self._accumulator = 0.

    def _contacts(self, data=None):
        data = self.data if data is None else data
        result = []
        for contact in data.contact[:data.ncon]:
            a, b = int(contact.geom1), int(contact.geom2)
            robot_a = int(self.model.geom_bodyid[a]) in self.body_ids
            robot_b = int(self.model.geom_bodyid[b]) in self.body_ids
            if (robot_a or robot_b) and contact.dist < -.0001:
                result.append({"geoms": [self.model.geom(a).name, self.model.geom(b).name], "distance_m": float(contact.dist), "self_collision": robot_a and robot_b})
        return result

    def _set_joint_target(self, name, value):
        actuator = self.model.actuator(f"ctrl_{name}").id
        limits = self.model.actuator_ctrlrange[actuator]
        self.data.ctrl[actuator] = np.clip(value, limits[0], limits[1])

    def _hold(self):
        for index in range(self.model.nu):
            self.data.ctrl[index] = self.data.qpos[self.model.jnt_qposadr[self.model.actuator_trnid[index, 0]]]
        self.data.qvel[:] = 0.

    def _joint_demo(self, elapsed):
        cycle = elapsed*.65
        # Both wheel hinge DOFs and planar base actuators move. This does not
        # claim wheel-driven balancing dynamics or a vendor mobile controller.
        self._set_joint_target("base_x", .025*math.sin(cycle*.65))
        self._set_joint_target("base_y", .014*math.sin(cycle*.45))
        self._set_joint_target("base_yaw", .07*math.sin(cycle*.55))
        self._set_joint_target("left_wheel_joint", .5*math.sin(cycle*.65)+.18*math.sin(cycle*.55))
        self._set_joint_target("right_wheel_joint", .5*math.sin(cycle*.65)-.18*math.sin(cycle*.55))
        for side, sign, phase in (("left", 1, 0.), ("right", -1, 1.1)):
            self._set_joint_target(f"{side}_lift", .055*math.sin(cycle*.55+phase))
            for index, initial in enumerate(INITIAL_ARM_Q, 1):
                amplitude = [.08, .18, .15, .20, .17, .15, .22][index-1]
                value = initial+amplitude*math.sin(cycle+phase+index*.25)
                if index == 1:
                    value = sign*(.11+.07*math.sin(cycle+phase))
                self._set_joint_target(f"{side}_joint_{index}", value)
            for finger in (-1, 1):
                self._set_joint_target(f"{side}_gripper_{finger}", -finger*(.16+.12*math.sin(cycle*1.5+phase)))

    def _position_ik(self, target, side="left", base_x=.18):
        candidate = mujoco.MjData(self.model)
        candidate.qpos[:] = self.data.qpos
        candidate.qpos[self.model.joint("base_x").qposadr[0]] = base_x
        joints = [self.model.joint(f"{side}_joint_{i}").id for i in range(1, 8)]
        qindices = np.array([self.model.jnt_qposadr[i] for i in joints])
        dofs = np.array([self.model.jnt_dofadr[i] for i in joints])
        site = self.model.site(f"{side}_ee").id
        target = np.asarray(target, dtype=float)
        for _ in range(240):
            mujoco.mj_forward(self.model, candidate)
            error = target-candidate.site_xpos[site]
            if np.linalg.norm(error) < .006:
                break
            jac = np.zeros((3, self.model.nv))
            mujoco.mj_jacSite(self.model, candidate, jac, None, site)
            jac = jac[:, dofs]
            delta = jac.T @ np.linalg.solve(jac @ jac.T+.003*np.eye(3), error)
            candidate.qpos[qindices] = np.clip(candidate.qpos[qindices]+np.clip(delta, -.065, .065), -2.65, 2.65)
        mujoco.mj_forward(self.model, candidate)
        residual = float(np.linalg.norm(target-candidate.site_xpos[site]))
        return candidate, residual

    def solve_reach(self, target, side="left", base_x=.18):
        """Return endpoint IK plus sampled collision check; no action occurs here."""
        with self.lock:
            vector = np.asarray(target, dtype=float)
            if side not in {"left", "right"} or vector.shape != (3,) or not np.isfinite(vector).all() or not -.1 <= base_x <= .25:
                raise ValueError("Invalid bounded synthetic reach request")
            candidate, residual = self._position_ik(vector, side, base_x)
            sampled = mujoco.MjData(self.model)
            collisions = []
            for ratio in np.linspace(0., 1., 60):
                sampled.qpos[:] = (1-ratio)*self.data.qpos+ratio*candidate.qpos
                mujoco.mj_forward(self.model, sampled)
                collisions = self._contacts(sampled)
                if collisions:
                    break
            return {"reachable": residual < .015, "collision_free_samples": not collisions, "sample_count": 60, "residual_m": residual, "target": vector.tolist(), "side": side, "contacts": collisions, "target_qpos": candidate.qpos.tolist(), "hardware_model_verified": False, "authorizes_hardware": False}

    def command(self, action):
        if isinstance(action, dict):
            action = action.get("command", action.get("action"))
        with self.lock:
            if action == "reset":
                mujoco.mj_resetData(self.model, self.data)
                self.data.qpos[:] = self.initial_q
                self.data.ctrl[:] = self.initial_ctrl
                mujoco.mj_forward(self.model, self.data)
                self.mode, self.paused = "idle", False
                self.reach_plan, self.stop_reason = None, None
                self.last_contacts = []
                self.step_count, self._accumulator = 0, 0.
            elif action == "pause":
                self.paused = not self.paused
            elif action == "joint_demo":
                self.mode, self.paused = "joint_demo", False
                self.mode_started = float(self.data.time)
                self.stop_reason = None
                self.reach_plan = None
            elif action == "reach_demo":
                # Target is a visible point near the tabletop edge. No object
                # is attached or moved, and no grasp success is fabricated.
                target = [.22, -.53, .96]
                plan = self.solve_reach(target)
                if not plan["reachable"] or not plan["collision_free_samples"]:
                    self.stop_reason = "Reach rejected by endpoint IK or sampled collision gate"
                    self.reach_plan = plan
                    self.paused = True
                else:
                    self.reach_plan = {**plan, "start_qpos": self.data.qpos.tolist(), "duration_s": 4.}
                    self.data.mocap_pos[0] = target
                    self.mode, self.paused = "reach_demo", False
                    self.mode_started = float(self.data.time)
                    self.stop_reason = None
            else:
                raise ValueError("Allowed commands: joint_demo, reach_demo, pause, reset")
            self.last_clock = time.monotonic()
            return self._state()

    def advance(self, seconds):
        """Explicit deterministic stepping hook for tests and local experiments."""
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 <= seconds <= 2:
            raise ValueError("Advance must be a finite duration between zero and two seconds")
        with self.lock:
            if self.paused:
                return self._state()
            self._accumulator += seconds
            steps = min(1000, int((self._accumulator+1e-10)/self.model.opt.timestep))
            self._accumulator -= steps*self.model.opt.timestep
            for _ in range(steps):
                elapsed = float(self.data.time)-self.mode_started
                if self.mode == "joint_demo":
                    self._joint_demo(elapsed)
                elif self.mode == "reach_demo" and self.reach_plan and "start_qpos" in self.reach_plan:
                    ratio = np.clip(elapsed/self.reach_plan["duration_s"], 0., 1.)
                    ratio = float(ratio*ratio*(3.-2.*ratio))
                    desired = (1-ratio)*np.asarray(self.reach_plan["start_qpos"])+ratio*np.asarray(self.reach_plan["target_qpos"])
                    for index in range(self.model.nu):
                        qindex = self.model.jnt_qposadr[self.model.actuator_trnid[index, 0]]
                        self.data.ctrl[index] = desired[qindex]
                mujoco.mj_step(self.model, self.data)
                self.step_count += 1
                contacts = self._contacts()
                if contacts or not np.isfinite(self.data.qpos).all():
                    self.last_contacts = contacts
                    self.stop_reason = "Synthetic contact stop" if contacts else "Nonfinite physics state"
                    self._hold()
                    self.paused = True
                    break
            mujoco.mj_forward(self.model, self.data)
            return self._state()

    def _state(self):
        bodies = {name: {"position": self.data.xpos[self.model.body(name).id].tolist(), "quaternion": self.data.xquat[self.model.body(name).id].tolist()} for name in self.body_names}
        joints = {self.model.joint(i).name: float(self.data.qpos[self.model.jnt_qposadr[i]]) for i in range(self.model.njnt)}
        end_effectors = {side: self.data.site_xpos[self.model.site(f"{side}_ee").id].tolist() for side in ("left", "right")}
        metrics = {"physics_steps": self.step_count, "finite_dynamics": bool(np.isfinite(self.data.qpos).all()), "contacts": self.last_contacts, "stop_reason": self.stop_reason, "grasp_success": None, "object_attached": False}
        if self.reach_plan:
            distance = float(np.linalg.norm(np.array(end_effectors[self.reach_plan["side"]])-self.reach_plan["target"]))
            metrics["reach"] = {"target": self.reach_plan["target"], "ik_residual_m": self.reach_plan["residual_m"], "actual_endpoint_error_m": distance, "endpoint_reached": distance < .02, "sampled_collision_gate_passed": self.reach_plan["collision_free_samples"], "samples": self.reach_plan["sample_count"]}
        return {"bodies": bodies, "joints": joints, "mode": self.mode, "paused": self.paused, "simulation_time": float(self.data.time), "end_effectors": end_effectors, "metrics": metrics, "model_hash": self.metadata["model_hash"], "hardware_model_verified": False, "authorizes_hardware": False, "source": "MuJoCo forward dynamics on reference-informed unverified surrogate", "target": {"position": self.data.mocap_pos[0].tolist()}}

    def state(self):
        with self.lock:
            timestamp = time.monotonic()
            elapsed = max(0., min(.05, timestamp-self.last_clock))
            self.last_clock = timestamp
            return self.advance(elapsed)
