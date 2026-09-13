# New Bracket Bot integration boundary

The application uses `robot.capabilities.HardwareCapabilityProvider`; the supplied `UnconfiguredBracketBot` refuses observation and all trajectory execution because no vendor bridge is installed. `stop()` explicitly returns `confirmed=false`. It never pretends to have stopped a disconnected physical robot.

The machine-readable [capability manifest](../robot/capability-manifest.json) distinguishes reported facts from unknown runtime values with provenance on each fact. Reported values are transcribed from supplied summaries, not independently inspected original handout/video evidence. Unknown values remain null. The [original integration summary](sources/BRACKETBOT_INTEGRATION.md) is preserved.

The software mock implements logical room changes only. The MuJoCo surrogate has two seven-joint arms, one illustrative lift, grippers and head/wrist cameras. Its dimensions, inertias, drive semantics, limits and geometry are generated research assumptions. A simulation pass cannot authorize a hardware action.

Before replacing the bridge, obtain and validate:

1. Exact hardware/SDK/firmware revisions, API authentication and supported transport.
2. CAD/URDF/MJCF, collision meshes, inertias, base kinematics and dimensions; stage count and travel; both arm joint names/axes/limits.
3. Payload-dependent velocity/acceleration/effort envelopes, gripper geometry/force sensing and stop/hold semantics.
4. All camera intrinsics/extrinsics, clocks, synchronization, feedback rates and timestamp guarantees.
5. Physical E-stop and independent watchdog behavior, command timeout and fault/recovery semantics, validated without application/network dependence.
6. Quest action representation and synchronized demonstration transport; vendor VLA observation/action schema, action horizon and deployment interface.
7. Lab evidence matching calibrated real trajectories to model outputs, followed by task-specific institutional review.

Replacement sequence: build a device-authenticated read-only handshake; validate signed model/configuration artifacts; run observe-only recording; qualify stop/watchdog behavior; map verified controllers; replay bounded lab trajectories; compare real/sim telemetry; introduce task-specific permissions. No environment variable currently bypasses this sequence or enables physical control.

