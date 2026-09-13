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
from sim.reference_demos import DEMO_COMMANDS, load_trajectories
from sim.reference_assistance import ASSISTANCE_COMMANDS, assistance_gate, observe_assistance


class ReferenceSimulation:
    def __init__(self):
        self.lock = threading.RLock()
        self.model, self.data, self.metadata = load_reference_model()
        self.initial_q = self.data.qpos.copy()
        self.initial_ctrl = self.data.ctrl.copy()
        self.body_names = [spec["name"] for spec in self.metadata["body_specs"]]
        self.body_ids = {self.model.body(spec["name"]).id for spec in self.metadata["body_specs"] if spec.get("robot_body", not spec.get("dynamic_object"))}
        self.actuated_q = self.model.jnt_qposadr[self.model.actuator_trnid[:, 0]].copy()
        self.actuated_dofs = self.model.jnt_dofadr[self.model.actuator_trnid[:, 0]].copy()
        self.mode = "idle"
        self.paused = False
        self.last_clock = time.monotonic()
        self.mode_started = 0.
        self.last_contacts = []
        self.stop_reason = None
        self.visual_tracking_pause_reason = None
        self.reach_plan = None
        self.step_count = 0
        self._accumulator = 0.
        self.stages = []
        self.stage_index = 0
        self.stage_started = 0.
        self.stage_start_ctrl = self.data.ctrl.copy()
        self.pickup = None
        self.lift_demo = None
        self.demo = None
        self.demo_definition = None
        self.intentional_contacts = set()

    def _contacts(self, data=None, allow_phone_grasp=None):
        data = self.data if data is None else data
        if allow_phone_grasp is None:
            allow_phone_grasp = self.mode in {"pickup_demo", "release_phone", "phone_return_demo"}
        result = []
        for contact in data.contact[:data.ncon]:
            a, b = int(contact.geom1), int(contact.geom2)
            robot_a = int(self.model.geom_bodyid[a]) in self.body_ids
            robot_b = int(self.model.geom_bodyid[b]) in self.body_ids
            names = [self.model.geom(a).name, self.model.geom(b).name]
            if frozenset(names) in self.intentional_contacts:
                continue
            if allow_phone_grasp and "phone_geom" in names and any(name in {"left_finger_-1_geom", "left_finger_1_geom"} for name in names):
                continue
            if self.mode in ASSISTANCE_COMMANDS and self.demo_definition and self.demo_definition.get("object_name"):
                object_name=self.demo_definition["object_name"]
                allowed_supports={self.demo_definition["support_geom"],"phone_riser" if object_name=="phone" else "meal_riser","bedside_tray"}
                if f"{object_name}_geom" in names and not allowed_supports.intersection(names) and contact.dist<-.0001:
                    result.append({"geoms":names,"distance_m":float(contact.dist),"self_collision":False,"carried_object_collision":True})
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
        for spec in self.metadata["body_specs"]:
            if spec.get("dynamic_object"):
                if np.linalg.norm(self.data.xpos[self.model.body(spec["name"]).id]-np.asarray(spec["pos"]))>.015:
                    raise ValueError("Reset the scene before starting this fixture demonstration")
            elif spec.get("passive_joint") and abs(float(self.data.qpos[self.model.joint(spec["joint"]).qposadr[0]]))>.01:
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
            if allow_phone_grasp and stage["name"] in {"close", "lift", "hold", "press_blinds_control"}:
                break
            for ratio in np.linspace(0., 1., 60):
                sampled.qpos[:] = self.data.qpos
                sampled.qpos[self.actuated_q] = (1-ratio)*previous[self.actuated_q]+ratio*stage["target_qpos"][self.actuated_q]
                if any("meal_box_geom" in pair or "phone_geom" in pair for pair in self.intentional_contacts):
                    # A loaded servo target lies inside the grasped object.
                    # Use an open pad pose for route checks;
                    # every actual pad/object/support contact is checked online.
                    for finger in (-1,1):
                        address=self.model.joint(f"left_gripper_{finger}").qposadr[0]
                        sampled.qpos[address]=finger*max(.10,finger*sampled.qpos[address])
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
            if self.demo and stage.get("gate_after"):
                gate=stage["gate_after"]
                if not self._demo_gate(gate):
                    self._stop_demo(f"Demo stopped: {gate} gate failed after {stage['name']}")
                    return
                measured=self.demo["measurements"]
                measured[f"gate_{gate}_passed"]=True
                if gate=="grasp_confirmed":
                    measured["confirmed_grasp_height_m"]=self.pickup["height_gain_m"]
                    measured["confirmed_grasp_hold_s"]=self.pickup["bilateral_hold_s"]
                elif gate=="phone_supported":
                    observation=self._phone_observation()
                    measured["supported_release_height_m"]=observation["phone_position"][2]
                    measured["supported_release_force_n"]=observation["riser_support_force_n"]
                    measured["supported_release_bilateral"]=len(self._finger_contacts()[0])==2
                elif gate=="assist_grasped":
                    measured["confirmed_grasp_height_m"]=measured["object_height_gain_m"]
                    measured["confirmed_grasp_hold_s"]=measured["grasp_hold_s"]
                elif gate=="assist_supported":
                    measured["supported_release_force_n"]=measured["support_force_n"]
                    measured["supported_release_position"]=list(measured["object_position"])
                    measured["supported_release_bilateral"]=measured["bilateral_contact"]
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
            if self.mode in {"pickup_demo", "phone_return_demo"}:
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
            if self.mode == "phone_return_demo":
                stage = self.stages[self.stage_index]["name"]
                if stage in {"lower_phone", "open_fingers", "retreat_hand", "clear_return", "return_base", "rest_arms", "settle"}:
                    self.pickup["success"] = False
                    self.pickup["status"] = "lowering" if stage == "lower_phone" else "returning"
                if stage in {"lift", "hold", "lower_phone"} and len(touching) != 2 and self.pickup["height_gain_m"] > .02:
                    self._stop_demo("Demo stopped: phone contact lost during supported manipulation")
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

    def _phone_observation(self):
        phone = self.data.xpos[self.model.body("phone").id].copy()
        address = self.model.joint("phone_free").dofadr[0]
        support_force = 0.
        for index, contact in enumerate(self.data.contact[:self.data.ncon]):
            names = {self.model.geom(int(contact.geom1)).name, self.model.geom(int(contact.geom2)).name}
            if names == {"phone_geom", "phone_riser"}:
                wrench = np.zeros(6)
                mujoco.mj_contactForce(self.model, self.data, index, wrench)
                support_force += max(0., float(wrench[0]))
        target = np.array(self.demo_definition["outcomes"]["phone_target"])
        return {"phone_position": phone.tolist(), "phone_xy_error_m": float(np.linalg.norm(phone[:2]-target[:2])), "phone_z_error_m": abs(float(phone[2]-target[2])), "phone_speed_m_s": float(np.linalg.norm(self.data.qvel[address:address+3])), "phone_angular_speed_rad_s": float(np.linalg.norm(self.data.qvel[address+3:address+6])), "riser_support_force_n": support_force, "hand_clearance_m": float(np.linalg.norm(self.data.site_xpos[self.model.site("left_grasp_center").id]-phone))}

    def _phone_settled(self, observation):
        thresholds = self.demo_definition["outcomes"]
        return (observation["phone_xy_error_m"] <= thresholds["phone_xy_tolerance_m"] and observation["phone_z_error_m"] <= thresholds["phone_z_tolerance_m"] and observation["phone_speed_m_s"] <= thresholds["phone_speed_tolerance_m_s"] and observation["phone_angular_speed_rad_s"] <= thresholds["phone_angular_speed_tolerance_rad_s"] and observation["riser_support_force_n"] > thresholds["support_force_minimum_n"])

    def _demo_gate(self, gate):
        if self.mode in ASSISTANCE_COMMANDS:
            return assistance_gate(self,gate)
        touching, _ = self._finger_contacts()
        if gate == "bilateral_contact":
            return len(touching) == 2
        if gate == "grasp_confirmed":
            return bool(self.pickup and self.pickup["success"] and self.pickup["ever_succeeded"])
        if gate == "phone_supported":
            return len(touching) == 2 and self._phone_settled(self._phone_observation())
        if gate == "phone_settled":
            return not touching and self._phone_settled(self._phone_observation())
        raise ValueError(f"Unknown demo gate: {gate}")

    def _stop_demo(self, reason):
        self.stop_reason = reason
        self.paused = True
        if self.demo:
            self.demo.update(complete=False, status="stopped")
            self.demo["measurements"]["settle_dwell_s"] = 0.
        if self.pickup:
            self.pickup.update(success=False, status="stopped", bilateral_hold_s=0.)
        self._hold()

    def _measure_demo(self):
        if not self.demo:
            return
        demo, thresholds = self.demo, self.demo_definition["outcomes"]
        measured = demo["measurements"]
        elapsed = max(0., float(self.data.time)-self.mode_started)
        demo.update(stage=self.stages[self.stage_index]["name"], stage_index=self.stage_index, elapsed_s=elapsed, progress=min(1., elapsed/demo["duration_s"]))
        measured["rest_qpos_error"] = float(np.max(np.abs(self.data.qpos[self.actuated_q]-self.initial_q[self.actuated_q])))
        measured["robot_speed"] = float(np.max(np.abs(self.data.qvel[self.actuated_dofs])))
        checks = {"returned_to_rest": measured["rest_qpos_error"] <= thresholds["rest_qpos_tolerance"], "robot_settled": measured["robot_speed"] <= thresholds["robot_speed_tolerance"]}
        if self.mode in ASSISTANCE_COMMANDS:
            checks.update(observe_assistance(self))
        elif self.mode == "bedside_demo":
            base = np.array([float(self.data.qpos[self.model.joint(name).qposadr[0]]) for name in ("base_x", "base_y", "base_yaw")])
            target = np.array(thresholds["base_goal_qpos"])
            measured.update(base_position_qpos=base.tolist(), base_goal_error_m=float(np.linalg.norm(base[:2]-target[:2])), base_yaw_error_rad=abs(float(base[2]-target[2])), base_home_error_m=float(np.linalg.norm(base[:2])))
            measured["max_base_excursion_m"] = max(measured.get("max_base_excursion_m",0.), measured["base_home_error_m"])
            measured["visited_bedside"] = bool(measured.get("visited_bedside", False) or measured["base_goal_error_m"] <= thresholds["base_goal_tolerance_m"] and measured["base_yaw_error_rad"] <= thresholds["yaw_tolerance_rad"])
            checks.update(visited_bedside=measured["visited_bedside"], base_travel_observed=measured["max_base_excursion_m"] >= thresholds["minimum_base_excursion_m"])
        elif self.mode == "greeting_demo":
            height = float(self.data.site_xpos[self.model.site("left_ee").id,2])
            measured["hand_height_m"] = height
            measured["max_hand_height_m"] = max(measured.get("max_hand_height_m",height),height)
            if demo["stage"].startswith("wave_"):
                wave = float(self.data.qpos[self.model.joint("left_joint_6").qposadr[0]])
                measured["wave_min_rad"] = min(measured.get("wave_min_rad",wave),wave)
                measured["wave_max_rad"] = max(measured.get("wave_max_rad",wave),wave)
            measured["wave_range_rad"] = measured.get("wave_max_rad",0.)-measured.get("wave_min_rad",0.)
            checks.update(hand_raised=measured["max_hand_height_m"] >= thresholds["minimum_hand_height_m"], wrist_waved=measured["wave_range_rad"] >= thresholds["minimum_wave_range_rad"])
        elif self.mode == "phone_return_demo":
            observation = self._phone_observation()
            measured.update(observation)
            touching, _ = self._finger_contacts()
            checks.update(confirmed_grasp=bool(self.pickup and self.pickup["ever_succeeded"]), phone_on_riser=self._phone_settled(observation), fingers_clear=not touching, hand_retracted=observation["hand_clearance_m"] >= thresholds["hand_clearance_m"])
            if self.pickup and demo["stage"] in {"retreat_hand", "clear_return", "return_base", "rest_arms", "settle"}:
                self.pickup["released"] = checks["phone_on_riser"] and checks["fingers_clear"]
                self.pickup["status"] = "returned" if self.pickup["released"] else "returning"
        demo["checks"] = checks
        all_checked = all(checks.values())
        if self.paused and self.stop_reason:
            demo.update(complete=False,status="stopped")
            return
        if self.stage_index == len(self.stages)-1 and all_checked:
            measured["settle_dwell_s"] = measured.get("settle_dwell_s",0.)+self.model.opt.timestep
        else:
            measured["settle_dwell_s"] = 0.
        if demo["complete"] and not all_checked:
            self._stop_demo("Demo stopped: a completed outcome no longer holds")
        elif elapsed+1e-9 >= demo["duration_s"] and all_checked and measured["settle_dwell_s"] >= thresholds["settle_dwell_s"]:
            demo.update(complete=True,status="complete")
        elif elapsed > demo["duration_s"]+3. and not demo["complete"]:
            self._stop_demo("Demo stopped: measured outcome checks did not settle within the bounded grace period")

    def command(self, action):
        if isinstance(action, dict):
            action = action.get("command", action.get("action"))
        with self.lock:
            if self.stop_reason and action != "reset":
                raise ValueError("Reset the scene after a simulation stop")
            if action in {"joint_demo", "reach_demo", "lift_demo", "pickup_demo"} | DEMO_COMMANDS and self.mode in DEMO_COMMANDS:
                raise ValueError("Reset the scene before another demonstration")
            if action in {"joint_demo", "reach_demo", "lift_demo", "pickup_demo"} | DEMO_COMMANDS and self.mode in {"pickup_demo", "release_phone", "phone_return_demo"}:
                raise ValueError("Release the phone and reset the scene before another demonstration")
            if action == "reset":
                mujoco.mj_resetData(self.model, self.data)
                self.data.qpos[:] = self.initial_q
                self.data.ctrl[:] = self.initial_ctrl
                mujoco.mj_forward(self.model, self.data)
                self.mode, self.paused = "idle", False
                self.reach_plan, self.stop_reason = None, None
                self.visual_tracking_pause_reason = None
                self.last_contacts = []
                self.step_count, self._accumulator = 0, 0.
                self.stages, self.pickup, self.lift_demo = [], None, None
                self.stage_index, self.stage_started = 0, 0.
                self.demo, self.demo_definition = None, None
                self.intentional_contacts = set()
            elif action == "pause":
                self.paused = not self.paused
                self.visual_tracking_pause_reason = None
            elif action == "pause_for_tracking":
                self.paused = True
                self.visual_tracking_pause_reason = "Visual tracking lost"
            elif action == "joint_demo":
                self.demo, self.demo_definition = None, None
                self.mode, self.paused = "joint_demo", False
                self.mode_started = float(self.data.time)
                self.stop_reason = None
                self.reach_plan = None
                self.stages, self.lift_demo = [], None
            elif action in DEMO_COMMANDS:
                self._require_fixture_start()
                library=load_trajectories(self.metadata["model_hash"])
                if library["nq"] != self.model.nq or library["nu"] != self.model.nu or library["actuated_q_indices"] != self.actuated_q.tolist():
                    raise ValueError("Demo trajectory topology mismatch")
                definition=library["commands"][action]
                contacts={frozenset(pair) for pair in definition.get("intentional_contacts",[])}
                allowed_contacts=set()
                if action in {"deliver_phone_demo","deliver_meal_demo"}:
                    object_name="phone" if action=="deliver_phone_demo" else "meal_box"
                    allowed_contacts={frozenset((f"{object_name}_geom",f"left_finger_{finger}_geom")) for finger in (-1,1)}
                elif action=="blinds_demo":
                    allowed_contacts={frozenset(("blinds_handle_geom",name))for name in ("left_finger_-1_geom","left_finger_1_geom","left_hand_geom")}
                if contacts!=allowed_contacts:
                    raise ValueError("Invalid intentional contact allowance")
                stages=[{**stage,"target_qpos":np.asarray(stage["target_qpos"],dtype=float)}for stage in definition["stages"]]
                for stage in stages:
                    target=stage["target_qpos"]
                    if target.shape!=(self.model.nq,) or not np.isfinite(target).all() or not math.isfinite(stage["duration_s"]) or stage["duration_s"]<=0:
                        raise ValueError("Invalid demo stage target or duration")
                    if np.any(target[self.actuated_q]<self.model.actuator_ctrlrange[:,0]) or np.any(target[self.actuated_q]>self.model.actuator_ctrlrange[:,1]):
                        raise ValueError("Demo stage exceeds actuator control limits")
                if any(error["position_error_m"]>.003 or error["orientation_error_rad"]>.01 for error in definition.get("ik_errors",{}).values()):
                    raise ValueError("Demo rejected by pose IK gate")
                previous_contacts=self.intentional_contacts
                self.intentional_contacts=contacts
                try:
                    count=self._start_stages(stages,allow_phone_grasp=action=="phone_return_demo" or action in ASSISTANCE_COMMANDS)
                except Exception:
                    self.intentional_contacts=previous_contacts
                    raise
                self.demo_definition=definition
                self.demo={"command":action,"name":definition["name"],"stage":stages[0]["name"],"stage_index":0,"stage_count":len(stages),"elapsed_s":0.,"duration_s":definition["duration_s"],"status":"running","complete":False,"progress":0.,"measurements":{"settle_dwell_s":0.,"collision_samples":count},"checks":{}}
                self.mode,self.paused=action,False
                self.mode_started=float(self.data.time)
                self.reach_plan,self.stop_reason,self.lift_demo=None,None,None
                self.pickup=None
                if action=="phone_return_demo":
                    height=float(self.data.xpos[self.model.body("phone").id,2])
                    self.pickup={"stage":"park","status":"running","success":False,"ever_succeeded":False,"released":False,"initial_phone_height_m":height,"phone_height_m":height,"height_gain_m":0.,"bilateral_contact":False,"finger_contacts":[],"normal_forces_n":{},"bilateral_hold_s":0.,"ik_errors":definition["ik_errors"],"collision_samples":count,"sampled_collision_gate_passed":True,"attachment_constraints":0}
                self._measure_demo()
            elif action in {"pickup_demo", "lift_demo"}:
                self._require_fixture_start()
                self.demo, self.demo_definition = None, None
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
                self.demo, self.demo_definition = None, None
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
                raise ValueError("Allowed commands: joint_demo, reach_demo, pickup_demo, release_phone, lift_demo, bedside_demo, greeting_demo, phone_return_demo, deliver_phone_demo, deliver_meal_demo, blinds_demo, pause, pause_for_tracking, reset")
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
                elif self.mode in {"pickup_demo", "release_phone", "lift_demo"} | DEMO_COMMANDS:
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
                self._measure_demo()
                if self.paused:
                    break
                contacts = self._contacts()
                if contacts or not np.isfinite(self.data.qpos).all():
                    self.last_contacts = contacts
                    self.stop_reason = "Synthetic contact stop" if contacts else "Nonfinite physics state"
                    if self.pickup:
                        self.pickup.update(success=False, status="stopped", bilateral_hold_s=0.)
                    if self.demo:
                        self.demo.update(complete=False,status="stopped")
                    self._hold()
                    self.paused = True
                    break
            mujoco.mj_forward(self.model, self.data)
            return self._state()

    def _state(self):
        bodies = {name: {"position": self.data.xpos[self.model.body(name).id].tolist(), "quaternion": self.data.xquat[self.model.body(name).id].tolist()} for name in self.body_names}
        actuated_joint_ids = set(self.model.actuator_trnid[:, 0].tolist())
        joints = {self.model.joint(i).name: float(self.data.qpos[self.model.jnt_qposadr[i]]) for i in actuated_joint_ids}
        object_joints = {self.model.joint(i).name: float(self.data.qpos[self.model.jnt_qposadr[i]]) for i in range(self.model.njnt) if i not in actuated_joint_ids and self.model.jnt_type[i] != mujoco.mjtJoint.mjJNT_FREE}
        cameras = {self.model.camera(i).name: {"position": self.data.cam_xpos[i].tolist(), "rotation": self.data.cam_xmat[i].tolist(), "fovy": float(self.model.cam_fovy[i]), "fovy_deg": float(self.model.cam_fovy[i]), "convention": "mujoco_opengl"} for i in range(self.model.ncam) if self.model.camera(i).name != "overview"}
        end_effectors = {side: self.data.site_xpos[self.model.site(f"{side}_ee").id].tolist() for side in ("left", "right")}
        metrics = {"physics_steps": self.step_count, "finite_dynamics": bool(np.isfinite(self.data.qpos).all()), "contacts": self.last_contacts, "stop_reason": self.stop_reason, "visual_tracking_pause_reason": self.visual_tracking_pause_reason, "grasp_success": None, "object_attached": False}
        if self.pickup:
            metrics["pickup"] = copy.deepcopy(self.pickup)
            metrics["grasp_success"] = self.pickup["success"]
        if self.lift_demo:
            metrics["lift"] = copy.deepcopy(self.lift_demo)
        if self.demo:
            metrics["demo"] = copy.deepcopy(self.demo)
        if self.reach_plan:
            distance = float(np.linalg.norm(np.array(end_effectors[self.reach_plan["side"]])-self.reach_plan["target"]))
            metrics["reach"] = {"target": self.reach_plan["target"], "ik_residual_m": self.reach_plan["residual_m"], "actual_endpoint_error_m": distance, "endpoint_reached": distance < .02, "sampled_collision_gate_passed": self.reach_plan["collision_free_samples"], "samples": self.reach_plan["sample_count"]}
        return {"bodies": bodies, "joints": joints, "object_joints": object_joints, "cameras": cameras, "mode": self.mode, "paused": self.paused, "simulation_time": float(self.data.time), "end_effectors": end_effectors, "metrics": metrics, "model_hash": self.metadata["model_hash"], "hardware_model_verified": False, "authorizes_hardware": False, "source": "MuJoCo forward dynamics on reference-informed unverified surrogate", "target": {"position": self.data.mocap_pos[0].tolist()}}

    def state(self):
        with self.lock:
            timestamp = time.monotonic()
            elapsed = max(0., min(.05, timestamp-self.last_clock))
            self.last_clock = timestamp
            return self.advance(elapsed)
