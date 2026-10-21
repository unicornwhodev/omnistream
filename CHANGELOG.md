# Changelog

## 1.0.0-rc4 — Validated launch snapshots

- Requalify the current candidate locally on October 21: complete automatic Windows/Kit checks, OpenUSD, observed PhysX motion and actual decoded Chrome video/native input. Keep the Codex panel-opening blocker explicit; add sanitized evidence and a reproducible setup/usage guide.
- Accept current signaling/TLS/remote configuration keys in strict doctor while validating their structure without echoing private values; preserve optional transport and remote profiles during repair.
- Keep an already active decoded stream when Attach is requested again, avoiding a second SDK peer and a misleading negotiation failure.
- Pin Vite 6.4.5; the recorded complete npm audit reports zero vulnerabilities.
- Update only the transitive source-map-js dependency to 1.2.2.
- Require validation and a matching preflight after every draft edit; display one complete launch snapshot and invalidate previous success messages.
- Ignore outdated configuration/preflight/poll responses and admit only one concurrent launch.
- Add opaque configuration identities and optional expectedConfigurationId to launch; reject a changed configuration before Kit side effects while retaining legacy empty arguments.
- Snapshot preflight inputs before asynchronous runtime inspection.
- Add behaviour tests using the existing Node runner and TypeScript compiler; retain the six-view interface.
- Track source/native evidence and actual Codex video/input/dialog acceptance separately in the RC4 qualification report.
- Read current private MCP Apps metadata during stream attachment, allow explicit attachment retries, and diagnose bounded signaling/CSP failures without reporting them as received video.
- Document a real FireViewer Die–Pontaix map qualification case with isolated source copies and dedicated cameras; record the actual Codex CSP blocker separately from successful Kit controls.
- Add an optional owned localhost TLS signaling relay for Codex hosts that require WSS. Require an already trusted, valid non-CA server certificate; never install trust or bypass certificate validation. Preserve Kit, NVIDIA SDK, bearer authentication and media ports.
- Preserve the complete controller configuration when reopening: late runtime-default replies cannot replace its workspace or Kit root, and hydration grants no launch readiness.
- Add an opt-in local MCP signaling transport for embedded hosts: bounded app-only exchanges negotiate the unchanged NVIDIA client's native WebRTC video/input with the owned loopback Kit session. Keep SDP/ICE in private app metadata, preserve bearer authentication, and close stale channels on session changes.
- Match asynchronous WebSocket close semantics so the NVIDIA client can release its signaling socket without interpreting its own close as a remote disconnect.
- Attach operator-allowlisted existing remote Kit streams with separate viewer ownership, private MCP signaling/ICE, native video/input, and local mutation guards. Support an explicitly verified private Tailscale peer as well as authenticated WSS with direct or server-configured TURN media; disconnect never stops the external runtime or GPU.

## 1.0.0-rc3 — Public studio and truthful runtime states

- Windows qualification fixes: preserve prerequisite-probe arguments, launch npm diagnostics through `cmd.exe`, serialize validation reports on Windows PowerShell, initialize the correct module lookup from CMD, and accept a locally built panel during MCP tests.
- Restore optional platform dependencies in the lockfile and update the transitive Nano ID dependency to 3.3.19.
- Stage the Python bridge through the Kit extension build and add native tests for disabled startup, loopback rejection, and camera persistence.
- Keep animation key times in seconds through session cadence changes and exported override layers.
- Author persisted camera matrix opinions without adding a duplicate composed transform op; reacquire the camera after Kit updates.
- Guard uninstall identity and protected paths, and preserve unrelated user environment configuration.
- Enforce matching package/plugin/web/bridge/README versions in release verification; preserve checkout source bytes through Git attributes.
- Record actual Windows/OpenUSD/Kit/PhysX and FireViewer Die–Pontaix qualification separately from the remaining Codex video/input/dialog gates.
- Full graphite/green workspace redesign: navigation rail, dominant viewport, persistent transport and task inspector; six real runtime surfaces and responsive layout.
- Removed unused generic favicon/social icons from the web scaffold.
- No installed example USD, canned animation keys, fake loaded path, default-as-measurement telemetry or synthetic video. Test fixtures remain isolated.
- Native MCP result errors/missing structured data are explicit; host arrival/loss, polling and stale values are handled; drafts survive supervision.
- Scene capture reads real simple TRS; complex stacks are refused. Expiring preview gating, shared action lock and sandbox-safe confirmation dialogs.
- Collider false now disables an existing collider. Capped diagnostic no longer asserts missing scene; incomplete scans block automatic bounded runs.
- Preview/export/discard safety, lost-edit confirmations, render error boundary and decoded-frame-only video status.
- Release audit now inspects actual source and rejects hidden binary payloads/symlinks. Windows ZIP includes hidden metadata; strict manifest check detects extras.
- Seven release checks plus twelve public UI/contract checks; explicit source-vs-bundle test modes; TypeScript pinned directly.
- Initial browser checks used actual source without a host and through a native MCP subprocess, without fake runtime/scene/WebRTC responses. The dated qualification report records the subsequent Windows/OpenUSD/Kit/PhysX results; actual Codex video/input/dialog checks remain outstanding.



