# OmniStream 1.0.0-rc3 — Verification report

## Verdict

The RC2 codebase received a redesign and hardening pass. The user workflow no longer installs a scene automatically, preloads animation, invents connection state, or substitutes a different renderer. **This conclusion covers the code and the workflow observed without Kit; it does not certify a native simulation or RTX video stream, neither of which was run here.**

## Checks performed

| Check | Result and scope |
|---|---|
| `npm run check` | PASS: Node module syntax plus application/Vite TypeScript checks. Check dependencies came from the supplied archive, not a clean installation. |
| `npm test` | PASS: historical MCP suite; 12 scene/event tests; 12 public-integrity tests; panel source contracts; 7 distribution tests. |
| `python -m unittest discover -s tests -v` | 32 tests found: **17 PASS, 15 SKIPPED**, no failures. The 15 skipped tests require the real `pxr`/OpenUSD package, which was unavailable here. |
| Bridge Python syntax | PASS: five modules compiled syntactically; this does not claim they import Kit. |
| Front-end formatting | PASS: Prettier checks for TSX, CSS, and the MJS utility source. |
| Panel source contracts | PASS: explicit `--source-only` mode; this does not replace the bundle contract. |
| `npm run test:web` | **BLOCKED / ENVIRONMENT FAILURE**: Vite cannot load `@rollup/rollup-linux-x64-gnu`, which is absent from the supplied Windows dependencies. The build and bundle contract are therefore unverified. |
| Clean dependency installation | Not verified: the network attempt had no usable name resolution/outbound access. This report does not claim that the lockfile dependencies or SDK were installed from scratch. |
| Distribution audit / manifest | Run separately on a clean tree and then on a re-extracted archive; see the reproduction commands below. |

Protocol unit tests use test doubles for some Kit responses and isolated test data. They are identified as such; they are not evidence of a physical simulation. This RC's browser test does not use fabricated Kit/WebRTC responses.

## Browser method and evidence

The Browser plugin was unavailable; Playwright used system Chromium in headless mode. The browser policy in this environment rejects local HTTP navigation. The document was therefore loaded with `set_content`, using the real TSX source transpiled for this check and the actual React/NVIDIA SDK libraries available locally. This CommonJS test loader is outside the release; it is not a distributed Vite build.

First workflow: no host. All six surfaces render, runtime actions are disabled, the viewport explains that no connection exists, and measurements remain unknown. No demo asset, object, or animation is generated.

Second workflow: the real `mcp/server.mjs` runs in a Node process. A test-only IPC adapter connects panel calls to its native JSONL protocol. No runtime status, scene content, tool response, or WebRTC frame is fabricated. **This is not the actual Codex host.**

Observed checks: an actually empty workspace is returned as empty; entered settings remain intact through several polls; the controller rejects a missing file path; that path never appears as a loaded stage; all six views navigate; and the panel recognizes the actual MCP process shutdown as an unavailable controller. No console errors or warnings occurred in this workflow. Transport errors after the process closes are expected and displayed by the panel.

Checked viewport sizes: **1440×1000, 820×900, 420×900, and 360×800**. No horizontal overflow. At 420 px, geometry after navigation showed the sticky bar ending at 63 px and the inspector header starting at about 72 px, so they do not overlap. Full-page captures taken after scrolling can reposition a sticky bar; a viewport capture is the evidence of its actual on-screen position.

## Visual review

The comparison was between the supplied RC2 front end and the RC3 rendering, not the rejected earlier API dashboard image. The review covered:

1. Navigation: a dedicated rail instead of a grid of small tabs in the inspector.
2. Composition: a dominant viewport, playback controls directly below it, and controls in a separate inspector.
3. Typography: distinct headings, labels, buttons, and statuses; desktop rail labels were enlarged after review.
4. Colors: graphite and neutral greys with green action/status accents; no decorative khaki panels.
5. States: missing host/runtime is visible; no scene or camera is assumed; unknown values are explicit.
6. Responsive layout: horizontal navigation at small widths, stacked fields, and an accessible inspector without overflow.
7. Labels: “Target cadence” makes no promise about physical speed; “Video active” is not inferred from signaling.

Text and navigation changes are intentional and tied to the actual product. No generated mockup, decorative statistic, or API card serves as a reference. Screens with active objects or video still need checking in Kit.

## Functional fixes verified in source

Explicit handling of errors and empty MCP results; host arrival/loss detection; protection of drafts during supervision; a shared lock for scene actions; preview timeout/expiration; native panel confirmations; a visible React error boundary instead of a blank screen; and explicit confirmation for camera saving and shutdown when edits could be lost.

The two unused web scaffold assets (generic purple favicon and social-network icon sprite) were also removed. They did not participate in any product function.

The bridge now actually writes the disabled state of an existing collider. A truncated inspection no longer incorrectly asserts that no physics scene exists, and it blocks an automatic bounded run. Pose capture returns only a recognized simple TRS stack; complex stacks are rejected. Corresponding OpenUSD tests exist but are among the **15 native tests skipped**, not local passes.

## Distribution

The audit now checks the actual tree and rejects binaries (rather than ignoring them), dependencies, archives, symbolic links, hidden null bytes in text, and oversized source files without review. The Windows script archives through .NET to preserve hidden metadata, then checks that metadata is present. The manifest verifies sizes and SHA-256 hashes; `--strict` rejects additional files. **Hashes are not a digital signature.**

On a clean extraction:

```powershell
npm run audit:public
npm run verify:release -- --strict
```

After obtaining dependencies locally on the correct platform:

```powershell
npm run check
npm test
npm run test:python
npm run test:web
installer\test.cmd
npm run test:physics
```

## Still to qualify

PowerShell install/repair/resume/uninstall; a clean dependency installation and production Vite build; real OpenUSD import and editing; Kit/PhysX; WebRTC decoding and interaction in actual Codex; large datasets and third-party extensions. No GitHub Actions workflow is currently versioned in the repository, so this report makes no CI-success claim. Passing the tested security checks is not an independent security audit.

These limits justify **RC3**, not an artificial promotion to stable. The product remains `UNLICENSED`; no catalogue publication or rights change has been made.
