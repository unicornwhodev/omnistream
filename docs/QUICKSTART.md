# Quick start

This guide covers installation and the studio's two workflows: launch an operator-selected USD file or continue working on a scene already open in the managed Kit session.

## 1. Extract and install

On the Windows RTX machine that will run Omniverse Kit, extract the OmniStream release to a normal local folder and run:

```bat
installer\install.cmd
```

The installer verifies the release manifest before copying source files. It then checks Node/npm, Git, and the NVIDIA driver. NVIDIA Kit/WebRTC components are **not bundled**: if they are missing, OmniStream opens or invokes the official NVIDIA acquisition/setup flow, waits for the operator to complete any NVIDIA terms, login, or template steps, validates the resulting local project, and resumes.

For a product-oriented installation, choose **Production** when prompted. Choose **Existing** only if you already have a compatible Kit project. Use **Feature** for development/prototyping, not qualification.

## 2. Let installation qualification finish

A normal install ends by running the product validation script. A locally qualified installation must finish with:

```text
VALIDATION OMNISTREAM: PASS
```

The machine-readable report is stored at:

```text
%LOCALAPPDATA%\OmniStream\state\validation-report.json
```

If the runtime smoke test was skipped, the installation can be used for diagnosis/development but is **not qualified as stable** until `installer\test.cmd` succeeds without skip switches.

## 3. Load the local plugin in Codex

The default installed plugin root is:

```text
%LOCALAPPDATA%\OmniStream\plugin
```

Load/import that local plugin in Codex, then open **OmniStream for Codex**.

## 4. Choose a workflow

### Open a new scene

The installer creates no sample content. The user workspace remains empty. Place a trusted USD file in the configured workspace. Do not open an unfamiliar file without checking its dependencies/extensions.

In **Configure** (currently **Configurer**), select the workspace and use **Scan** (currently **Scanner**), or enter the path to your real file. Validate the configuration. In **Launch** (currently **Lancer**), review preflight and launch when the required checks pass. An available signaling port does not prove that a frame is being received. Wait until your actual scene appears in the viewport.

### Continue with the scene already open

This workflow applies to Kit managed by the current MCP session. If the runtime is ready but the panel has lost its stream, use **Attach** (currently **Rattacher**) in **Launch** or call `attach_omniverse_stream`. Do not call `launch_omniverse_simulation` for a correction: launch opens the USD file saved in the configuration. A separately started Kit process is not automatically adopted.

In **Scene** (currently **Scène**), inspect the stage and object before making changes. Preview the correction, then apply the still-valid preview. Physics controls depend on the capability Kit actually reports. In **Control** (currently **Contrôler**), use play, pause, stop, frame stepping, and seek; target cadence does not promise solver time dilation. **Supervise** (currently **Superviser**) and **Diagnostics** (currently **Diagnostic**) distinguish runtime, video, bridge, scene, logs, and measurements.

If no scene or measurement is available, the interface says so instead of substituting demo data. Scene corrections remain in the session: export them before stopping Kit. Camera saving is a separate source write that requires explicit confirmation.

## 5. Recover if something fails

```bat
installer\diagnose.cmd
installer\repair.cmd
installer\test.cmd
```

`repair.cmd` reuses the existing external Kit project and does not delete or redownload NVIDIA software. See [Troubleshooting](TROUBLESHOOTING.md) for guidance specific to each failure.
