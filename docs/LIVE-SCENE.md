# Open scene, simulation, and diagnostics

## What this module controls

The scene is the one **already open in the Kit runtime managed by this MCP session**. No reload is needed to inspect its objects, prepare animation, change approved physics settings, or run the timeline. An Omniverse application launched independently is not automatically adopted: the bridge must belong to the managed runtime and use its authentication and workspace.

Video remains the NVIDIA/RTX render streamed over WebRTC; no replacement 3D engine has been added to the browser. Launch uses a mode without a native window. Kit stays active in the background while its MCP session is active. Closing the panel does not stop a run; stopping or quitting the MCP server triggers a safe stop. This is not a Windows service that runs independently of Codex.

## Two separate workflows

**New session:** install → open the studio → configure the workspace and USD → preflight → launch. This opens a file and starts or reuses Kit.

**Scene already open:** attach the stream if needed → inspect the scene → choose an object → preview → apply → run → observe → pause/stop → edit → run again. Do not call `launch_omniverse_simulation` for a simple correction: that command loads the configured stage.

## Actions actually available

| Need | Tool | Details |
|---|---|---|
| Browse the scene | `inspect_omniverse_scene` | Paginated direct children, `stageId`, revision, up axis, units, time range, and PhysX availability. |
| Inspect an object | `inspect_omniverse_prim` | Bounded scalar/vector attributes, schemas, local matrix, and key count. Large arrays are omitted. |
| Prepare a correction | `preview_omniverse_scene_patch` | Validates and builds an isolated USD layer without changing the live scene. |
| Apply | `apply_omniverse_scene_patch` | Requires the scene ID, expected revision, and an unexpired preview. |
| Undo | `undo_omniverse_scene_patch` | Undoes the latest OmniStream correction, not the history of all Kit tools. Up to 12 states. |
| Export | `export_omniverse_scene_patch` | Writes a new `.usda` file to the workspace after confirmation; never overwrites. |
| Discard | `discard_omniverse_scene_edits` | Deletes private corrections and their history after confirmation; does not touch source files. |
| Configure observation | `configure_omniverse_scene_watch` | Up to 16 existing USD attributes, with an optional local pause on NaN/Inf. |
| Diagnose | `diagnose_omniverse_scene` | Bounded structural inspection: capabilities, bodies, colliders, animation/dynamic-body conflicts, invalid masses, and missing/multiple physics scenes. |
| Run without reloading | `run_omniverse_scene` | Animation/timeline or physics, with a wall-clock duration limit, optional rewind-to-start, and looping disabled. |
| Read live observation | `read_omniverse_live_telemetry` | Latest sample and events from a cursor, without waiting for another Kit RPC. |

Timeline and camera controls, runtime supervision, and bounded log reads are also available; see the [MCP reference](MCP-REFERENCE.md).

### Supported scene settings

`transform`: position, local XYZ rotation in degrees, and scale. This operation replaces the local transform-op order in the correction layer. It is not a small delta added to an arbitrary stack: inspect the matrix and verify the target before confirming.

`animate_transform`: 2–120 complete keys, with strictly increasing time in seconds and translation/rotation/scale. OmniStream pins the override layer's time-code rate and authors keys in that layer's clock. USD composition then preserves their time in seconds when the session cadence changes. Export retains that clock; `framesPerSecond` describes playback cadence and can differ from `timeCodesPerSecond`. This RC does not support quaternion interpolation, Bézier curves, skeletal animation, or retargeting. An animated body must be kinematic, not dynamic.

`rigid_body`: mass, kinematic/dynamic state, and optional collider. `collider`: enable/disable collision on geometry. Meshes use a convex-hull approximation, not an exact concave mesh reconstruction. Nested bodies and instances are rejected.

`physics_scene`: create/configure a PhysicsScene prim, gravity direction and magnitude. Distances/accelerations use scene units; 9.81 is appropriate for metres and 981 for centimetres. Read `metersPerUnit` and `upAxis` before proposing settings. The `mass` parameter follows USD mass units, usually kilograms.

`attribute`: typed edits to a short allowlist of existing physics attributes (mass, density, velocities, enabled state, gravity, friction, restitution). No Python code, shader, external reference, or arbitrary USD string. The panel provides the main forms; detailed attribute editing is exposed to Codex through MCP.

`playback_range`: start, end, and frames per second. Metadata is applied to the session layer, not saved to the source. Concurrent external changes to this metadata are detected and may block undo rather than being overwritten.

## Physics execution and its limits

The presence of `UsdPhysics` allows USD editing but **does not prove that a solver is available**. Physics mode requires the `omni.physx` extension to be detected, at least one physics scene, and an active body; detected structural errors block execution.

The selected NVIDIA channel and template must provide this extension. When it is missing, the panel reports that and disables physics mode. Adding `"omni.physx" = {}` to a compatible Kit application’s dependencies and rebuilding it with NVIDIA tools is an administration task for that Kit project; a simulation tool does not install it silently. Check the availability and terms for that project. This archive redistributes no NVIDIA dependencies.

