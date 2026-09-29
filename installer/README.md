# OmniStream Windows installer

Use `install.cmd` for normal installation. The installer is an **orchestrator**, not a NVIDIA redistributor: NVIDIA Kit/WebRTC dependencies are acquired from NVIDIA by the operator on the target machine, validated, then used to build OmniStream locally.

## Commands

```text
install.cmd      install/resume and qualify
repair.cmd       reuse the configured external Kit project and repair OmniStream
diagnose.cmd     strict local configuration/runtime diagnosis
test.cmd         full product qualification, including runtime smoke
uninstall.cmd    remove OmniStream-owned plugin files
```

## Runtime channel

`install.cmd` defaults to `-RuntimeChannel Auto` and asks when no compatible Kit project is already known:

- **Production** — recommended product path; uses the official NVIDIA Production Branch SDK acquisition/project workflow.
- **Existing** — uses a project you already obtained/built from NVIDIA.
- **Feature** — clones the official `NVIDIA-Omniverse/kit-app-template` repository for development/prototyping.

OmniStream never accepts NVIDIA terms on the operator's behalf and never copies NVIDIA runtime binaries into its release archive.

## Resume and state

Installer state is persisted at:

```text
%LOCALAPPDATA%\OmniStream\state\install-state.json
```

The checkpoint retains the install root, Kit root, workspace, asset root, selected streaming layer and runtime channel. Rerunning the installer revalidates these values instead of blindly trusting the previous phase.

A release archive also includes `release-manifest.json`; the installer verifies each listed file's size and SHA-256 hash before installation and rejects unexpected source files outside known local generated directories. The manifest is not a digital signature.

## Validation report

A normal install ends with `Test-OmniStream.ps1`. Its machine-readable result is:

```text
%LOCALAPPDATA%\OmniStream\state\validation-report.json
```

A PASS without `-SkipRuntimeSmoke` is the local qualification gate for Kit + WebRTC + bridge + USD/timeline/camera control.

## Uninstall boundary

`Uninstall-OmniStream.ps1` removes the OmniStream plugin by default. It deliberately preserves:

- the separately acquired NVIDIA Kit project;
- `%LOCALAPPDATA%\OmniStream\config` unless `-RemoveConfiguration` is requested;
- the Documents workspace unless `-RemoveWorkspace` is requested.

The external NVIDIA project is never removed by this uninstaller.
