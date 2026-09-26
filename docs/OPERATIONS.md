# Operations

## Primary workflow: Configure → Launch → Supervise → Control

For normal use, Codex should prefer the simulation-level workflow instead of assembling a run from many low-level calls. `preflight_omniverse_simulation` is the read-only readiness gate before launch, and `read_omnistream_runtime_logs` is the bounded diagnostic surface during supervision.

There are two distinct scene workflows. **Configurer → Préflight → Lancer** opens the USD selected in the session configuration. **Scène** works on the stage already open in the managed Kit runtime and does not reload that USD. Use **Lancer → Rattacher** or `attach_omniverse_stream` only to reconnect the panel to that same ready session. An independently launched Kit process is not adopted automatically. The six panel sections are **Configurer**, **Lancer**, **Scène**, **Contrôler**, **Superviser**, and **Diagnostic**.

### 1. Configure

Call `configure_omniverse_simulation` with a bounded workspace and an existing USD stage. The configuration can also define:

- optional compatible `kitRoot`;
- human-readable run name;
- initial timeline time;
- playback rate;
- loop state;
- play-every-frame policy;
- autoplay;
- optional existing camera path.

Configuration is validated and retained in the MCP session. It does **not** start Kit and does not write USD.

### 2. Launch

Call `launch_omniverse_simulation` after configuration. Launch is one serialized orchestration operation:

1. start the managed hidden Kit runtime when necessary;
2. wait until the owned process, WebRTC signaling and authenticated bridge are ready;
3. load the configured stage below the configured workspace root;
4. apply the session-only timeline/camera configuration;
5. create a simulation `runId` and start timestamp.

No other mutating operation may interleave with those steps. If a bridge timeout makes stage loading or configuration uncertain, OmniStream records the uncertain operation and blocks further unsafe mutation until the state is reconciled or safely stopped.

### 3. Supervise

Call `supervise_omniverse_simulation` for a consolidated read-only snapshot. It reports:

- stored simulation configuration;
- current tracked run and uptime;
- managed Kit process/lifecycle state;
- WebRTC signaling state;
- authenticated bridge state;
- stage state;
- timeline state/time/rate/frame policy;
- selected camera state when available;
- an aggregated health object for runtime, stream, bridge, stage and simulation.

The panel polls this operation while an active runtime exists so the Simulation Deck reflects external stops and runtime transitions instead of becoming stale.

### 4. Control

`control_omniverse_simulation` accepts:

- `play`
- `pause`
- `stop` — stops playback only; **does not terminate Kit**
- `reset` — stops playback and returns to the configured initial time
- `step_forward`
- `step_back`
- `seek` + `timeSeconds`
- `set_rate` + `rateMultiplier` from `0.05` to `8`
- `set_loop` + `loop`

These are session controls. They do not save USD timeline metadata.

## Effective Codex control surface

| Scope | MCP operations | Boundary |
| --- | --- | --- |
| Simulation orchestration | `preflight_omniverse_simulation`, `configure_omniverse_simulation`, `launch_omniverse_simulation`, `supervise_omniverse_simulation`, `control_omniverse_simulation` | Preferred public workflow for readiness, configuration, running, observing and controlling a simulation. |
| Bounded diagnostics | `read_omnistream_runtime_logs` | Read-only, redacted tail of managed Kit stdout/stderr; never returns session credentials. |
| Panel | `open_omniverse_simulation_studio`, `attach_omniverse_stream` | Opening or attaching never starts Kit or changes USD. Attach succeeds only for the existing, ready, MCP-owned session. |
| Runtime diagnostics | `inspect_omniverse_stream_runtime`, `start_omniverse_stream`, `get_omniverse_stream_status`, `stop_omniverse_stream` | Advanced lifecycle operations. Start/stop affect only the process identity created by this server. |
| Local stages | `list_workspace_usd_stages`, `load_omniverse_stage`, `discover_omniverse_local_assets` | Advanced discovery/loading. Root stages stay under the selected workspace. USD dependencies are not fully audited. |
| Timeline compatibility | `get_omniverse_simulation_state`, `control_omniverse_timeline` | Lower-level session timeline interface retained for compatibility. |
| Cameras | `list_omniverse_cameras`, `select_omniverse_camera`, `navigate_omniverse_camera` | Only existing cameras; navigation is temporary. |
| Persistence | `save_omniverse_camera` | The only USD-writing operation. It must be explicitly requested and is marked destructive. |

The stable public plugin name is `omnistream-for-codex`.

## UI control model

The panel mirrors the same workflow:

- **Configurer** — workspace, stage, camera, initial time and playback policy for a new launch;
- **Lancer** — preflight, launch, active session identity, and attach to the existing managed stream;
- **Scène** — inspect the open stage, preview/apply corrections, export or discard managed edits;
- **Contrôler** — timeline transport and temporary camera navigation;
- **Superviser** — runtime, WebRTC, bridge, stage and timeline health;
- **Diagnostic** — scene structure, watched values, live events and bounded runtime logs.

The WebRTC viewport remains the primary visual evidence. Process health alone is not a rendered scene.

For the complete scene-edit operations, required stage/revision arguments, telemetry boundaries and physical-solver limits, see [Scène ouverte, simulation et diagnostic](LIVE-SCENE.md) and the [MCP reference](MCP-REFERENCE.md).

## Attach and terminate runtime

Use `attach_omniverse_stream` only to restore the panel connection to the same live session. It does not launch Kit, load a stage, or mutate USD.

Use `stop_omniverse_stream` when the **runtime itself** must end. This is intentionally separate from `control_omniverse_simulation { action: "stop" }`, which only stops timeline playback.

For runtime termination, the server first closes mutation admission and asks the bridge to prepare for stop. It then terminates only the verified process identity it created and waits for local signaling to stop before releasing the session.

Do not kill a PID manually. If the server reports `stop_pending`, `safe_stop_pending`, `stream_stop_timeout`, or a bridge-recovery state, supervise/read runtime status and let the bounded safe-stop path finish.

## Recovery rules

- A timeout or `mutation_uncertain` means the effect may already have happened. Supervise/read state before any retry.
- A launch uncertainty can identify `simulation.launch:stage.open` or `simulation.launch:simulation.configure`; do not issue another mutating command until reconciled.
- A camera-save error after the commit phase does not prove no USD write occurred. Inspect the target layer and returned camera state before acting again.
- `stream_port_in_use` means another local signaling process is responding. Do not assume it is this plugin's process.
- `runtime_unavailable` means the configured Kit root, streaming `.kit`, or hidden launcher is unavailable. Fix the external prerequisite; do not replace it with a browser-side renderer.

## What to record for a support report

Record the non-secret supervision/status fields, the configured Kit/workspace roots supplied by the operator, the simulation `runId`, operation name, and whether an actual panel frame appeared. Never paste the WebRTC bearer, bridge token, raw process command line, or private local files into a public issue.
