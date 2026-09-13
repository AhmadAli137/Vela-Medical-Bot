# Bracket Bot handout + supplied demo evidence

**Purpose:** preserve exactly what the provided Bracket Bot materials support, and separate it from inference or planned product behavior.

## Primary handout: Hack the North 2026 Robot Kit Track

### Page 1 hardware chart
The provided handout visually specifies:

- custom stereo depth camera, stated 180° view and 2560×960 video;
- speaker with acoustic echo cancellation (AEC);
- independent shoulder vertical linear stage;
- wrist camera on each arm for visual servoing;
- dual 7-DOF arms;
- rotary pincher grippers driven by a 50 kg·cm stall-servo claim;
- 2 kg payload **per arm**;
- stated reach from the floor to 6 ft height;
- Jetson Orin Nano Super 8 GB compute;
- hub BLDC drive motors, stated 8.5 N·m;
- stated 5 minutes to first map navigation;
- instant setup/data collection claim.

### Page 2 platform workflow
The handout states the platform path as:

`TELEOPERATE > COLLECT DATA > TRAIN > DEPLOY`

It explicitly lists:

- SLAM + navigation;
- speaker + microphone;
- dual 7-DOF arms with custom IK and Meta Quest control;
- VLA data + training;
- access to a shared 8× NVIDIA H100 node for policy training.

## Demo 01 — Onboard Multi-Camera Views

Observed visually:

- simultaneous head view;
- left arm/wrist view;
- right arm/wrist view;
- viewpoints update as the robot/arms move.

Supported inference: the platform is well suited to multi-view visuomotor policies because wide contextual vision and close-up wrist vision are available concurrently.

Not established by this clip: exact camera calibration, frame rate contract, depth accuracy/range, synchronization guarantees, or production API.

## Demo 02 — Bracket Bot Platform Demo

Observed visually:

- mobile platform movement in a cluttered indoor environment;
- robot orientation/position changes over the clip;
- a live 3D map / point-cloud-style visualization is shown on a nearby laptop;
- the robot operates around tables, boxes and narrow passages.

The handout independently states that mapping, localization and autonomous movement are available out of the box, so the product architecture can rely on a platform navigation layer while still requiring runtime verification of exact APIs and limits.

## Demo 03 — Meta Quest Teleoperation Demo

Observed visually:

- both arms participate in the task;
- the robot grasps and lifts a flexible black fabric item;
- it reorients, spreads and repositions the fabric over a table;
- the task requires coordinated bimanual motion rather than a single rigid pick-and-place.

This is strong evidence of **hardware dexterity under teleoperation** and of the usefulness of demonstration learning. It is not evidence that the same fabric task is already autonomous.

## Product implications

1. **Bimanual is core.** The app must model two 7-DOF arms, not one arm.
2. **Vertical reach matters.** The independent shoulder lift substantially expands accessible hospital workspaces.
3. **Wrist vision is a major asset.** Close-range visual feedback enables manipulation that would be brittle from the head camera alone.
4. **Teleoperation is part of the product-development loop.** Meta Quest control is the fastest path to demonstrations, corrections and supervised fallback.
5. **VLA should be a first-class execution mode.** Tasks involving clutter, variable geometry or deformables may need learned visuomotor behavior rather than only scripted IK.
6. **Simulation remains necessary but not sufficient.** MuJoCo is excellent for reach, collision, rigid-body dynamics and action-envelope testing; real teleop data is particularly important for deformable/high-contact tasks where simulation mismatch can dominate.
7. **The hospital safety boundary does not change.** Greater dexterity does not grant permission to touch patients, medical lines, medication, sharps or clinical controls.
