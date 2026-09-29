# Release checklist

## Required for every candidate

- [ ] `npm --prefix .\web ci` succeeds on Windows using the configured NVIDIA registry.
- [ ] `npm run check` passes.
- [ ] `npm test` passes.
- [ ] `npm run test:python` passes with a real USD installation and zero skipped USD tests.
- [ ] `npm run test:web` passes.
- [ ] `npm run audit:public` passes from the clean candidate tree.
- [ ] `installer\Build-Release.ps1` creates a source-only archive and SHA-256 file.
- [ ] A freshly extracted archive passes `npm run verify:release -- --strict`, including plugin metadata and no unmanifested files.
- [ ] Archive contains no `node_modules`, `web-dist`, `_build`, Kit binaries/caches, credentials, logs, or machine-specific paths.
- [ ] Documentation version, plugin manifest, bridge extension version, and package versions agree.

## Required to promote an RC to stable

- [ ] Install from the release ZIP on a clean or representative Windows RTX machine.
- [ ] Use the intended **Production** NVIDIA runtime channel, or document the exact approved Existing project.
- [ ] `installer\test.cmd` passes without skip flags.
- [ ] `validation-report.json` has `ok: true`, `runtimeSmokeSkipped: false`, and `kitTestsSkipped: false`.
- [ ] The actual Codex panel shows a decoded RTX/WebRTC frame.
- [ ] Verify viewport pointer/keyboard input.
- [ ] Configure → Preflight → Launch → Supervise → Control works on a real USD provided by the operator.
- [ ] `npm run test:physics` observes actual displacement with the intended PhysX configuration.
- [ ] Verify current-scene edit / preview / apply / watch / undo / export on a real USD file.
- [ ] Safe runtime stop leaves no managed process/listener behind.
- [ ] Exercise repair/resume once.
- [ ] Uninstall preserves the external NVIDIA project and removes only selected OmniStream-owned paths.

## Public/open-source release administration

The repository currently declares the web package `UNLICENSED` and does not ship a project licence file. Before a public open-source/competition submission, the project owner must deliberately choose and add the intended licence. Do not infer or add an open-source licence automatically: that decision changes redistribution rights.

## RC3 public verification

- [ ] No sample USD is installed automatically; the workspace is empty.
- [ ] No test result or replacement transport is imported by the production front end.
- [ ] Connected/loaded/video-active state is not inferred from a field or port alone.
- [ ] TRS capture is based on a real prim; no animation is preloaded.
- [ ] Missing source and bridge produce useful errors and disabled commands.
- [ ] Forms remain unchanged during a supervision refresh.
- [ ] Confirm and cancel dialogs in the actual Codex host.
- [ ] Do not publish the RC as stable or open source before technical gates and licensing are complete.
