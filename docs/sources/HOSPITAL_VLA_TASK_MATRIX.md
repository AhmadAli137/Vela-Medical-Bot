# Hospital manipulation + VLA task matrix

This document separates **hardware possibility**, **teleoperated evidence**, **research hypothesis**, and **production autonomy**. The robot's dexterity should not be confused with permission to perform a task in a hospital.

| Task | Patient value | Staff value | Deterministic feasible? | VLA value | Initial mode | Notes |
|---|---:|---:|---|---|---|---|
| Find requested phone/glasses/remote | High | Medium | Yes for detection/search | Medium | observe + retrieve in mock room | strong patient-independence wedge |
| Retrieve approved item from clutter | High | Medium | Brittle | High | teleop -> VLA | wrist cameras useful for recovery |
| Bring item to bedside **surface** | High | Medium | Yes | Medium | deterministic/VLA hybrid | surface placement before direct handoff |
| Open approved drawer/cabinet | Medium | Medium | Site-specific | High | teleop -> VLA | articulated-object generalization |
| Move/arrange small room accessories | Medium | High | Often | Medium | deterministic first | validated weight/geometry only |
| Reset room to desired state | Medium | High | Partially | High for variable objects | hybrid | world-state layer defines goal; skills execute |
| Organize clean bag / belongings | Medium | Medium | Hard | High | teleop -> VLA research | consent and privacy controls required |
| Handle clean linen on empty surface | Low/Medium | Medium | Hard | High | VLA research only | motivated by bimanual fabric demo |
| Fold/spread clean fabric in mock room | Low | Medium | Hard | Very high | VLA benchmark | useful policy benchmark, not first clinical feature |
| Operate blinds/curtain | High | Low/Medium | Site-specific | High | teleop -> learned fixture skill | non-clinical only |
| Navigate/search for equipment | Medium | High | Yes | Low | deterministic | vendor SLAM/navigation preferred |
| Telepresence / remote eyes | Medium | High | Yes | Low | deterministic | no manipulation required |
| Clinical device/line manipulation | N/A | N/A | Physically maybe | Irrelevant | **blocked** | prohibited regardless of capability |
| Patient contact/repositioning | N/A | N/A | Physically maybe | Irrelevant | **blocked** | prohibited in V1/V2 |

## Recommended VLA benchmarks before hospital pilot

1. **Cluttered personal-item retrieval:** unseen instances, varying occlusion and lighting.
2. **Drawer/handle family:** different shapes/positions, visual-servo recovery.
3. **Bag stabilization:** one arm holds, one arm manipulates.
4. **Fabric benchmark:** fold/spread clean cloth on an empty table; inspired by the supplied teleoperation demo.
5. **Room reset:** restore 3-5 allowlisted objects to a learned desired state.
6. **Abstention benchmark:** prohibited object, uncertain identity, person too close, object too heavy, unknown fixture.

Success is not only task completion. Every benchmark records intervention rate, abstention quality, unexpected contacts, minimum person clearance, object drops, completion time, sim-to-real gap and post-action verification.
