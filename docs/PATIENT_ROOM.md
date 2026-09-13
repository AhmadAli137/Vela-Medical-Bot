# Furnished room and patient

The room retains named assemblies for the hospital bed, visitor chair, bedside work table, bedside cabinet, wardrobe, round visitor table, and planter. Bed rails have two deck-mounted sockets each, connected upper/lower rails and internal bars. Cabinet handles have mounting posts; cabinets and table bases meet the floor. The chair has transverse seat rails and back uprights. The drinking cup has an open rim and inner wall.

Before material batching, the Blender builder records evaluated object bounds in `assets/simulation/room-geometry-manifest.json`. `scripts/audit_room_visuals.py` checks actual mesh surface contacts and connections to the floor, selected required furniture components, and bedding support. The build stops if that audit fails. The audit accepts joined or intersecting parts and does not detect every unwanted overlap; close-up browser inspection complements it. These checks do not certify engineering load capacity or clinical furniture safety.

The patient is a fictional adult built from MakeHuman's openly licensed anatomical mesh, skin, hair and eye assets. The model rests on the mattress and pillow, wears a hospital gown, and has a shaped lower-body blanket. It is a static visual model without physiological behavior or clinical data. The simulator includes fixed approximate patient occupancy shapes that participate in its robot collision stop.

Source assets, original license documents and download hashes are retained in `assets/patient/makehuman/`. The integrated editable scene is `assets/simulation/reference-scene.blend`, with textures packed. The patient creation code is `scripts/build_patient_visual.py`; the body-fit manifest is `assets/patient/patient-build-manifest.json`.

```powershell
blender --background --factory-startup --python-exit-code 1 --python scripts/build_reference_visuals.py -- --render
npm --prefix apps/web run build:public
node apps/web/scripts/check-room-completeness.mjs
```

The browser check inspects the actual exported assembly meshes and captures room, patient, bed, chair, storage and wardrobe views. Each GLB and physics file uses the shared build revision to prevent old cached geometry from mixing with the current scene. See [measured verification](TESTING.md).
