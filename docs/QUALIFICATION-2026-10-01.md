# Windows qualification — October 1, 2026

## Verdict

**Version: `1.0.0-rc3`.** Local source checks, real OpenUSD editing, the installed Kit/control smoke test, PhysX displacement, and the operator's FireViewer map workflow passed. This remains a release candidate. Video decoding, viewport input, and confirmation dialogs in the actual Codex host have not been verified.

This report supersedes the earlier source-only results in [QA-REPORT.md](../QA-REPORT.md). That earlier report is retained as historical evidence; its dependency and USD limitations no longer describe this Windows run.

## Target and runtime identity

| Component | Observed configuration |
|---|---|
| GPU | NVIDIA GeForce RTX 5070 Ti, 16,303 MiB |
| NVIDIA driver | 616.56 |
| Node / npm | 24.14.0 / 11.9.0 |
| Standalone Python / OpenUSD | Python 3.11.9; isolated `usd-core==26.8` |
| NVIDIA WebRTC client | `@nvidia/ov-web-rtc` 6.6.0, obtained from the configured NVIDIA registry |
| Runtime channel | **Existing**, a separate local qualification project derived from the operator's FireViewer Kit project |
| Template Git revision | `483e364a4176f102f2d3c3aaf9f301a103d61d69` |
| Kit kernel | `110.2.0+feature.windows-x86_64.release` |
| Application | `omnistream.runtime_streaming.kit`, using the existing FireViewer USD Composer application and OmniStream bridge |

The qualification project is isolated from the original FireViewer project. The installer builds NVIDIA dependencies through that project's `repo.bat`. This **does not qualify Production Branch PB 26h1** or establish portability to other Kit builds. NVIDIA components and the FireViewer map are external to OmniStream's source archive.

## Automated gates

| Gate | Result and scope |
|---|---|
| Clean Windows `npm --prefix .\web ci` | PASS; the lockfile includes optional platform packages. |
| `npm run check` | PASS; Node syntax and application/Vite TypeScript. |
| `npm test` | PASS; MCP protocol, 12 scene/event checks, 12 public-integrity checks, panel contracts and release checks. The release suite has one explicitly skipped Windows file-symlink test. |
| `npm run test:python` | **34 PASS, zero skipped** with actual OpenUSD. |
| `npm run test:web` | PASS; the Vite production bundle and MCP/panel resource contracts. Generated test bundles are removed afterwards. |
| Clean-tree publication audit | PASS on staged/extracted candidate source; local evidence and dependencies are excluded. |
| ZIP and SHA-256 | PASS; source-only candidates built with `Build-Release.ps1`, including hidden plugin metadata. |
| Fresh extraction / strict manifest | PASS; sizes, hashes, required metadata, version agreement and no extra source files. |
| NVIDIA `repo.bat test` | PASS; includes four OmniStream bridge tests in actual Kit. |
| Full installed validation | **PASS**, without `SkipRuntimeSmoke` or `SkipKitTests`. |
| `npm run test:physics` | **PASS**; actual falling-body displacement observed through USD, with source unchanged. |
| Safe shutdown | PASS; managed process, signaling listener and authenticated bridge are absent after stop. |
| Resume / repair | Resume passed after interrupted installations. The repair CMD path is also exercised from PowerShell 7. |
| Uninstall | PASS on the actual installed plugin; Kit project, configuration, operator map and exported override hashes were preserved. Separate selected-cleanup checks preserve external NVIDIA/assets and unrelated user environment settings. |

The full validation report records:

```json
{
  "ok": true,
  "runtimeSmokeSkipped": false,
  "kitTestsSkipped": false,
  "visualWebRtcVerified": false,
  "codexHostVerified": false,
  "productionReady": false
}
```

Automatic PASS covers native lifecycle/control and signaling. These false visual/host fields remain intentional. No GitHub Actions execution or independent security audit is claimed.

## Operator scene: FireViewer Die–Pontaix

