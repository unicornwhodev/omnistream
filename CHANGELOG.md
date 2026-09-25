# Changelog

## 1.0.0-rc3 — Public studio and truthful runtime states

- Full graphite/green workspace redesign: navigation rail, dominant viewport, persistent transport and task inspector; six real runtime surfaces and responsive layout.
- Removed unused generic favicon/social icons from the web scaffold.
- No installed example USD, canned animation keys, fake loaded path, default-as-measurement telemetry or synthetic video. Test fixtures remain isolated.
- Native MCP result errors/missing structured data are explicit; host arrival/loss, polling and stale values are handled; drafts survive supervision.
- Scene capture reads real simple TRS; complex stacks are refused. Expiring preview gating, shared action lock and sandbox-safe confirmation dialogs.
- Collider false now disables an existing collider. Capped diagnostic no longer asserts missing scene; incomplete scans block automatic bounded runs.
- Preview/export/discard safety, lost-edit confirmations, render error boundary and decoded-frame-only video status.
- Release audit now inspects actual source and rejects hidden binary payloads/symlinks. Windows ZIP includes hidden metadata; strict manifest check detects extras.
- Seven release checks plus twelve public UI/contract checks; explicit source-vs-bundle test modes; TypeScript pinned directly.
- Actual-source browser checks without host and through a real native MCP subprocess, without fake runtime/scene/WebRTC responses. Windows/RTX/Kit, full Vite build and actual Codex video remain unverified target gates.



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
