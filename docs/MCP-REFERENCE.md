# MCP reference

> RC3 : pour le travail dans la scène déjà ouverte, les nouveaux outils physiques/animation, la télémétrie et leurs limites, consulter [Scène ouverte et debug](LIVE-SCENE.md). Le cycle ci-dessous décrit le runtime et les outils historiques.

OmniStream exposes a high-level simulation workflow plus lower-level diagnostic/compatibility tools. Prefer the high-level tools for normal automation.

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

## Lower-level tools

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
