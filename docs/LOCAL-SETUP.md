# Local setup and reproducible qualification

This guide applies to the Windows `1.0.0-rc4` candidate. See the
[October 21 local qualification](QUALIFICATION-LOCAL-2026-10-21.md) for measured
results, and the [October 23 Codex fixes](QUALIFICATION-CODEX-2026-10-23.md)
for the opening/layout regression and current host evidence. Remote sessions are outside
this local qualification.

## Prerequisites and installation

Use Windows x64, an NVIDIA RTX GPU with a working NVIDIA driver, Node.js
20.18.1 or later, npm 10.2.3 or later, and Git. Check `nvidia-smi` before setup.
Allow space for the external Kit project and its extension/build caches.
The measured target is an RTX 5070 Ti with 16 GB; this is not a minimum-VRAM
benchmark or a promise for other GPUs.

From a clean source archive, verify its SHA-256 and run:

```powershell
npm run verify:release -- --strict
npm run audit:public
.\installer\install.cmd
```

The installer obtains dependencies on the target computer; NVIDIA components
and the generated WebRTC bundle are excluded from the repository. Choose
Production for a new qualification installation, or Existing for an already
compatible Kit project. NVIDIA login and licence acceptance remain operator
steps. This run reused Existing; it does not certify a fresh Production install.

The default plugin location is `%LOCALAPPDATA%\OmniStream\plugin`. Load that
folder as a local plugin in Codex. Rebuild the bundle and open a new panel instance
after UI changes. Reload the MCP controller when tool schemas, entrypoints or
controller configuration change; the panel and controller must belong to the
same candidate.

The opening tool declares a conversation side-panel entrypoint. Its UI resource
now prefers `fullscreen`, and the initialized Apps client makes one bounded
request for that expanded host surface. A refused display request does not
disable controller access. Actual opening still needs to be observed in Codex;
these declarations alone do not certify it. The current UI resource is
`ui://omnistream-for-codex/panel-rc4-layout.html`. Reload the plugin's MCP
controller after an update so Codex discovers its current schema and entrypoint;
close old cards before opening the new resource. The inline layout uses content
height and must stop resizing once its contents have settled.

The embedded panel must complete the standard MCP Apps initialization before
calling tools. The official Apps SDK performs this handshake and retains private
tool-response metadata. The presence of `window.openai` alone does not establish
readiness. An initialization timeout in the Codex host logs is a failed host
integration, even if the interface was briefly visible. Keep a new panel open
past the initialization period and verify its controls and decoded video.

## Local transport

Configuration is stored in `%LOCALAPPDATA%\OmniStream\config\omnistream.json`,
or under `OMNISTREAM_HOME` when explicitly configured. Follow
[Configuration](CONFIGURATION.md) for the complete schema. Keep actual workspace
paths and any remote profile/credential references out of commits.

For an embedded host that blocks direct WS signaling, an existing local
configuration can select:

```json
"panelSignalingTransport": "mcp"
```

This routes signaling through the authenticated MCP controller. Video remains
the actual NVIDIA WebRTC stream. It creates no certificate or public endpoint.
An existing TLS configuration stays inactive in this mode. WSS is a separate
option requiring an already trusted localhost certificate; setup never installs
trust automatically. The diagnostic validates configuration shape; preflight
checks the live requirements.

## Use a real local scene

1. Place a trusted USD file and its required assets below a dedicated workspace.
2. Open OmniStream in Codex. In **Configurer**, enter the workspace and stage,
   then validate. Validation must not start Kit.
3. In **Lancer**, run preflight, inspect its result, and launch the validated
   configuration. Readiness requires the owned Kit process, signaling,
   authenticated bridge, and loaded stage. Video is a separate indicator:
   wait for an actual decoded frame.
4. Inspect the current scene before editing. Preview/apply corrections in the
   session layer, then run bounded animation/physics. Pause or stop before undo.
   Use camera selection/navigation without saving the source during ordinary
   inspection. An explicit camera save can write the source file.
5. Reattach a lost panel to the existing managed session. Do not relaunch/reload
   the stage just to regain its stream or correct an object.
6. Stop playback to keep Kit open, or use **Arrêter Kit** to end the owned
   runtime. Verify that process, signaling and bridge are all absent afterward.