Both modes use **the same global Kit timeline**. Animation mode does not disable existing physics. Stop may reset engine state; undoing a patch does not deterministically rewind the solver. `seek` and stepping backward are not reverse physics integration.

The legacy `rateMultiplier` controls target update cadence, **not guaranteed physical time scaling**. The panel now calls it “Target cadence” (“Cadence cible”). The solver, application settings, and frame policy determine actual execution.

## What “real time” means here

There are three separate loops:

- **Video:** native WebRTC stream, with cadence dependent on Kit/RTX and decoding. Video FPS is never inferred from the bridge clock.
- **Local observation:** sampling targets every 250 ms on Kit’s main thread; events are sent over the authenticated socket to an independent MCP cache. The panel reads this cache every second while visible. `kitUpdateMs` measures the Kit update loop, not GPU time or video FPS.
- **Codex decisions:** the model calls tools to observe, diagnose, and act. Events do not wake the model automatically or give it a reasoning loop on every frame.

The local watchdog pauses after the allowed wall-clock duration (1–3,600 seconds) or when a watched value is non-finite. It also runs with the panel closed, **as long as Kit and its main loop remain responsive**. This is not a hardware watchdog: if the main thread is blocked, it cannot run. Telemetry older than 2.5 seconds or a disconnection is explicitly marked stale.

Monitoring reads USD. State stored only in Fabric, CUDA, or a domain extension is not automatically observable. Controlling robots, joints, fluids, fire, sensors, OmniGraph, or custom solvers still requires a domain adapter; current scene tools do not support those interfaces.

## Corrections and persistence

A preview is tied to one scene and revision and expires after 120 seconds. At most 4 previews, 32 operations per patch, 120 animation keys, 2 MiB of managed layer data, and 12 undo states are retained.

Applying a correction transfers the validated layer into a private anonymous session layer. Both affected layers are saved in memory before transfer and restored if applying fails; `Sdf.ChangeBlock` alone would not be a transaction. If a stronger session opinion masks a proposed property, the patch is rejected instead of being reported as effective.

Pause is required to prepare/apply transforms; **Stop** is required for physics settings and undo. Scene corrections do not call `Save` on source files. The legacy `save_omniverse_camera` tool remains the explicit exception: at the user's request, it can save a camera pose into an authorized existing file.

Export produces **an override layer**, not a standalone or flattened scene. Compose it with the source scene in a USD project; referenced assets are not copied. Export does not clear the session or mark corrections as discarded. Exporting and then discarding lets you open another stage. Stopping Kit without exporting loses in-memory corrections.

## Logs and diagnostics

Buffers are bounded: 400 bridge events, 500 MCP cache events, and 150 UI events. The cursor, dropped events, and freshness are exposed. Carbonite logs use the public callback when available; runtime stdout/stderr files are available otherwise. File reads are limited to the last 512 KiB, followed by the requested line count.

Redaction masks the two session secrets and common credential formats. It does not guarantee detection of every arbitrary secret from third-party extensions; review logs before publishing them.

On `revision_conflict` or `stage_changed`, inspect again and create a new preview instead of blindly retrying. On `operation_uncertain`, supervise the runtime and follow safe-stop recovery; a transport error does not prove that no effect occurred.

## Workflow on your scene

The installer does not copy a scene or animation into the workspace. Choose a real, trusted USD file within the authorized workspace, or inspect the stage already open in the managed Kit runtime.

In **Scene** (currently **Scène**), inspect and select an object. Unobserved settings remain empty. For animation, enter keys explicitly or capture the current pose; capture is offered only for a recognized simple local TRS stack. Complex stacks are not decomposed arbitrarily. Captured values come from a fresh inspection of the prim at the time chosen by the runtime. The time field sets where to place this pose in the animation; editing that field does not move the timeline by itself.

Preview the correction and confirm applying it before the preview expires. Stop the timeline before physics changes. Disabling an existing collider now actually writes `physics:collisionEnabled = false`. Choose a valid bounded duration, run, then observe the scene and real measurements. Stale or incomplete diagnostics are reported; a truncated inspection blocks an automatic bounded run.

The scenes in `tests/fixtures/*.usda` and `mcp/fixtures/*.usda` are reserved for explicit tests. They are imported neither by the production interface nor by the normal MCP server. `npm run test:runtime` and `npm run test:physics` use dedicated temporary copies: they are native tests, not a product demo mode.

## Technical references

- NVIDIA Kit streaming: https://docs.omniverse.nvidia.com/kit/docs/kit-app-template/latest/docs/streaming.html
- NVIDIA Timeline: https://docs.omniverse.nvidia.com/kit/docs/omni.timeline/latest/omni.timeline/omni.timeline.Timeline.html
- OpenUSD layers: https://openusd.org/release/api/class_sdf_layer.html
- OpenUSD Xformable: https://openusd.org/dev/api/class_usd_geom_xformable.html
- OpenAI plugin/UI bridge: https://developers.openai.com/plugins/build/chatgpt-ui
