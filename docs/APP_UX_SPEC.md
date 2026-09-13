# Vela application experience

The implemented browser application is `apps/web`, a React + TypeScript + Vite client with four routes. It runs against the FastAPI service and never generates operational counts, task results, or success rates in the browser. The default route is `/#staff`.

## Implemented surfaces

| Route | Purpose | Working interactions |
|---|---|---|
| `/#staff` | Room operations | Inspect the synthetic semantic room map and object permissions; search objects; compare desired room templates; scan a new mock snapshot; create, validate, approve, execute and cancel plans; inspect safety checks and post-action verification. |
| `/#patient` | Bedside assistance | Large common-item, environment, information and staff-request controls; text intake; optional browser speech input; request response and source; cancellation; privacy preferences; larger text. Clinical responses clearly state that the demo cannot contact real staff. |
| `/#fleet` | Robotics operations | Honest unavailable hardware telemetry; conceptual dual-arm robot illustration; explicit disconnected camera placeholders; skill inventory; mock E-stop/reset; consent-gated correction session recording and completion. |
| `/#research` | Research and simulation | Evidence hypotheses with primary-source links and actual service scores; actual MuJoCo scene preview; an **Open 3D simulator** button that opens the native interactive viewer on the local computer; configurable seeded surrogate benchmarks; downloadable JSON results; skill lifecycle inspection; actual image record counts and provenance. |

Navigation selects the corresponding role in the loopback demo. Starting a correction from a task selects the operator role before creating the session, then preserves that session's ownership while recording and completing it. Staff can explicitly select another demo role; Privacy & preferences exposes the same selector on all surfaces. The backend enforces permissions. This is a local demonstration mechanism, not hospital SSO.

## Interaction integrity

- API mutations display a busy state and disable dependent controls. Service errors display the server's reason, with no simulated success replacement.
- Physical assistance first creates a plan. Validation, staff approval and mock execution are distinct server calls.
- Object scene positions come from the current service snapshot. The drawing is an illustrative top-down semantic diagram, not a calibrated sensor view or vendor CAD.
- Protected and unknown objects retain explicit text policy labels. Skill capability is never presented as permission.
- Each UI mutation refreshes authoritative service state; a refresh control updates it explicitly. This prototype does not provide a live event subscription.
- Learned-policy metrics, hardware telemetry and staff time savings remain unavailable unless measured by the appropriate service. Surrogate benchmark output is labeled as such.
- Mock corrections record twelve synthetic state/action frames with opaque media references before labeling the episode. They contain no Quest input or camera pixels. Training and promotion require the separate research API/CLI workflow.

## Accessibility and privacy

The interface provides keyboard navigation, an explicit skip link, semantic controls, modal focus trapping and focus restoration, Escape dismissal, visible focus indicators, reduced-motion support, status announcements, text alternatives, responsive layouts and large patient controls. This implementation has not undergone a formal WCAG audit or patient usability study.

Fonts are bundled locally; the app has no runtime font CDN requests. Cameras are represented as disconnected placeholders. Browser speech input is optional, off until the user enables it, and requires browser microphone permission. The consent text explains that browser speech recognition may use an external service. Voice produces a transcript for the user to review and send; it does not automatically submit a request. Do not use patient data with this optional browser service.

The French selection is explicitly labeled a limited preview: primary headings and actions have translated labels; the full service responses and all controls are not yet localized. Clinical interpreter integration is unavailable. Larger text is a local display preference; camera and microphone preferences persist in the backend room state.

## Deliberate gaps

No real hospital, EHR, call-bell, RTLS, robot, camera, Quest device or live foundation-model service is claimed as connected. The app does not display invented wait estimates, patient identities, camera imagery, battery values or savings. The full VLA training/promotion API exists elsewhere in the repository; the UI currently inspects the lifecycle and exercises mock correction, rather than presenting a generic autonomous-learning switch.

Browser checks live in `apps/web/e2e/workflows.spec.ts`. Run the API on port 8000 and Vite on 5173, then run `npm run test:e2e` from `apps/web`. The suite uses a real local API and Chrome, mutates only the synthetic workspace, and saves desktop/mobile screenshots in `apps/web/artifacts/`.

## Immersive reference simulation

`/#simulation` opens a separate, full-window Three.js studio. The Research → Simulation card links directly to it. Detailed Blender GLBs load from the authenticated local `/api/sim/assets/room.glb` and `/api/sim/assets/robot.glb` routes. Physically based materials, a prefiltered reflection environment, directional daylight, shadow maps, ambient occlusion and ACES tone mapping provide the rendering; no external CDN or cloud renderer is used.

