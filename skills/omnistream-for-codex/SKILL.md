---
name: omnistream-for-codex
description: Operate the current local Omniverse scene in Codex: hidden Kit/WebRTC, bounded simulation and animation authoring, live telemetry, structural diagnosis and reversible corrections.
---

# OmniStream for Codex — RC3

Use this plugin for a local Omniverse scene rendered by NVIDIA Kit/RTX and displayed inside Codex. The browser is NOT a replacement renderer. The compatible Kit process stays windowless in the background; never substitute a visible desktop window or fake stream.

## First decide whether a scene is already open

Read `supervise_omniverse_simulation`. If there is an open stage in the managed runtime, use `inspect_omniverse_scene` and `attach_omniverse_stream` as needed. **Do not call launch/load again just to configure or correct an open scene.** The managed runtime is the one owned by the current MCP process, not any unrelated Omniverse application already running.

Only for a new session: `open_omniverse_simulation_studio` → choose a bounded workspace and USD → `configure_omniverse_simulation` → `preflight_omniverse_simulation` → `launch_omniverse_simulation`. Configuration does not launch Kit; launch loads the selected USD. Secrets in private widget metadata are for the panel only, never print or repeat them.

## Current-scene workflow

1. `inspect_omniverse_scene`: obtain stageId, revision, units, axis, capability flags and paginated direct children. Descend explicitly; do not assume paths.
2. `inspect_omniverse_prim`: inspect actual transforms, schemas, attributes and key counts before changing an object.
3. Pause animation or Stop physics with `control_omniverse_simulation`. Stop playback leaves Kit/stream alive.
4. `preview_omniverse_scene_patch`: propose a bounded correction to the user's requested objects only. Supply stageId and expectedRevision. Explain target, effect and warnings. No arbitrary Python or USD snippets.
5. `apply_omniverse_scene_patch`: apply that exact unexpired preview once authorized by the user's request; never replay against a new revision blindly. Existing session opinions that mask a patch are refused.
6. `configure_omniverse_scene_watch`: at most 16 existing scalar/vector USD properties, optionally pause on non-finite values.
7. `run_omniverse_scene`: animation or physics, bounded wallTimeLimitSeconds (use 5–30 seconds for initial tests). Does NOT reload the USD. Both modes use the global Kit timeline; animation does NOT disable existing physics.
8. `read_omniverse_live_telemetry`: read fresh snapshots/events using nextSequence as afterSequence. Check stale, connection, age and dropped events. Follow with `diagnose_omniverse_scene` and/or `read_omnistream_runtime_logs` when needed.
9. Pause/Stop → inspect again → preview a minimal correction → apply → rerun. Summarize observed evidence, not assumed success.

## Allowed edits and important semantics

- `transform`: complete local translation, XYZ rotation in degrees, positive scale. Replaces the composed local xform order in the private layer, not a delta. Cameras use dedicated camera tools.
- `animate_transform`: 2–120 complete TRS keys, strictly increasing seconds, converted to USD time codes. A keyframed body must be kinematic. No skeletal animation/retargeting/Bezier promises.
- `rigid_body`: mass, kinematic, collider; `collider`: geometry collision enabled. Mesh approximation is convexHull, not arbitrary concave geometry. No nested body/instance authoring.
- `physics_scene`: explicit PhysicsScene prim path and gravity. Read metersPerUnit/upAxis; gravity is stage-distance units/s². USD physics schemas do not prove an active PhysX runtime.
- `attribute`: existing allowlisted physical scalar/vector/bool attributes only. Use the tool schema and returned types, not invented parameter names.
- `playback_range`: session start/end/fps. The old rateMultiplier is target cadence, NOT guaranteed physical time scaling. Seek/backward frame is NOT inverse physics.

Physical runs require actually enabled `omni.physx`, a scene and an active body, and reject detected structural errors. Missing capability is not repaired by pretending the mode ran. Ask for an administrator/runtime rebuild when an extension is missing; simulation tools do not silently install dependencies.

## Undo/export and source safety

Corrections live in a separate anonymous session override, not a source file. `undo_omniverse_scene_patch` undoes only OmniStream's last correction after Stop, not solver history. `export_omniverse_scene_patch` writes a NEW workspace-relative .usda override with explicit confirm:true after authorization. No overwrite; no standalone/flattened scene or referenced assets included. `discard_omniverse_scene_edits` is explicitly destructive to this session's edits and needs confirm:true. Export valuable work before discard or runtime shutdown.

`save_omniverse_camera` is the separate legacy exception that can persist an existing camera pose to a source USD below the authorized workspace. Use only on an explicit user request, never as part of an automatic fix. Temporary navigation must not silently become permanent.

## Real-time and diagnosis boundaries

Kit samples at up to 4 Hz on its responsive main loop and pushes events into a bounded MCP cache. The visible UI polls at 1 Hz. This is not hard real-time and does not autonomously wake Codex. The local duration/non-finite watchdog works while the panel is closed, but cannot run while Kit's main thread is hung.

Watch values come from USD; Fabric-only/CUDA/internal extension state may not be reflected. `kitUpdateMs` measures app update cadence, NOT GPU rendering FPS. A listening port/bridge/capability flag is not proof of visible video or solver convergence. A real decoded frame and observed displacement are separate evidence.

Structural diagnosis is capped and must be reported as partial when scanCapped. No fire, fluid, robotics, articulation, sensor, OmniGraph or arbitrary script adapters are provided. Do not invent them. For unknown simulation types inspect what exists, state unsupported controls, and use only supported operations.

## Uncertain outcomes / shutdown

Mutations are serialized. On revision_conflict/stage_changed inspect and preview again. On uncertain timeout, do not retry mutations blindly; read status/telemetry, inspect the existing effect and use managed safe-stop recovery. `stop_omniverse_stream` ends ONLY the exact owned process after the Kit admission barrier; do not kill arbitrary PIDs.

The bridge is authenticated loopback. USD entry paths/exports are bounded, but referenced assets can still be resolved externally by Kit. Logs are bounded/expurgated, not guaranteed free from every possible third-party secret. Review before sharing.

## Installation and proof

Use the bundled Windows installer; NVIDIA runtime, extensions, WebRTC SDK and generated bundles are obtained on the target machine, never redistributed in the source archive. RC3 remains a candidate until target checks pass. `npm run test:runtime` covers native animation/session control. `npm run test:physics` additionally requires an observed physical displacement through USD. Neither certifies the actual Codex widget's video or input; verify those visibly.

See `docs/LIVE-SCENE.md` and `QA-REPORT.md` for exact scope and current evidence.

## Public runtime integrity

Never invent a stage, prim, telemetry value, successful launch or video frame. The installer never seeds the workspace. Test USD files are test fixtures, not a default user scene. A typed path is configuration, not evidence of a loaded stage. Confirm the bridge and inspect the current stage before scene mutations. Treat incomplete tool responses as failures. If a bounded diagnostic reports scanCapped, do not claim the entire stage is valid. Captured animation keys must come from real supported TRS values, or explicit user-authored values; never fill an animation with canned rotations. Cadence multipliers are not guaranteed physical time dilation.