Unexported session corrections disappear when Kit stops. Export to a new USD
override only when requested. USD references can resolve dependencies outside
the selected root: workspace bounds are not a complete asset sandbox.

## Reproduce automatic checks

From the source directory with its dependencies available:

```powershell
npm --prefix .\web ci
.\installer\test.cmd
npm run test:physics
```

`test.cmd` runs source/TypeScript checks, MCP and panel tests, a built-panel
contract, a final build, strict doctor, NVIDIA project tests and the actual
runtime smoke. Do not use skip switches for a complete automatic qualification.
The report is `%LOCALAPPDATA%\OmniStream\state\validation-report.json`.
This report deliberately does not grant itself visual Codex certification.

For OpenUSD authoring tests, use an isolated Python environment with `usd-core`:

```powershell
$env:OMNISTREAM_REQUIRE_USD = '1'
python -m unittest discover -s tests -v
Remove-Item Env:\OMNISTREAM_REQUIRE_USD
```

Use the Python executable from that environment. A run with skipped USD tests
does not validate native USD editing. `usd-core` supplies neither Kit nor PhysX.

## Browser harness for diagnosis

```powershell
npm run build:web
npm run serve:panel-harness
```

Open the printed loopback URL in a local browser. The harness uses the actual
panel, MCP controller and configured Kit runtime. It does not fabricate video,
tool responses or telemetry. It is a development diagnostic, started explicitly;
the installer does not launch it and it does not certify the Codex host.

For a reproducible visual scene, copy
`tests/fixtures/local-qualification.usda` into a separate test workspace and
select `/World/FrontCamera`. The fixture is never installed as user content.
Record hashes before and after the test. Stop Kit through the panel before
closing the harness; Ctrl+C then closes its controller safely.

For video evidence, record dimensions, `readyState`, `currentTime` and decoded
frame counters twice, plus a screenshot of the rendered viewport. A signaling
connection or a timeline position alone is insufficient. Use native browser
input to qualify pointer/keyboard forwarding; synthetic DOM clicks are weaker
evidence and must be labelled accordingly.

## Current limits and recovery

The October 23 report tracks the Codex integration gate after the opening and
height fixes. The corrected panel has completed its Apps handshake and launched
Kit from the real Codex UI. Scene supervision and telemetry work in that run,
but video initially stops before a decoded frame is verified. The panel reports a
`connect-src` violation and Kit logs `NVST_R_INVALID_STATE`; their causal link
has not been established. Screenshot automation also fails, then UI automation
stops responding while the operator reports the panel remains usable. Record
these as separate failures. Do not widen CSP permissions without identifying
the blocked destination. Real host video, interactions and stability require
their own proof.
If no MCP Apps tab opens, record the host error and candidate identity; do not
interpret the text “studio opened” as proof that the UI rendered. Browser
harness evidence and automatic native tests remain separate results.

A subsequent isolated comparison reproduces the video disconnection in Chrome
with the same client. Restricting the local DirectConfig to H.264 then decodes
the real RTX scene without restarting that diagnostic Kit. Local streams now
request H.264 explicitly; automatic AV1/HEVC selection is not qualified. This
does not change external session profiles. The updated client still requires
an observed Codex panel run before the integrated video gate can pass.

Use `installer\diagnose.cmd`, inspect bounded runtime logs, and rerun preflight.
Repair preserves operator-configured `panelSignalingTransport`, `signalingTls`
and `remoteSessions`. Repair/uninstall still require their own lifecycle
qualification before a stable release; this run does not certify uninstall.

Telemetry is sampled at up to 4 Hz and the panel normally polls at 1 Hz. It is
not hard real-time. PhysX must actually be enabled and motion observed;
`kitUpdateMs` is not GPU FPS. No robotics, fluids, fire solver, skeletal
animation or arbitrary Python adapters are provided by this release.

Keep raw logs, screenshots, local configuration, test workspaces and runtime
files outside the public source tree. Inspect sanitized evidence and the exact
Git index before committing; use a public no-reply commit identity.

To check additional private names/addresses, supply a semicolon-separated
`OMNISTREAM_AUDIT_PRIVATE_MARKERS` environment value locally before running
`node scripts/publication-audit.mjs --index`. The auditor omits marker values
from its error messages; do not save those values in source or public receipts.