The viewer offers room, bedside, robot and phone camera presets, mouse/touch orbit/pan/zoom, full-screen mode, a performance setting, pause/resume, reset, joint motion, endpoint reach, vertical travel and phone pickup. The renderer applies each coherent MuJoCo pose directly, preserving articulated geometry; independent world-space interpolation is not used. Local Python state is requested at approximately 20 Hz, while public browser physics updates at up to 60 Hz according to device performance. Offscreen multisampling provides antialiasing through the postprocessing pipeline. The HUD displays actual simulation time, synchronization count, joint positions, step counts, contact stops and measured outcomes.

The detailed visual reconstruction still has estimated geometry and mechanics. The UI calls it a **reference reconstruction**, marks hardware verification as unavailable, and explains that vendor CAD, inertias, calibration and joint limits are required before hardware validation. The native MuJoCo viewer remains available separately. `tests/test_reference_api.py` verifies local-mode restrictions, role authorization, command allowlisting, actual physics state behavior, and exact asset-file access.

## Public static simulation

`npm run build:public` builds the browser-only demonstration for Vercel. Its default route opens the immersive simulation; all hashes remain in that public surface. The local operational workspace is described in an accessible About dialog and requires the Python backend. No hospital or robot API is exposed or required by the public site.

The public transport loads the pinned official MuJoCo WebAssembly engine from the built site, with the same reference MJCF and body descriptors as the local simulator. Joint controls and the reach controller run actual physics on the visitor's device. The public UI identifies the engine as **MuJoCo / WebAssembly**, while the normal local build continues to identify **MuJoCo / Python**. Neither authorizes physical hardware.

The build copies the three detailed GLBs from `assets/simulation` into the output directory. Physics XML and descriptors are tracked in `apps/web/public/simulation`; WASM and fonts are bundled from npm dependencies. Runtime assets are served from the same origin. Root `vercel.json` applies the required WebAssembly CSP allowance and disables camera, microphone and location access for this public surface.

`npm run test:public` checks the production build using a standalone static server with the exact Vercel security headers and no API proxy. It verifies geometry synchronization, joint motion, pause, reach, public routing, About dialog keyboard behavior, and absence of local API requests. Measured output is written to `artifacts/public-browser-check.json` and a screenshot to `apps/web/artifacts/public-simulation.png`.

## Contact pickup and vertical travel

The updated reference model contains 25 actuated robot coordinates and an independent free-body phone. The phone starts on a physical riser that provides finger clearance. **Pick up phone** runs orientation-aware approach, descent, closure, lift and hold stages. The live readout confirms a pickup only after a lift above 15 cm and at least two seconds of measured force-bearing contact from both fingers. **Release phone** becomes available after that confirmation; opening the gripper lets gravity return the phone to the scene. No weld, attachment constraint or direct phone-pose animation is used.

**Vertical travel** moves both carriages through a measured range of approximately 84 cm, then demonstrates low and high hand positions. The UI shows current carriage positions, measured travel and hand height. Both demonstrations use a fixed synthetic fixture, estimated mechanics and online collision checks. These demonstrations do not establish hardware capability or general-purpose object pickup.

Other demonstrations are disabled during an active demonstration, and the reset control displays **Reset to switch**. Contact faults clear the current success indication and require reset. Pickup history records that a grasp previously succeeded separately from whether it remains held now.

The public browser checker also verifies low/high travel, sustained pickup and gravity-driven release, and captures each view. `VELA_PUBLIC_URL` selects an anonymous deployed-site check; `VELA_RECORD_VIDEO=1` records the actual run. All three GLBs and both physics fixtures carry one build-content revision query, preventing cached older geometry from being paired with a new physics model.

## Furnished room and patient views

**Patient bedside** frames the modeled patient and hospital bed. The **Model & physics** panel also offers a patient close-up and inspection views of the bed foot/chassis, rear bed corner, visitor chair, bedside storage, wardrobe and visitor table. These controls move only the camera and remain available during robot demonstrations.

The visible patient is labeled **Synthetic patient model**. The scene provides an anatomical visual model with a gown and blanket; it does not display patient identity, medical measurements or clinical status. Fixed occupancy colliders approximate the space occupied by the patient.

`scripts/check-room-completeness.mjs` loads the actual production assets, checks that all eight named room assemblies (including the planter) contain geometry, compares world bounds to the optional source manifest, and captures nine camera views in Chrome. It also checks patient placement, model labeling, physics-control availability, asset revision consistency and browser/network errors. Geometry diagnostics are read from the loaded GLB rather than inferred from UI text.

Bounds use actual transformed mesh vertices. The seven furniture/patient assemblies must agree with source bounds within 2.5 cm. The planter must fit its conservative source envelope and retain comparable extents; rotated leaf bounding boxes enclose more space than their actual surfaces. The evidence records the comparison method and measurements for each assembly.
