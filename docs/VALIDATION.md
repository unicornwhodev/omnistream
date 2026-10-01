# Validation

OmniStream separates **source qualification**, **installed-runtime qualification**, and **visible Codex evidence**. No single process ID, port, build, or unit test is presented as evidence for all three.

## Source gate

After obtaining the `web` dependencies on Windows:

```powershell
npm --prefix .\web ci
npm run check
npm test
npm run test:python
npm run test:web
.\installer\Build-Release.ps1
```

| Command | Evidence | Launches Kit / writes USD? |
|---|---|---|
| `npm run check` | Node syntax plus TypeScript checks for the real panel and Vite application. | No. |
| `npm test` | MCP descriptors/protocol, simulation contracts, atomic-launch guard, loopback auth, path policy, redaction, safe stop, and source-only behavior. | No. |
| `npm run test:python` | Scene policy, telemetry, and actual OpenUSD authoring/undo/export when `pxr` is installed. USD-dependent skips are reported explicitly. | No Kit; temporary test USD only. |
| `npm run test:web` | Builds the real panel, validates its MCP resource/bundle contract, then removes generated test output. | No Kit / no USD. |
| `npm run audit:public` | Verifies that publication scope excludes generated/dependency/runtime material, local paths, and common secret patterns. | No. |

No GitHub Actions workflow is currently versioned in this repository. Until a workflow is added and a run is observed, report these commands as local source checks, not CI evidence.

## Installed-product gate

Run:

```bat
installer\test.cmd
```

`Test-OmniStream.ps1` performs the following steps in order:

1. source and TypeScript contracts;
2. MCP/security tests;
3. panel build/resource contract;
4. final panel build;
5. strict environment/configuration doctor;
6. NVIDIA project `repo.bat test`, unless explicitly skipped;
7. real `npm run test:runtime`, unless explicitly skipped.

The report is written to:

```text
%LOCALAPPDATA%\OmniStream\state\validation-report.json
```

The runtime smoke test exercises the product workflow against real Kit:

**Configure → Preflight → Launch → Supervise → Read bounded logs → Control → Camera navigation/save → Safe stop**.

It verifies that credentials are not exposed in ordinary structured results or log diagnostics and uses a temporary USD fixture rather than modifying a user's scene.

The runtime smoke command is available locally, but no self-hosted GitHub Actions workflow is currently versioned in this repository.

## RC-to-stable promotion gate

`1.0.0-rc3` must remain an RC until all of the following are true on the intended target machine:

- `installer\test.cmd` passes with **no skip flags**;
- a decoded RTX/WebRTC frame is visible in the Codex panel;
- focused pointer/keyboard input reaches the live Kit viewport;
- the Simulation Deck can configure, preflight, launch, supervise, and control a real stage deliberately provided by the operator;
- safe runtime stop leaves no managed Kit process or signaling listener behind;
- repair and rerun retain normalized configuration and external NVIDIA ownership boundaries.

Only after that evidence should the version be promoted to `1.0.0`.

## Manual Codex visual gate

Automated runtime tests still do not prove that a particular Codex Desktop build rendered the embedded video. Verify that:

1. `ui://omnistream-for-codex/panel.html` loads after the local panel build.
2. Config validation does not start Kit.
3. Launch reaches ready states for the managed process, signaling, authenticated bridge, and selected stage.
4. Supervision updates while runtime/timeline state changes.
5. The connection overlay disappears after a decoded RTX frame arrives.
6. Play/pause/reset/step/seek/rate/loop work without terminating Kit.
7. Viewport input works after focus.
8. Runtime stop completes cleanly.

Record this separately from the machine-readable validation report.

## Additional RC3 gates

`npm test` includes 12 Node scene/event tests, 12 public-integrity tests, panel contracts, release checks, and the MCP protocol suite. On Windows, release checks also execute the prerequisite probes and validation-report serialization under Windows PowerShell. `npm run test:python` runs 17 Python tests independent of Kit and 17 additional tests requiring real `pxr`, including cadence changes and export. If `pxr` is unavailable, those 17 tests are **SKIPPED**, never counted as passes. No CI workflow is currently versioned here, so there is no current CI result to report for this candidate.

For an isolated OpenUSD installation on Windows:

```powershell
$usdVenv = Join-Path $env:TEMP 'omnistream-usd-rc3'
python -m venv $usdVenv
& (Join-Path $usdVenv 'Scripts\python.exe') -m pip install usd-core==26.8
& (Join-Path $usdVenv 'Scripts\python.exe') -m unittest discover -s tests -v
```

Keep the virtual environment outside the release tree. `usd-core` supplies OpenUSD bindings; it does not supply Kit or PhysX. Record the installed version and require zero skips for the native USD candidate gate.

The runtime smoke test now includes preview/apply/undo for USD animation and monitoring with a local duration limit. `npm run test:physics` adds a drop test that must observe displacement in USD. It fails without PhysX capability or USD-visible motion. A solver that uses Fabric only needs a different measurement adapter.

The PowerShell report explicitly separates automatic checks from `visualWebRtcVerified`, `codexHostVerified`, and `productionReady`, which remain false: scripts do not grant themselves visual certification. Automated success alone is not a stable-release promotion.

See `QA-REPORT.md` for the results actually obtained, local versions, and checks not run.

## RC3 public checks

`npm test` also includes 12 UI/state-integrity tests and 7 distribution tests (rejecting binaries, null bytes, dependencies, oversized files, and symbolic links; Windows packaging contract). `npm run test:panel-source` checks source without claiming to check a bundle. `npm run test:web` keeps the Vite build and real-bundle checks as distinct required steps.

The RC3 browser harness used the real React source and local NVIDIA SDK, first without a host, then with the real MCP process through a test-only IPC adapter. No scene/Kit/WebRTC result was fabricated for this check. This demonstrates the no-runtime workflow and actual errors, not editing in Kit or video. See the report for this release.
