# Troubleshooting

For errors while inspecting, editing, or running the already-open stage, also see [Open scene, simulation, and diagnostics](LIVE-SCENE.md).

Start with:

```bat
installer\diagnose.cmd
```

For an installed product, the two most useful state files are:

```text
%LOCALAPPDATA%\OmniStream\state\install-state.json
%LOCALAPPDATA%\OmniStream\state\validation-report.json
```

Managed Kit stdout/stderr logs are under `%LOCALAPPDATA%\OmniStream\logs`. In Codex, `read_omnistream_runtime_logs` or the **Read Kit logs** action (currently **Lire les logs Kit**) exposes only a bounded, redacted tail for the active managed session.

## Preflight is blocked

Run `preflight_omniverse_simulation` or **Launch → Preflight** (currently **Lancer → Préflight**) and fix the failing blocking check instead of repeatedly invoking launch. Typical blockers include a missing workspace/stage, built `kit.exe`, streaming `.kit`, control bridge/panel bundle, or a signaling port already owned by another process.

A configuration change intentionally invalidates the previous preflight result; run it again before launch.

## Current-stage tools reject an edit

If inspection reports a different stage or revision, inspect the current stage again and create a fresh preview. Previews expire after 120 seconds; do not retry an old `previewId`. Structural diagnosis may be incomplete when its inspection is capped, so treat the result as bounded evidence.

Physics controls require Kit to report the actual `omni.physx` capability and a compatible physics scene/body. USD physics schemas alone do not prove that a solver is loaded; see [Open scene](LIVE-SCENE.md).

If live values are missing or marked stale, check the telemetry connection and the `ageMs` and `stale` fields. Kit samples values visible in USD; process health or an open port does not prove a fresh sample or decoded video frame.

## `The panel bundle is missing`

A release archive intentionally does not contain `mcp/web-dist/`. A normal installation obtains the NVIDIA web dependency directly on the target machine and builds that bundle locally. To repair an installed copy:

```bat
installer\repair.cmd
```

For a developer tree:

```powershell
npm --prefix .\web ci
npm run build:web
```

## `runtime_unavailable`

Check the normalized config and strict doctor output. The selected external Kit project must have produced both:

```text
<kit-root>\_build\windows-x86_64\release\kit\kit.exe
<kit-root>\_build\windows-x86_64\release\apps\<configured-streaming-layer>.kit
```

Do not set `kitRoot` to a download/archive folder that has not generated a project.

## Signaling or bridge is not ready

A running process alone is insufficient. OmniStream considers a session ready only when the managed process is alive, signaling is listening, and the authenticated local control bridge is connected.

After launch, use **Supervise → Read Kit logs** (currently **Superviser → Lire les logs Kit**). If a bridge request times out, avoid repeated camera-save/timeline mutations until runtime health has been re-established.

## `stream_port_in_use`

Another process owns the local signaling endpoint. OmniStream does not assume it owns that process. Identify the owner and resolve the collision; do not terminate an arbitrary PID just because it uses port 49100.

## `stop_pending` / `stream_stop_timeout`

Safe stop deliberately waits for an authenticated `runtime.prepare_stop` acknowledgement and for the signaling endpoint to disappear. The controller retains recovery ownership during bounded retries. Avoid force-killing Kit unless an operator has independently verified the exact process and accepted the recovery consequences.

## No image in the panel

A PID, listener, and connected bridge still do not prove that a video frame was decoded. Verify the external Kit streaming stack, matching signaling/media ports, and local NVIDIA WebRTC client build. The panel overlay remains until a real decoded frame arrives.

## Installer was interrupted

Run `installer\install.cmd` again. The installer reloads the checkpoint/config, revalidates paths/components, and resumes. It does not silently mark a previous phase complete just because the state file lists it.

## Installation tests fail

Read `validation-report.json` for the first failing check. After correcting it, run:

```bat
installer\repair.cmd
installer\test.cmd
```

Do not label an installation stable when the report says `runtimeSmokeSkipped: true` or `ok: false`.
