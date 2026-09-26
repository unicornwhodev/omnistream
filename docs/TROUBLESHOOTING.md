# Troubleshooting

Pour une erreur lors de l’inspection, de l’édition ou de l’exécution du stage déjà ouvert, consulter aussi [Scène ouverte, simulation et diagnostic](LIVE-SCENE.md).

Start with:

```bat
installer\diagnose.cmd
```

For an installed product, the two most useful state files are:

```text
%LOCALAPPDATA%\OmniStream\state\install-state.json
%LOCALAPPDATA%\OmniStream\state\validation-report.json
```

Managed Kit stdout/stderr logs live under `%LOCALAPPDATA%\OmniStream\logs`. In Codex, `read_omnistream_runtime_logs` / the **Lire les logs Kit** action exposes only a bounded redacted tail for the active managed session.

## Preflight is blocked

Run `preflight_omniverse_simulation` or **Lancer → Préflight** and fix the failing blocking check rather than repeatedly invoking launch. Typical blockers are a missing workspace/stage, built `kit.exe`, streaming `.kit`, control bridge/panel bundle, or a signaling port already owned by another process.

A configuration change invalidates the previous preflight result intentionally; rerun it before launch.

## The current-stage tools reject an edit

If inspection reports a different stage or revision, inspect the current stage again and create a fresh preview. Previews expire after 120 seconds; do not retry an old `previewId`. A structural diagnosis can be incomplete when its inspection is capped, so treat the result as bounded evidence.

Physics controls require Kit to report the actual `omni.physx` capability and a compatible physics scene/body. USD physics schemas alone do not prove a solver is loaded; see [Scène ouverte](LIVE-SCENE.md).

If live values are absent or marked stale, check the telemetry connection, `ageMs` and `stale` fields. Kit samples USD-visible values; process health or an open port does not prove a fresh sample or decoded video frame.

## `The panel bundle is missing`

A release archive does not contain `mcp/web-dist/` by design. A normal installation obtains the NVIDIA web dependency directly on the target machine and builds that bundle locally. To repair an installed copy:

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

Do not point `kitRoot` at a download/archive folder that has not generated/built a project.

## Signaling or bridge is not ready

A running process alone is insufficient. OmniStream considers the session ready only when the managed process is alive, signaling is listening and the authenticated local control bridge is connected.

Use **Superviser → Lire les logs Kit** after launch. If a bridge request times out, avoid repeated camera-save/timeline mutations until runtime health has been re-established.

## `stream_port_in_use`

Another process owns the local signaling endpoint. OmniStream refuses to assume that it owns that process. Identify the owner and resolve the collision; do not terminate an arbitrary PID solely because it uses port 49100.

## `stop_pending` / `stream_stop_timeout`

Safe stop deliberately waits for an authenticated `runtime.prepare_stop` acknowledgement and for the signaling endpoint to disappear. The controller retains recovery ownership during bounded retries. Avoid force-killing Kit unless an operator has independently verified the exact process and accepted the recovery consequences.

## No image in the panel

A PID, listener and connected bridge still do not prove a decoded video frame. Verify the external Kit streaming stack, matching signaling/media ports and local NVIDIA WebRTC client build. The panel overlay remains until a real decoded frame arrives.

## Installer was interrupted

Run `installer\install.cmd` again. The installer reloads the checkpoint/config, revalidates paths/components and resumes. It does not silently mark a previous phase complete just because it appears in the state file.

## Installation tests fail

Read `validation-report.json` for the first failing check. After correcting it, run:

```bat
installer\repair.cmd
installer\test.cmd
```

Do not label an installation stable when the report says `runtimeSmokeSkipped: true` or `ok: false`.