## 1.0.0-rc2 — Current scene and live observation

- Ten scene tools plus a cached live-telemetry tool, exposed to both model and app.
- Current-stage inspection; typed TRS animation, rigid bodies, colliders, gravity and allowlisted physical properties.
- Isolated previews, stage/revision checks, bounded undoable session layers and new-file-only override export.
- Physics capability/structural validation, explicit local wall-time limit and optional non-finite-watch pause.
- Kit-pushed 4 Hz telemetry, bounded event cache, 1 Hz panel polling and stale/disconnect visibility.
- Scene/Debug UI, watch values, event filter and responsive fixes at 420/820/1440px.
- Corrected target-cadence labeling, bearer redaction ordering, Python startup import shadowing, and per-operation rollback.
- Dedicated source tests, optional real-USD tests, expanded native animation test and explicit physical-motion gate.
- Original physics/animation example installed without overwriting existing example files.
- Honest candidate report: local source/browser checks only; locked clean install, production Vite build, real USD/Kit/PhysX/WebRTC/Codex remain target gates.

All notable OmniStream product changes are recorded here.

## 1.0.0-rc1 — 2026-09-03

### Product surface

- Reframed OmniStream around the complete simulation lifecycle: **Configure → Launch → Supervise → Control**.
- Added first-class MCP tools for simulation configuration, atomic launch, consolidated supervision, playback control, preflight readiness and bounded runtime-log retrieval.
- Kept lower-level Kit, USD, timeline and camera tools for diagnostics and advanced workflows.
- Reworked the Codex panel into a viewer-first Simulation Studio with runtime telemetry, launch preflight, session journal, Kit log tail and advanced camera persistence controls.

### Installation and runtime

- Added resumable Windows installer checkpoints and normalized paths under `%LOCALAPPDATA%\OmniStream` plus user workspace/assets under Documents.
- Added Production / Feature / Existing NVIDIA runtime channels. NVIDIA binaries and WebRTC packages remain external and are never redistributed in OmniStream releases.
- Added package integrity manifest, atomic source replacement, repair, diagnosis, validation and uninstall entry points.
- Pinned the panel dependency graph with `web/package-lock.json`; target installations use `npm ci`.

### Reliability and security

- Made simulation launch a serialized transaction so start/load/configuration cannot interleave with another mutation.
- Added global MCP tool-descriptor validation and fixed the camera-navigation descriptor contract.
- Added authenticated loopback Kit bridge, session-token redaction, bounded USD root selection, exact process-identity checks and safe-stop recovery.
- Added runtime preflight and redacted bounded log access for diagnosis before/after launch.

### Qualification

- Added Windows source CI and an explicit self-hosted RTX/Kit smoke workflow.
- Added target-side `Test-OmniStream.ps1`, validation reports, strict doctor checks and runtime smoke coverage.
- Release remains **RC** until the full Windows RTX / Kit / WebRTC smoke gate succeeds on the target environment.
