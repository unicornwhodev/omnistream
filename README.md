# OmniStream for Codex — 1.0.0-rc3

A local studio for controlling **a real NVIDIA Omniverse Kit scene** from Codex: configure a session, launch the runtime without a native window, inspect and edit USD, control animation and rigid bodies, observe telemetry, and diagnose errors. The browser receives the WebRTC render; it does not replace it with a local 3D scene.

**Status: release candidate, not a certified stable release.** Windows source/build checks, 34 actual OpenUSD tests, installed Kit/control tests, PhysX displacement, and the FireViewer Die–Pontaix map workflow passed on the recorded Existing runtime. Actual Codex video, viewport input, and dialogs remain acceptance gates. See the [October 1 qualification report](docs/QUALIFICATION-2026-10-01.md) for the exact target and limitations.

## Install

On the target Windows RTX machine, extract the archive and run:

```bat
installer\install.cmd
```

The wizard checks prerequisites, opens the required external sources, waits for the operator to complete installations or accept terms, then resumes. The archive contains no Kit, compiled NVIDIA runtime or extension, prepackaged WebRTC SDK, or generated bundle. Dependencies are obtained on the target machine. By default, the installed plugin is under `%LOCALAPPDATA%\OmniStream\plugin`.

The workspace and asset folder are created **empty**. No sample scene, canned animation, decorative statistic, or fabricated telemetry is installed. Use your own trusted USD file. The development mode is not launched by the installer and does not replace the production transport.

[Quick start](docs/QUICKSTART.md) · [Installation and recovery](docs/INSTALLATION.md) · [Preparing a public distribution](docs/PUBLIC-DEPLOYMENT.md)

## Choose a workflow

- **Open a new scene:** configure the workspace and USD file, run preflight, then start the Kit session from **Launch**.
- **Work on the scene that is already open:** use the active OmniStream Kit session, inspect the stage in **Scene**, then preview and apply corrections. Do not relaunch the simulation for a simple correction: launch loads the configured stage.

The second workflow applies to a scene opened in the runtime managed by the current MCP session; OmniStream does not automatically attach to a Kit process launched independently. See the [open-scene guide](docs/LIVE-SCENE.md) and the [documentation index](docs/README.md).

## Interface

The studio has a dominant viewport, side navigation, and task inspector: **Configure / Launch / Scene / Control / Supervise / Diagnostics**. The current application displays these section names in French: **Configurer / Lancer / Scène / Contrôler / Superviser / Diagnostic**. It uses a graphite palette with green accents, readable fields, keyboard navigation, and a responsive layout. Playback controls remain directly below the viewport.

A typed path remains a draft until validated; it does not mean that a scene is loaded. Missing values are marked “Not verified” (“Non vérifié”) or “—”. Video is marked active only after a frame is decoded, not merely when a port is open. Scene commands are disabled without an authenticated bridge. Periodic supervision does not overwrite form input.

## What Codex can actually request

| Workflow | Main tools |
|---|---|
| Prepare the runtime | `configure_omniverse_simulation`, `preflight_omniverse_simulation` |
| Start or attach | `launch_omniverse_simulation`, `attach_omniverse_stream` |
| Inspect the scene | `inspect_omniverse_scene`, `inspect_omniverse_prim` |
| Correct without writing the source | `preview_omniverse_scene_patch`, `apply_omniverse_scene_patch`, `undo_omniverse_scene_patch` |
| Run and control | `run_omniverse_scene`, `control_omniverse_simulation` |
| Observe and debug | `supervise_omniverse_simulation`, `read_omniverse_live_telemetry`, `diagnose_omniverse_scene`, `read_omnistream_runtime_logs` |
| Keep or discard changes | `export_omniverse_scene_patch`, `discard_omniverse_scene_edits` |

[MCP reference](docs/MCP-REFERENCE.md) · [Open scene, physics, and animation](docs/LIVE-SCENE.md)

Editing covers TRS transforms, animation keys, approved physical properties, colliders, rigid bodies, and gravity. This is not a complete editor for robots, fluids, skeletal animation, or OmniGraph. The presence of USD schemas does not prove that PhysX is available. Target cadence is not a guaranteed physical speed.

## Security and data

The managed runtime is local, its control bridge is authenticated and bound to loopback, the workspace is bounded, operations are serialized, and observation has explicit limits. Previews are tied to a scene revision and expire; edits can be undone in-session or exported to a new file. The model cannot send arbitrary Python. Explicit camera saving remains an exception that writes to an authorized source file.

Closing the panel does not stop Kit; closing its MCP session triggers a safe stop. Unexported corrections are lost when the runtime stops. Undoing a patch does not deterministically rewind the solver. The product is not a standalone Windows service or an internet-hosted multi-user rendering server.

[Architecture](docs/ARCHITECTURE.md) · [Security](docs/SECURITY.md) · [Troubleshooting](docs/TROUBLESHOOTING.md)

## Verify

After obtaining dependencies on the target platform:

```powershell
npm --prefix .\web ci
npm run check
npm test
npm run test:python
npm run test:web
npm run build:web
```

The native tests `npm run test:runtime` and `npm run test:physics` use test USD files in temporary copies. These files remain separate from the product and the user's workspace. Test results are never displayed as real telemetry. Visible qualification in Codex is a separate gate.

From a freshly extracted archive, run `npm run verify:release -- --strict` and then `npm run audit:public`. The manifest checks file integrity; it is not a digital signature.

[Validation](docs/VALIDATION.md) · [Release checklist](docs/RELEASE-CHECKLIST.md) · [Changelog](CHANGELOG.md) · [Third-party notice](THIRD_PARTY.md)

## Version, downloads, and licence

The source version is `1.0.0-rc3`, targeting Windows 10/11 x64 with an NVIDIA RTX GPU. This repository is public, but the software remains `UNLICENSED`: no open-source licence has been selected. The npm package is not published (`private: true`). As checked on October 1, 2026, no tag or release artifact has been published on GitHub. The [Releases page](https://github.com/unicornwhodev/omnistream/releases) will list downloads when a candidate is published.

Build the source-only Windows archive with:

```powershell
.\installer\Build-Release.ps1
```

The script creates a ZIP and its `.sha256` file under `release/`. The ZIP excludes Kit, NVIDIA binaries, WebRTC dependencies, and the generated bundle. The digest detects file changes but is not a signature. Tagging, release-candidate, and distribution criteria are described in [Versions and distribution](docs/RELEASING.md). No npm package or stable GitHub release is announced here.

## Public distribution

This release-preparation pass covers local software distribution; it does not publish the plugin in a catalogue or expose any Kit port to the internet. No licence has been selected, so the project remains `UNLICENSED`. Do not describe it as open source until the rights holder has made that decision.
