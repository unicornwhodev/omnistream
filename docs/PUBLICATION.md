# Public and release publication policy

## Project-source release rule

An OmniStream release archive may contain the plugin source, UI source, tests, installer, documentation, and **OmniStream-owned bridge source**. It must not contain third-party NVIDIA runtime material or machine-local build state.

Forbidden in a release archive or public commit:

- Any Kit App Template checkout copied from NVIDIA, `_build/`, Kit executable, extension cache, or Packman cache;
- `web/node_modules/`, including `@nvidia/ov-web-rtc`;
- `mcp/web-dist/` or `web/dist/` generated bundles containing third-party SDK code;
- Browser traces, local runtime logs/PIDs/config, user workspaces, credentials, or machine-specific paths.

The bundled installer retrieves required third-party components directly on the target machine and builds the local runtime/panel there. `web/package-lock.json` is intentionally shipped so the JavaScript dependency graph is reproducible while third-party package bytes remain absent.

## Release gate

From a developer checkout with target dependencies installed, test and then build the clean release stage:

```powershell
npm run check
npm test
.\installer\Build-Release.ps1
```

The release builder uses an allow/exclude boundary, runs the publication audit against the clean staged tree, scans for forbidden dependency/build directories and native NVIDIA/runtime binaries, then writes a per-file SHA-256 `release-manifest.json` before creating the ZIP.

## Third-party boundary

OmniStream does not mirror or grant rights to NVIDIA software. The operator retrieves NVIDIA components directly from NVIDIA under the terms applicable to that software/account. The project-owned `runtime/bridge/omnistream.codex.bridge` extension is distinct from those NVIDIA components and is intentionally included because it implements OmniStream's own authenticated MCP control contract.

## RC3: audit the actual contents

By default, the audit inspects the filesystem, not just a potentially outdated Git index. The `--index` mode is explicit. It rejects dependencies/caches/binaries/archives, symbolic links, binary null bytes hidden in text files, and oversized source files without review. Secret patterns are not a comprehensive security audit.

Windows packaging uses `System.IO.Compression.ZipFile` directly and verifies that `.codex-plugin/plugin.json`, `.mcp.json`, and the manifest are present in the ZIP. Use `npm run verify:release -- --strict` on a clean extraction; it rejects unlisted extra files. Without `--strict`, it can check installed sources even when generated dependencies are present.

Test data remains in test directories. Normal installation does not copy it into the workspace. A source archive can contain tests without the application providing a fake demo mode.

Run `npm run audit:public` separately on a clean release extraction. A developer checkout with installed dependencies is intentionally rejected by the filesystem audit. No GitHub Actions workflow is currently versioned in this repository; if CI is configured, it should use `Build-Release.ps1` to audit a clean stage without weakening that boundary.
