# Additional simulation demonstrations

Open **More demos** in the simulation studio and choose a demonstration. Each start restores the baseline scene before applying the selected controller. The sidebar shows the stage, progress and outcome supplied by the physics runtime. Pause freezes the simulation; reset clears the current demonstration and its completion state.

| Demonstration | Scripted behavior | Evidence for completion |
| --- | --- | --- |
| Bedside approach | Follow a preset base path into the clear lane near the foot of the bed, then return to the starting area and resting pose. | At least 0.70 m of base excursion, arrival within 25 mm and 0.03 radians of the preset goal, then return and settle. |
| Greeting | Raise the left hand, move the wrist through a greeting gesture, then return to rest. | Hand height of at least 1.50 m and wrist excursion of at least 0.50 radians, then return and settle. |
| Phone return | Pick up the phone with contact and friction, lower it to its original support, open the gripper and withdraw. | At least a 15 cm lift with two seconds of bilateral hold, followed by support contact, release and settling within 20 mm horizontally and 6 mm vertically of the support target. |

These are deterministic fixture demonstrations. The patient remains a static visual model. The base uses constrained planar simulation coordinates; the bedside path does not demonstrate autonomous navigation, obstacle discovery, balance control or real-world localization. The greeting does not detect or interact with a person. The phone sequence uses a known starting pose and support rather than general object recognition or learned manipulation. All geometry and mechanics remain an unverified surrogate, and no physical robot is connected.

The shared trajectories are recorded in `sim/reference_demo_trajectories.json`. Native and browser controllers expose `metrics.demo` with the command, stage, status, normalized progress, measured outcomes and boolean completion checks. Reaching the end of a trajectory alone must not establish completion.

## Browser verification

After creating the public production build, run:

```powershell
npm --prefix apps/web run build:public
node apps/web/scripts/check-more-demos.mjs
```

The checker serves `apps/web/dist` on loopback port 4175 with the Vercel response headers and opens actual Chrome. It uses the accessible gallery and start buttons, compares measured outcomes with the trajectory thresholds, observes successful pickup before phone return, pauses and resumes each run, checks that starting another demonstration resets the baseline time, and confirms that reset removes completion. It also checks the gallery's keyboard focus and Escape behavior and rejects browser errors, failed requests and API calls.

To inspect an existing public deployment, set `VELA_PUBLIC_URL` to its URL and run the same checker. `VELA_CAPTURE_NAME` changes the artifact prefix; `VELA_DEMO_CHECK_PORT` changes the local server port. The remote check does not deploy or modify the site.

The default local report is `artifacts/more-demos-check.json`; the remote default is `artifacts/vercel-more-demos-check.json`. Gallery, action-stage and final-state screenshots are written to `apps/web/artifacts/` with the same prefix. A report records measured completion only when the checks pass; an available checker or screenshot alone is not evidence that a run succeeded. Browser checks validate the scripted simulation behavior, not clinical effectiveness or hardware readiness.

The local Chrome run on 2026-09-13 passed all three demonstrations at scene revision `29709227503dcc6f`, including pause/resume, gallery keyboard controls, switching and reset. It measured 0.807 m of base excursion, a 1.693 m hand height and 0.711-radian wrist sweep, and a 0.228 m phone lift followed by return with 1.257 mm horizontal error and positive support force. No browser errors, failed requests or API calls occurred. The [run report](../artifacts/more-demos-check.json) contains the full measurements, thresholds and seven screenshot paths. These are local build results; a deployed build requires its own remote check.

The [production site](https://vela-medical-bot.vercel.app) also passed all three demonstrations in anonymous Chrome on 2026-09-13 at scene revision `e910282b948201f7`. Pause/resume, switching, reset and gallery keyboard checks passed with no browser, HTTP, network or API errors. Production action frames visibly show the approach, raised greeting arm and held phone; the phone returned with 1.257 mm horizontal error and 1.766 N of measured support force. The [production report](../artifacts/vercel-more-demos-check.json) records the complete outcomes and seven screenshots.
