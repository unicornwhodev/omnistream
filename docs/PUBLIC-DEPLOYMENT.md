# Public distribution — RC3

## Target for this release

An **installable local application for a Windows RTX machine**, integrated with Codex. This is not a SaaS offering, multi-user server, or renderer available at a public URL. The control bridge remains authenticated and bound to loopback. Do not expose it through port forwarding or a public tunnel.

The distribution contains OmniStream source, its bridge, installer, tests, and documentation. NVIDIA components and web dependencies are obtained on the target machine. The bundle containing the WebRTC SDK is built locally and is never included in this ZIP.

## No implicit demo workflow

Installation creates required directories but injects no scene, animation, fictional configuration, or telemetry. The operator must choose a real USD file. Files under `tests/fixtures` and `mcp/fixtures` are used only by explicit tests, on temporary copies. Protocol test doubles are not imported by the production interface and never provide its responses.

Initial values visible in the configuration, such as initial time or cadence multiplier, are settings to apply, not measurements. Missing measurements remain unknown. A truncated or old diagnostic cannot establish that the entire scene is valid. A ready port does not make video active: a frame must be decoded.

## User workflow

Install prerequisites with the wizard, let the checks finish, and load the local plugin. Choose the workspace and USD file. Validate the configuration, review preflight, then launch. Inspection and editing are available only after the bridge has connected successfully. Navigation remains available for checking installation, status, and errors.

The studio distinguishes session configuration, runtime, USD content, playback transport, supervision, and diagnostics. Forms are not refreshed from old configuration while the operator is typing. Animation keys are entered by the operator or captured from a recognized real TRS stack; no demo rotation is preloaded.

## Pre-publication checks

| Check | Status for this release |
|---|---|
| Source, TypeScript, protocol, and UI contracts | Run locally: PASS |
| Integrity and absence of redistributed dependencies/binaries | Verified on a clean extraction |
| Real panel, navigation, and errors from the real MCP without Kit | Run with Chromium and a test transport adapter |
| Production Vite build / clean install | Not verified here: missing native dependency, installation network unavailable |
| Windows + RTX + Kit + PhysX | To qualify on the target machine |
| Video decoding and interaction in actual Codex | To verify on the target machine |
| Windows install/resume/repair/uninstall | Scripts reviewed, not run here |
| Public licence and any catalogue submission | Rights holder decision/action; not done |

The code remains `1.0.0-rc3` and `UNLICENSED`. Do not present this archive as certified stable, open source, or a plugin already accepted into a catalogue.

## Validation record to retain

After a clean installation, retain `validation-report.json` and exact versions of Windows, GPU/driver, Kit, extensions, WebRTC SDK, Node, and Codex. Add a real observation of video and viewport interactions. Run `npm run test:physics`: passing requires observable physical displacement, not merely a launch response. Also try external stop, reconnect, path error, bridge loss, export without overwriting, install resume, and uninstall that preserves NVIDIA and user data.

The local test for this release did not open a real Kit application. It showed that the absence of Kit remains an absence, with actual MCP errors, rather than a demo state.

## Maintenance references

- Official UI integration API: https://developers.openai.com/plugins/reference
- NVIDIA SDK and documentation matching the installed package: https://docs.omniverse.nvidia.com/ov-web-sdk/latest/web-streaming-library/overview.html
- `Compress-Archive` limitations for hidden files: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.archive/compress-archive

The source pins its SDK version. An SDK update must go through qualification again; changing only the version in the lockfile is insufficient.
