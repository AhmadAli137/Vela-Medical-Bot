# Fictional adult patient visual asset

The patient is a generic, artist-authored adult human derived from MakeHuman's
hm08 base mesh. It is not a scan of an identified person and contains no patient
name, medical record or clinical information. The pose, gown and bedding are
created by `scripts/build_patient_visual.py` for the demonstration room.

The base mesh contains modeled facial features, ears, individual fingers and
full body topology. Official graphical rig weights place the arms;
the official barycentric fitting data positions the short hair and eye meshes.
The visible skin, hair and eyes retain their source UV textures. The patient is
fully dressed in a hospital gown with the lower body beneath a shaped blanket.

## Source and license

- [MakeHuman's official license, section C](https://github.com/makehumancommunity/makehuman/blob/master/LICENSE.md)
  releases graphical assets, including the base mesh, targets, textures, clothes
  and poses, under CC0 1.0 Universal.
- [Official MakeHuman system asset pack](https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html)
  lists the selected adult skin, short01 hair, high-poly eyes and brown eye
  material as CC0.
- `makehuman/LICENSE.ASSETS.md` preserves the upstream CC0 legal text.
- `makehuman/download-provenance.json` records every downloaded file, source URL,
  archive member, byte count and SHA-256 digest. Selected archive members were
  fetched with HTTP range requests; the 267 MB core pack was not bundled.

Only graphical asset data was downloaded. The builder does not import or require
the MakeHuman application, MPFB addon or their application source code.

The adult stature, resting pose and cloth fit are visual approximations. This is
a static scene asset, with no patient dynamics, physiology or clinical behavior.
`patient-build-manifest.json` records generated bounds and named anatomy markers.
