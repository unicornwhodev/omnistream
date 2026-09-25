# Installation

## Supported target

OmniStream's managed runtime targets **Windows 10/11, x64, with an NVIDIA RTX-capable GPU**. The runtime launcher, process-identity checks and Kit/WebRTC qualification are Windows-specific in this release candidate.

Normal entry point:

```bat
installer\install.cmd
```

The release is intentionally source-only for NVIDIA components. OmniStream does not contain or mirror Kit SDK binaries, extension caches, a Kit `_build`, `@nvidia/ov-web-rtc`, or a generated WebRTC panel bundle.

## Installation flow

The installer performs these phases and checkpoints each one in `%LOCALAPPDATA%\OmniStream\state\install-state.json`:

1. verify `release-manifest.json` hashes/sizes and reject unexpected source files;
2. verify Windows, Node.js 20.18.1+, npm 10.2.3+, Git and `nvidia-smi`;
3. atomically install OmniStream source under `%LOCALAPPDATA%\OmniStream\plugin` by default;
4. select and validate a NVIDIA Kit project using one of the runtime channels below;
5. add the **OmniStream-owned** `omnistream.codex.bridge` source to that external project and patch the selected streaming `.kit` source layer;
6. invoke NVIDIA's project build tooling and validate the built `kit.exe` plus streaming layer;
7. run `npm --prefix .\web ci` against the configured NVIDIA npm registry and build the Codex panel locally;
8. save the normalized non-secret configuration;
9. run source/MCP/panel/doctor/Kit/runtime qualification unless explicitly skipped.

If the process is interrupted, run `installer\install.cmd` again. Recorded paths and phases are recovered and every prerequisite is revalidated before it is trusted.

## NVIDIA runtime channels

### Production — recommended for qualification

Choose **Production** for the release/qualification path. OmniStream opens the official NVIDIA Kit SDK Production Branch acquisition page and accepts either:

- an already generated Kit project containing `repo.bat`; or
- an extracted NVIDIA SDK root containing `new_project.bat`, which OmniStream invokes and then waits for the operator to provide the generated project root.

NVIDIA login, download, licence/terms acceptance and project/template choices stay in NVIDIA's own workflow. OmniStream does not automate acceptance or redistribute the resulting binaries.

### Existing

Use an existing compatible project containing `repo.bat`:

```powershell
.\installer\Install-OmniStream.ps1 `
  -RuntimeChannel Existing `
  -KitRoot 'C:\path\to\your-kit-project' `
  -SkipNvidiaRuntimeSetup
```

The existing project must already contain a streaming `.kit` source layer when `-SkipNvidiaRuntimeSetup` is used. OmniStream still installs/updates its own bridge source and invokes the NVIDIA build so the generated runtime matches the bridge.

### Feature — developer/prototype path

Feature mode clones NVIDIA's official `kit-app-template` repository directly and can run NVIDIA's `repo.bat template new` wizard. It is retained for development and prototyping; do not use it as the release-candidate stability gate when a Production Branch project is available.

## Template / streaming layer

If the selected Kit project has no streaming application and NVIDIA runtime setup is allowed, OmniStream invokes:

```text
repo.bat template new
```

Choose a compatible application (USD Viewer is the preferred minimal viewer) and include **Omniverse Kit App Streaming (Default)**. The exact `*_streaming.kit` source filename is discovered and stored in OmniStream configuration; no legacy project-specific runtime name is hard-coded.

Expected built layout:

```text
<kit-root>\
  _build\windows-x86_64\release\
    kit\kit.exe
    apps\<selected-streaming-layer>.kit
```

## Normalized paths

```text
%LOCALAPPDATA%\OmniStream\
  plugin\                  installed OmniStream source + locally built panel
  config\omnistream.json   normalized non-secret configuration
  logs\                    managed Kit stdout/stderr/PID logs
  state\                   install + validation reports
  cache\                   OmniStream cache
  external\                optional Feature-channel checkout

%USERPROFILE%\Documents\OmniStream\
  Workspace\               bounded root-stage workspace
  Assets\                  default local asset root
```

The installer creates only the required empty directories. It never installs a sample stage, animation, telemetry or simulated runtime into the user workspace. Test fixtures remain under the test tree and are only used by explicit test commands.

## Validation during installation

By default the installer runs `installer\Test-OmniStream.ps1`, including the real runtime smoke. A PASS records `%LOCALAPPDATA%\OmniStream\state\validation-report.json`.

Diagnostic/development switches exist, but change the qualification status:

- `-SkipValidation`: installs without product qualification;
- `-SkipRuntimeSmoke`: runs source/Kit checks but does not prove the live Kit/WebRTC/bridge path;
- `-SkipNvidiaRuntimeSetup`: requires an existing suitable Kit project.

An installation made with either of the first two switches must not be described as locally stable until `installer\test.cmd` passes without skip switches.

## Repair, diagnosis and uninstall

```bat
installer\diagnose.cmd
installer\repair.cmd
installer\test.cmd
installer\uninstall.cmd
```

- **Diagnose** performs the strict local doctor check and points to state/validation reports.
- **Repair** reruns installation against the existing configured Kit project without cloning or replacing NVIDIA runtime content.
- **Test** runs the full local qualification gate.
- **Uninstall** removes the OmniStream plugin by default and leaves the external NVIDIA project, configuration and workspace untouched. Use `-RemoveConfiguration` and/or `-RemoveWorkspace` only when those OmniStream-owned locations should also be deleted.

The uninstaller never removes the external NVIDIA Kit project.