The operator selected a FireViewer map of Die. Qualification used the existing package **`fireviewer-die-pontaix-map-r5`**, entry stage `map.usda`, copied into a dedicated workspace. The installer-created workspace and asset directory were empty before this explicit import.

Entry-stage SHA-256:

```text
fa6f2a43bc06b9aab8d8abafc181b6f4deed2b1957a6ce277bfe1d06f4a66f6c
```

All **296 copied files** matched their source hashes. OpenUSD resolved **149 layers and 26 assets with zero unresolved dependencies**. The stage uses metres and a Z up axis.

The real MCP controller and Kit bridge exercised:

1. Configure → Preflight → Launch → Supervise → Control on that map.
2. Inspect `/World/Sun`, an actual `DistantLight`, and capture its existing TRS.
3. Preview and apply a reversible session animation from the captured rotation `[24, -18, 42]` to `[24, -18, 43]` over two seconds.
4. Observe the real `xformOp:rotateXYZ:omnistream` value through fresh Kit telemetry and confirm paused playback.
5. Export a new `qualification-sun-override.usda` file inside the bounded workspace.
6. Undo the session patch and verify the original TRS and all 296 map-file hashes.
7. Stop Kit and verify no managed process, signaling listener or control bridge remains.

This verifies the requested editing/control workflow. It does not assess fire simulation, geographic accuracy, the map's visual quality, or physical behaviour of its vegetation/buildings. The PhysX gate uses a separate temporary rigid-body fixture.

## Fixes found during qualification

- Restore 49 optional platform entries in the dependency lockfile; update the transitive Nano ID package to 3.3.19. The subsequent clean installation reports zero known npm audit findings.
- Preserve prerequisite-probe arguments and use the correct Windows invocation for npm diagnostics.
- Support both source-only and already-built panel states in the MCP tests.
- Serialize validation check lists correctly in Windows PowerShell.
- Give CMD entry points the default Windows PowerShell module lookup when invoked from PowerShell 7.
- Stage the Python bridge through a Kit extension `premake5.lua`; copying source alone was insufficient.
- Treat a completely unconfigured bridge as intentionally disabled; invalid partial/non-loopback configurations still fail closed.
- Preserve animation times in seconds across cadence changes and override export.
- Persist camera matrix opinions without adding a duplicate composed transform op, and reacquire the camera after Kit updates.
- Verify uninstall product identity and protected paths before removing selected directories.
- Enforce version agreement in strict release verification and keep source checkout text in LF form for consistent hashes.

## Remaining acceptance gates

| Gate | Status |
|---|---|
| Decoded RTX/WebRTC frame in actual Codex | **Not verified** |
| Viewport pointer and keyboard input | **Not verified** |
| Confirm/cancel dialogs in actual Codex | **Not verified** |
| Production Branch runtime qualification | **Not performed**; the exact Existing stack is recorded above. |
| Licence and stable/public package publication | **Not authorized**; `private: true` and `UNLICENSED` remain. |

The local plugin was registered with the Codex CLI. Browser and native UI automation failed to initialize with `failed to write kernel assets` / Windows `os error 3`, including after a kernel reset. Refreshing the plugin cache also returned Windows access denied. Neither registration nor a ready signaling port establishes host video/input acceptance.

## Evidence and reproduction

Local logs, machine-specific JSON receipts, the isolated USD environment, the external Kit project, the map copy and candidate archives are kept under the ignored `release/qualification-20261001/` directory. They are not part of the published source. Relevant receipts include `validation-report-install-07.json`, `validation-report-final.json` (the actual `test.cmd` run without skip flags), `native-physics.log`, `fireviewer-map-receipt.json`, `fireviewer-runtime-receipt.json`, `uninstall-real-install-receipt.json`, and the repair/installer logs.

For another target, follow [Installation](INSTALLATION.md), [Validation](VALIDATION.md), and the [release checklist](RELEASE-CHECKLIST.md). Run the source commands against that target's dependencies, then run `installer\test.cmd` and `npm run test:physics` without suppressing native gates. Record Codex video/input/dialog evidence separately and verify the source archive before installing it.
