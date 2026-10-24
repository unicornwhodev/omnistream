# Tiled geographic scenes

Large territories can declare bounded terrain and asset streaming beside their
trusted USD entrypoint. Kit still renders the actual USD meshes and materials;
the Codex panel receives that render through NVIDIA WebRTC.

Install this candidate's Python bridge into the compatible Kit runtime before
starting the session. The installer stages it under the Kit project's source
extensions and build. Updating only the Codex plugin files does not update an
older bridge already staged in an external Kit build.

Put `omnistream-geographic.json` beside the entrypoint:

```json
{
  "schema": "omnistream.geographic-streaming.v1",
  "tile_counts": [2, 2],
  "tile_size_m": 500,
  "origin_local_m": [-500, -500],
  "vegetation_tiles": ["tile_00_00"],
  "building_tiles": [],
  "overview_camera": "/World/Cameras/Overview"
}
```

This example describes a grid contract; it supplies no terrain or assets. The
USD must already contain these fixed paths and their real payloads:

- `/World/Terrain/tile_XX_YY`, with a `lod` variant set containing `1` and `8`.
- `/World/Vegetation/tile_XX_YY/Canopy`, a PointInstancer whose prototype targets
  carry up to 18 payloads. List only existing vegetation tiles in the manifest.
- `/World/Buildings/tile_XX_YY`, for each building tile listed in the manifest.
- The existing camera named by `overview_camera`.

The manifest accepts at most 64 × 64 tiles, finite metric coordinates and the
fixed tile identifiers. It accepts no scripts, arbitrary prim roots, remote
locations or extra fields. Referenced USD assets retain the normal trusted-scene
requirements; the manifest is not a sandbox for untrusted USD composition.

On opening this scene, the bridge asks Kit to load no payloads initially, then
loads the complete terrain at LOD 8. Selecting or navigating a camera through
OmniStream updates residency: below an absolute local Z of 4,000 m, at most 25
tile centres within 1,100 m of that camera receive LOD 1 and their vegetation
and building payloads. Instancers load only the prototype indices actually
used. Moving to the overview releases those asset payloads and restores LOD 8.
LOD choices and residency changes remain in the session; source layers are
never saved by this controller.

The simulation state exposes `geographicStreaming` with terrain/detail/asset
tile counts, the update count and the focus source. A loaded payload is distinct
from a successfully rendered and decoded frame. Inspect the state and verify
the actual Codex video separately.

Current limits:

- Focus follows the supported camera selection/navigation commands. Native
  viewport movement and animated camera trajectories do not update it.
- Distances and the altitude threshold assume a metric Z-up scene. These are
  fixed rendering policies, not scientific model parameters.
- Changing between LOD 1 and LOD 8 can expose terrain edge differences. The
  controller does not generate transition meshes or skirts.
- Asset residency is bounded by tile count, not by measured GPU memory.
- This controller does not infer fire activity, damage severity, ignition,
  spread, smoke, fuel properties or a physical solver from geographic extents.
  Damaged geometry and fire effects need their own explicit scenario semantics.
- Native MNT/MNS measurements, geographic accuracy and uncertainty remain
  separate from render LODs and technical USD validation.

The real OpenUSD regression covers overview/detail changes, loading only the
used prototype, switching its index, unloading its geometry and preserving
source bytes. Tests requiring OpenUSD explicitly skip when it is absent; a
skip does not validate residency in Kit or its RTX render.
