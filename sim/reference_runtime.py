"""Bounded local MuJoCo actuation and body-pose playback for the reference model.

No hardware or robot SDK transport exists here. Every displayed moving robot
body pose comes from MuJoCo forward dynamics, never a browser animation curve.
"""
from __future__ import annotations

import math
import copy
import threading
import time

import mujoco
import numpy as np

from sim.reference_model import INITIAL_ARM_Q, load_reference_model
from sim.reference_pickup import lift_stages, pickup_stages


class ReferenceSimulation:
    def __init__(self):
        self.lock = threading.RLock()
        self.model, self.data, self.metadata = load_reference_model()
        self.initial_q = self.data.qpos.copy()
        self.initial_ctrl = self.data.ctrl.copy()
        self.body_names = [spec["name"] for spec in self.metadata["body_specs"]]
        self.body_ids = {self.model.body(spec["name"]).id for spec in self.metadata["body_specs"] if not spec.get("dynamic_object")}
        self.actuated_q = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]].copy()
        self.actuated_dofs = self.model.jnt_dofadr[self.model.actuator_trnid[:, 0]].copy()
        self.mode = "idle"
        self.paused = False
        self.last_clock = time.monotonic()
        self.mode_started = 0.
        self.last_contacts = []
        self.stop_reason = None
        self.reach_plan = None
        self.step_count = 0
        self._accumulator = 0.
        self.stages = []
        self.stage_index = 0
        self.stage_started = 0.
        self.stage_start_ctrl = self.data.ctrl.copy()
        self.pickup = None
        self.lift_demo = None

    def _contacts(self, data=None, allow_phone_grasp=None):
        data = self.data if data is None else data
        if allow_phone_grasp is None:
            allow_phone_grasp = self.mode in {"pickup_demo", "release_phone"}
        result = []
        for contact in data.contact[:data.ncon]:
            a, b = int(contact.geom1), int(contact.geom2)
            robot_a = int(self.model.geom_bodyid[a]) in self.body_ids
            robot_b = int(self.model.geom_bodyid[b]) in self.body_ids
            names = [self.model.geom(a).name, self.model.geom(b).name]
            if allow_phone_grasp and "phone_geom" in names and any(name in {"left_finger_-1_geom", "left_finger_1_geom"} for name in names):
                continue
            if (robot_a or robot_b) and contact.dist < -.0001:
                result.append({"geoms": names, "distance_m": float(contact.dist), "self_collision": robot_a and robot_b})
        return result

    def _set_joint_target(self, name, value):
        actuator = self.model.actuator(f"ctrl_{name}").id
        limits = self.model.actuator_ctrlrange[actuator]
        self.data.ctrl[actuator] = np.clip(value, limits[0], limits[1])

    def _hold(self):
        for index in range(self.model.nu):
            self.data.ctrl[index] = self.data.qpos[self.model.jnt_qposadr[self.model.actuator_trnid[index, 0]]]
        self.data.qvel[self.actuated_dofs] = 0.

    def _joint_demo(self, elapsed):
        cycle = elapsed*.65
        # Both wheel hinge DOFs and planar base actuators move. This does not
        # claim wheel-driven balancing dynamics or a vendor mobile controller.
        self._set_joint_target("base_x", .025*math.sin(cycle*.65))
        self._set_joint_target("base_y", .014*math.sin(cycle*.45))
        self._set_joint_target("base_yaw", .07*math.sin(cycle*.55))
        travel = .025*math.sin(cycle*.65)
        yaw = .07*math.sin(cycle*.55)
        self._set_joint_target("left_wheel_joint", (travel-.20*yaw)/.13)
        self._set_joint_target("right_wheel_joint", (travel+.20*yaw)/.13)
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

    def _require_fixture_start(self):
        phone = self.data.xpos[self.model.body("phone").id]
        if np.max(np.abs(self.data.qpos[self.actuated_q]-self.initial_q[self.actuated_q])) > .025 or np.linalg.norm(phone[:2]-[.63, -.72]) > .01 or abs(phone[2]-.8135) > .015:
            raise ValueError("Reset the scene before starting this fixture demonstration")

    def _start_stages(self, stages, allow_phone_grasp=False):
        # Sampling checks the robot's commanded path; the separate online gate
        # checks actual contact dynamics. The moving phone is not interpolated.
        sampled = mujoco.MjData(self.model)
        previous = self.data.qpos.copy()
        checked = 0
        for stage in stages:
            # Loaded finger position targets intentionally lie beyond the
            # contacted object to produce spring force. Forward kinematics at
            # those targets is not a prediction of a frictional grasp. Check
            # free-space approach here and check every actual physics step.
            if allow_phone_grasp and stage["name"] in {"close", "lift", "hold"}:
                break
            for ratio in np.linspace(0., 1., 60):
                sampled.qpos[:] = self.data.qpos
                sampled.qpos[self.actuated_q] = (1-ratio)*previous[self.actuated_q]+ratio*stage["target_qpos"][self.actuated_q]
                mujoco.mj_forward(self.model, sampled)
                checked += 1
                collisions = self._contacts(sampled, allow_phone_grasp)
                if collisions:
                    raise ValueError(f"Fixture path rejected during {stage['name']}: {collisions}")
            previous = stage["target_qpos"]
        self.stages = stages
        self.stage_index = 0
        self.stage_started = float(self.data.time)
        self.stage_start_ctrl = self.data.ctrl.copy()
        return checked

    def _finger_contacts(self):
        touching = set()
        forces = {"left_finger_-1": 0., "left_finger_1": 0.}
        for index, contact in enumerate(self.data.contact[:self.data.ncon]):
            names = [self.model.geom(int(contact.geom1)).name, self.model.geom(int(contact.geom2)).name]
            if "phone_geom" not in names:
                continue
            for finger in forces:
                if f"{finger}_geom" in names and contact.dist < .0001:
                    wrench = np.zeros(6)
                    mujoco.mj_contactForce(self.model, self.data, index, wrench)
                    if wrench[0] > .01:
                        touching.add(finger)
                    forces[finger] += max(0., float(wrench[0]))
        return sorted(touching), forces

    def _staged_control(self):
        if not self.stages:
            return
        stage = self.stages[self.stage_index]
        elapsed = float(self.data.time)-self.stage_started
        if elapsed+1e-9 >= stage["duration_s"] and self.stage_index+1 < len(self.stages):
            if stage["name"] == "close" and len(self._finger_contacts()[0]) != 2:
                self.stop_reason = "Pickup stopped: bilateral finger contact not established"
                self.paused = True
                if self.pickup:
                    self.pickup["status"] = "failed"
                return
            self.stage_index += 1
            self.stage_started = float(self.data.time)
            # Keep squeeze force through phase changes. Restarting from actual
            # finger qpos would transiently zero spring error and drop the phone.
            self.stage_start_ctrl = self.data.ctrl.copy()
            stage = self.stages[self.stage_index]
            elapsed = 0.
        ratio = float(np.clip((elapsed+self.model.opt.timestep)/stage["duration_s"], 0., 1.))
        ratio = ratio*ratio*(3-2*ratio)
        self.data.ctrl[:] = (1-ratio)*self.stage_start_ctrl+ratio*stage["target_qpos"][self.actuated_q]

    def _measure_fixture(self):
        if self.pickup:
            phone_z = float(self.data.xpos[self.model.body("phone").id, 2])
            touching, forces = self._finger_contacts()
            self.pickup.update(stage=self.stages[self.stage_index]["name"], phone_height_m=phone_z, height_gain_m=phone_z-self.pickup["initial_phone_height_m"], finger_contacts=touching, normal_forces_n=forces, bilateral_contact=len(touching) == 2)
            if self.mode == "pickup_demo":
                if self.pickup["height_gain_m"] > .15 and len(touching) == 2:
                    self.pickup["bilateral_hold_s"] += self.model.opt.timestep
                    if self.pickup["bilateral_hold_s"] >= 2.:
                        self.pickup["success"] = True
                        self.pickup["ever_succeeded"] = True
                        self.pickup["status"] = "holding"
                else:
                    self.pickup["bilateral_hold_s"] = 0.
                    if self.pickup["success"]:
                        self.pickup["success"] = False
                        self.pickup["status"] = "lost_grasp"
            elif self.mode == "release_phone":
                self.pickup["success"] = False
                self.pickup["released"] = not touching and self.pickup["height_gain_m"] < .03
                self.pickup["status"] = "released" if self.pickup["released"] else "releasing"
        if self.lift_demo and self.mode == "lift_demo":
            self.lift_demo["stage"] = self.stages[self.stage_index]["name"]
            self.lift_demo["complete"] = self.stage_index == len(self.stages)-1 and self.data.time-self.stage_started >= self.stages[-1]["duration_s"]+.5
            for side in ("left", "right"):
                value = float(self.data.qpos[self.model.joint(f"{side}_lift").qposadr[0]])
                self.lift_demo["positions_m"][side] = value
                self.lift_demo["min_positions_m"][side] = min(value, self.lift_demo["min_positions_m"][side])
                self.lift_demo["max_positions_m"][side] = max(value, self.lift_demo["max_positions_m"][side])
                self.lift_demo["travel_m"][side] = self.lift_demo["max_positions_m"][side]-self.lift_demo["min_positions_m"][side]
                height = float(self.data.site_xpos[self.model.site(f"{side}_ee").id, 2])
                self.lift_demo["hand_height_m"][side] = height
                self.lift_demo["min_hand_height_m"][side] = min(height, self.lift_demo["min_hand_height_m"][side])
                self.lift_demo["max_hand_height_m"][side] = max(height, self.lift_demo["max_hand_height_m"][side])

    def command(self, action):
        if isinstance(action, dict):
            action = action.get("command", action.get("action"))
        with self.lock:
            if self.stop_reason and action != "reset":
                raise ValueError("Reset the scene after a simulation stop")
            if action in {"joint_demo", "reach_demo", "lift_demo", "pickup_demo"} and self.mode in {"pickup_demo", "release_phone"}:
                raise ValueError("Release the phone and reset the scene before another demonstration")
            if action == "reset":
                mujoco.mj_resetData(self.model, self.data)
                self.data.qpos[:] = self.initial_q
                self.data.ctrl[:] = self.initial_ctrl
                mujoco.mj_forward(self.model, self.data)
                self.mode, self.paused = "idle", False
                self.reach_plan, self.stop_reason = None, None
                self.last_contacts = []
                self.step_count, self._accumulator = 0, 0.
                self.stages, self.pickup, self.lift_demo = [], None, None
                self.stage_index, self.stage_started = 0, 0.
            elif action == "pause":
                self.paused = not self.paused
            elif action == "joint_demo":
                self.mode, self.paused = "joint_demo", False
                self.mode_started = float(self.data.time)
                self.stop_reason = None
                self.reach_plan = None
                self.stages, self.lift_demo = [], None
            elif action in {"pickup_demo", "lift_demo"}:
                self._require_fixture_start()
                if action == "pickup_demo":
                    stages, errors = pickup_stages(self.model, self.initial_q)
                    if any(error["position_error_m"] > .002 or error["orientation_error_rad"] > .01 for error in errors.values()):
                        raise ValueError("Pickup rejected by six-dimensional pose IK gate")
                    count = self._start_stages(stages, allow_phone_grasp=True)
                    self.pickup = {"stage": "park", "status": "running", "success": False, "ever_succeeded": False, "released": False, "initial_phone_height_m": float(self.data.xpos[self.model.body("phone").id, 2]), "phone_height_m": float(self.data.xpos[self.model.body("phone").id, 2]), "height_gain_m": 0., "bilateral_contact": False, "finger_contacts": [], "normal_forces_n": {}, "bilateral_hold_s": 0., "ik_errors": errors, "collision_samples": count, "sampled_collision_gate_passed": True, "attachment_constraints": 0}
                    self.lift_demo = None
                    self.data.mocap_pos[0] = [.63, -.72, 1.05]
                else:
                    self._start_stages(lift_stages(self.model, self.initial_q))
                    heights = {side: float(self.data.site_xpos[self.model.site(f"{side}_ee").id, 2]) for side in ("left", "right")}
                    self.lift_demo = {"stage": "clear_mast", "complete": False, "positions_m": {"left": 0., "right": 0.}, "min_positions_m": {"left": 0., "right": 0.}, "max_positions_m": {"left": 0., "right": 0.}, "travel_m": {"left": 0., "right": 0.}, "hand_height_m": dict(heights), "min_hand_height_m": dict(heights), "max_hand_height_m": dict(heights), "estimated_range_m": [-.72, .20]}
                self.mode, self.paused = action, False
                self.mode_started = float(self.data.time)
                self.reach_plan, self.stop_reason = None, None
            elif action == "release_phone":
                if self.mode != "pickup_demo" or not self.pickup or not self.pickup["success"]:
                    raise ValueError("Release is available after a confirmed bilateral pickup")
                released = self.data.qpos.copy()
                released[self.actuated_q] = self.data.ctrl
                for finger in (-1, 1):
                    released[self.model.joint(f"left_gripper_{finger}").qposadr[0]] = finger*.60
                # Releasing from the measured dynamic object pose is governed
                # by the online gate; the phone is never made kinematic.
                self.stages = [{"name": "release", "target_qpos": released, "duration_s": 1.5}]
                self.stage_index, self.stage_started = 0, float(self.data.time)
                self.stage_start_ctrl = self.data.ctrl.copy()
                self.mode, self.paused = "release_phone", False
                self.pickup["status"] = "releasing"
                self.pickup["success"] = False
                self.pickup["bilateral_hold_s"] = 0.
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
                raise ValueError("Allowed commands: joint_demo, reach_demo, pickup_demo, release_phone, lift_demo, pause, reset")
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
                elif self.mode in {"pickup_demo", "release_phone", "lift_demo"}:
                    self._staged_control()
                    if self.paused:
                        break
                elif self.mode == "reach_demo" and self.reach_plan and "start_qpos" in self.reach_plan:
                    ratio = np.clip(elapsed/self.reach_plan["duration_s"], 0., 1.)
                    ratio = float(ratio*ratio*(3.-2.*ratio))
                    desired = (1-ratio)*np.asarray(self.reach_plan["start_qpos"])+ratio*np.asarray(self.reach_plan["target_qpos"])
                    for index in range(self.model.nu):
                        qindex = self.model.jnt_qposadr[self.model.actuator_trnid[index, 0]]
                        self.data.ctrl[index] = desired[qindex]
                mujoco.mj_step(self.model, self.data)
                self.step_count += 1
                self._measure_fixture()
                contacts = self._contacts()
                if contacts or not np.isfinite(self.data.qpos).all():
                    self.last_contacts = contacts
                    self.stop_reason = "Synthetic contact stop" if contacts else "Nonfinite physics state"
                    if self.pickup:
                        self.pickup.update(success=False, status="stopped", bilateral_hold_s=0.)
                    self._hold()
                    self.paused = True
                    break
            mujoco.mj_forward(self.model, self.data)
            return self._state()

    def _state(self):
        bodies = {name: {"position": self.data.xpos[self.model.body(name).id].tolist(), "quaternion": self.data.xquat[self.model.body(name).id].tolist()} for name in self.body_names}
        joints = {self.model.joint(i).name: float(self.data.qpos[self.model.jnt_qposadr[i]]) for i in range(self.model.njnt) if self.model.jnt_type[i] != mujoco.mjtJoint.mjJNT_FREE}
        end_effectors = {side: self.data.site_xpos[self.model.site(f"{side}_ee").id].tolist() for side in ("left", "right")}
        metrics = {"physics_steps": self.step_count, "finite_dynamics": bool(np.isfinite(self.data.qpos).all()), "contacts": self.last_contacts, "stop_reason": self.stop_reason, "grasp_success": None, "object_attached": False}
        if self.pickup:
            metrics["pickup"] = copy.deepcopy(self.pickup)
            metrics["grasp_success"] = self.pickup["success"]
        if self.lift_demo:
            metrics["lift"] = copy.deepcopy(self.lift_demo)
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
