# MCP reference

OmniStream exposes two scene workflows: launch a configured USD stage, or work on the stage already open in the managed Kit session. The second workflow does not reload the configured file. Prefer the high-level simulation tools for a new launch and the scene tools for edits to the current stage. An independently launched Kit process is not adopted automatically.

## Current open-stage tools

These tools act on the stage already open in the managed Kit session. Inspect the scene first, then pass its `stageId` and expected `revision` to preview/apply operations. They do not call `open` on the configured stage. See [Open scene, simulation, and diagnostics](LIVE-SCENE.md) for supported operations, physical-solver requirements, persistence, and observation limits.

| Tool | Purpose and boundary |
|---|---|
| `inspect_omniverse_scene` | Read the current stage identity/revision, units, time range, physics capability and a bounded page of direct children. |
| `inspect_omniverse_prim` | Read bounded attributes, schemas and local transform for one prim at the current timeline time. |
| `preview_omniverse_scene_patch` | Validate a bounded correction on an isolated USD stage; returns an expiring preview and does not edit the live stage. |
| `apply_omniverse_scene_patch` | Apply that exact preview to an undoable OmniStream session layer if stage, revision and expiry still match. Does not save the source USD. |
| `undo_omniverse_scene_patch` | Undo the last OmniStream correction; does not rewind a physics solver. |
| `discard_omniverse_scene_edits` | Explicitly discard OmniStream's session corrections/history; does not delete source files. |
| `export_omniverse_scene_patch` | With confirmation, write a new `.usda` override layer under the authorized workspace; no overwrite or flattening. |
| `configure_omniverse_scene_watch` | Select up to 16 existing USD attributes for bounded live observation; optional local pause on non-finite values. |
| `diagnose_omniverse_scene` | Bounded structural diagnosis of physics capability, bodies, colliders and selected animation/physics conflicts. |
| `run_omniverse_scene` | Run animation or physics on the current stage with a wall-time limit; does not reload USD or guarantee deterministic stepping. |
| `read_omniverse_live_telemetry` | Read the latest cached sample and cursor-based events; check connection, `ageMs` and `stale`. A new call is needed to observe later changes. |

Scene edits remain in memory until exported or discarded. The separate `save_omniverse_camera` operation can write an existing camera pose to a USD source after an explicit request.

## High-level workflow

### `preflight_omniverse_simulation`

Read-only. No arguments.

Checks the configured simulation, workspace/stage, built Kit executable, streaming layer, PowerShell launcher, OmniStream bridge source, locally built panel bundle and signaling-port ownership.

Key output:

```json
{
  "ready": true,
  "checks": [{ "id": "stage", "ok": true, "label": "Stage USD", "detail": "..." }],
  "failed": []
}
```

Do not launch when `ready` is false.

### `configure_omniverse_simulation`

Validates and stores the session plan. It does not start Kit and does not write USD.

Required:

- `workspaceRoot` — existing local directory bounding root-stage selection;
- `stagePath` — existing `.usd/.usda/.usdc/.usdz` below that workspace.

Optional:

- `name` (1–80 chars);
- `kitRoot`;
- `initialTimeSeconds` (`0..1,000,000`);
- `rateMultiplier` (`0.05..8`);
- `loop`;
- `playEveryFrame`;
- `autoPlay`;
- `cameraPath` — existing absolute USD camera prim path.

Example:

```json
{
  "name": "Qualification scene",
  "workspaceRoot": "<workspace>",
  "stagePath": "<absolute-path-to-your-existing-USD>",
  "initialTimeSeconds": 0,
  "rateMultiplier": 1,
  "loop": false,
  "playEveryFrame": true,
  "autoPlay": false
}
```

### `launch_omniverse_simulation`

No arguments. Mutating/serialized.

Starts or reuses only the managed Kit session, waits for WebRTC + authenticated bridge readiness, opens the configured stage, applies session-only simulation settings and publishes a run ID only after the full transaction succeeds.

The WebRTC bearer used by the panel is returned through private widget metadata rather than ordinary structured tool output.

### `supervise_omniverse_simulation`

Read-only. No arguments.

Returns:

- stored configuration;
- tracked run ID/name/start/uptime;
- runtime/process ownership;
- WebRTC/bridge/stage health;
- current timeline/camera simulation state when available;
- consolidated `health` states.

### `control_omniverse_simulation`

Mutates only the active session state. `stop` stops playback; it does **not** terminate Kit.

Actions:

| Action | Extra argument |
| --- | --- |
| `play` | none |
| `pause` | none |
| `stop` | none |
| `reset` | none |
| `step_forward` | none |
| `step_back` | none |
| `seek` | `timeSeconds` |
| `set_rate` | `rateMultiplier` (`0.05..8`) |
| `set_loop` | `loop` boolean |

### `read_omnistream_runtime_logs`

Read-only diagnostic tool. Optional:

- `stream`: `stdout`, `stderr`, or `both` (default);
- `lines`: integer `10..500` (default 120).

It reads only the active managed Kit session's log files, bounds the amount returned and redacts known session credentials plus token/password/authorization-like values.

## Runtime, stage discovery, timeline and camera tools

| Tool | Purpose |
| --- | --- |
| `open_omniverse_simulation_studio` | Open the Codex panel resource. |
| `attach_omniverse_stream` | Reattach the panel to the same already-ready managed session. |
| `inspect_omniverse_stream_runtime` | Check Kit executable/streaming layout without launching. |
| `list_workspace_usd_stages` | Bounded local root-stage discovery. |
| `discover_omniverse_local_assets` | Inspect configured local asset roots. |
| `start_omniverse_stream` | Advanced raw runtime start. |
| `get_omniverse_stream_status` | Raw runtime/stream/bridge status. |
| `stop_omniverse_stream` | Safely terminate only the verified managed Kit runtime. |
| `load_omniverse_stage` | Advanced root-stage load within the session workspace. |
| `get_omniverse_simulation_state` | Lower-level timeline/stage/camera read. |
| `control_omniverse_timeline` | Compatibility timeline control. |
| `list_omniverse_cameras` | List existing cameras. |
| `select_omniverse_camera` | Select an existing camera for temporary navigation. |
| `navigate_omniverse_camera` | Temporary orbit/pan/dolly. |
| `save_omniverse_camera` | Explicitly persist the selected camera pose; destructive/write operation. |

## Common recoverable error codes

- `simulation_not_configured` — configure before launch.
- `workspace_mismatch` — active runtime is bound to another workspace; stop it before switching.
- `stream_port_in_use` — another local process owns the signaling port.
- `runtime_not_running` / `bridge_not_connected` — wait/relaunch/diagnose before controls.
- `operation_in_progress` — a serialized mutation is already active.
- `mutation_uncertain` — a timeout/disconnect made the outcome ambiguous; supervise and safely stop/reconcile before another mutation.
- `session_not_owned` / `identity_unverified` — OmniStream refuses to control/kill a process it cannot prove it owns.
- `stop_pending` / `stream_stop_timeout` — safe-stop recovery is still reconciling bridge/process/signaling state.

Treat an error with uncertain outcome differently from a clean failure: do not blindly repeat a mutation.
