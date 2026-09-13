"""No production SDK commands are inferred from legacy Bracket Bot code."""
from typing import Protocol

SOURCE = "docs/sources/BRACKETBOT_INTEGRATION.md (supplied summary; original handout/video unavailable)"


def fact(value=None, source=None, status=None, unit=None):
    return {"value": value, "verification": status or ("reported" if value is not None else "unknown"), "source": source or (SOURCE if value is not None else "vendor/runtime required"), "unit": unit}


def manifest():
    return {
        "id": "new-bracketbot", "hardware_model_verified": False, "execution_enabled": False,
        "hardware_revision": fact(), "sdk_revision": fact(), "firmware_revision": fact(),
        "base": {"mobile": fact(True), "slam": fact(True), "localization": fact(True), "navigation": fact(True), "motor_type": fact("hub BLDC"), "stated_motor_torque": fact(8.5, unit="N m"), "dimensions": fact(), "kinematics": fact()},
        "cameras": [{"id": "head", "type": fact("stereo depth"), "stated_fov": fact(180, unit="degree"), "video_resolution": fact([2560, 960]), "intrinsics": fact(), "transform": fact()}, *[{"id": side + "_wrist", "available": fact(True), "intrinsics": fact(), "transform": fact()} for side in ("left", "right")]],
        "microphone": fact(True), "speaker": {"available": fact(True), "aec": fact(True)},
        "arms": [{"id": side, "dof": fact(7), "stated_payload": fact(2, unit="kg per arm"), "joint_names": fact(), "joint_axes": fact(), "joint_limits": fact()} for side in ("left", "right")],
        "grippers": [{"id": side, "type": fact("rotary pincher"), "servo_stall_torque_claim": fact(50, unit="kg cm; not contact force"), "geometry": fact(), "force_limits": fact()} for side in ("left", "right")],
        "vertical_stage": {"available": fact(True), "arrangement": fact("independent shoulder vertical linear stage"), "travel": fact(), "count": fact()},
        "reach": fact("floor to 6 ft height; not radial reach"), "payload": fact("2 kg stated per arm; runtime envelope unknown"),
        "compute": fact("Jetson Orin Nano Super 8 GB"), "shared_training_compute": fact("8 x H100 at event; access unprovisioned"),
        **{field: fact() for field in ("joint_limits", "velocity_limits", "acceleration_limits", "force_limits", "transforms", "camera_intrinsics", "collision_meshes", "inertial_parameters", "emergency_stop", "watchdog", "vendor_safety_primitives", "supported_control_modes", "command_rates", "sensor_synchronization", "vla_action_schema")},
        "teleoperation_available": fact("Meta Quest + custom IK reported"), "VLA_runtime_available": fact("workflow reported; runtime API unknown"),
        "capability_verification_status": "planning evidence only; no runtime handshake",
    }


class HardwareCapabilityProvider(Protocol):
    def capabilities(self) -> dict: ...
    def observe(self) -> dict: ...
    def execute_verified_trajectory(self, trajectory: dict) -> dict: ...
    def stop(self) -> dict: ...


class UnconfiguredBracketBot:
    def capabilities(self):
        return manifest()

    def observe(self):
        raise RuntimeError("No verified vendor sensor adapter configured")

    def execute_verified_trajectory(self, trajectory):
        # Intentionally unconditional until an audited vendor bridge replaces this class.
        raise RuntimeError("Hardware execution disabled: SDK, model, calibration and stop/watchdog unverified")

    def stop(self):
        return {"confirmed": False, "reason": "No hardware connection; a physical stop cannot be confirmed"}

