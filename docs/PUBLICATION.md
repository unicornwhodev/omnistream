# Public/release publication policy

## Project-source release rule

An OmniStream release archive may contain the plugin source, UI source, tests, installer, documentation, and **OmniStream-owned bridge source**. It must not contain third-party NVIDIA runtime material or machine-local build state.

Forbidden in a release archive or public commit:

- any Kit App Template checkout copied from NVIDIA, `_build/`, Kit executable, extension cache, or Packman cache;
- `web/node_modules/`, including `@nvidia/ov-web-rtc`;
- `mcp/web-dist/` or `web/dist/` generated bundles containing third-party SDK code;
- browser traces, local runtime logs/PIDs/config, user workspaces, credentials, or machine-specific paths.

The bundled installer retrieves required third-party components directly on the target machine and builds the local runtime/panel there. `web/package-lock.json` is intentionally shipped so the JavaScript dependency graph is reproducible while third-party package bytes remain absent.

## Release gate

From a developer checkout with target dependencies installed, test then build the clean release stage:

```powershell
npm run check
npm test
.\installer\Build-Release.ps1
```

The release builder uses an allow/exclude boundary, runs the publication audit against the clean staged tree, scans it for forbidden dependency/build directories and native NVIDIA/runtime binaries, then writes a per-file SHA-256 `release-manifest.json` before creating the ZIP.

## Third-party boundary

OmniStream does not mirror or grant rights to NVIDIA software. The operator retrieves NVIDIA components directly from NVIDIA under the terms applicable to that software/account. The project-owned `runtime/bridge/omnistream.codex.bridge` extension is distinct from those NVIDIA components and is intentionally included because it implements OmniStream's own authenticated MCP control contract.

## RC3 — audit du contenu réel

L’audit inspecte le système de fichiers par défaut, pas seulement un index Git potentiellement ancien. Le mode `--index` est explicite. Il refuse les dépendances/cache/binaires/archives, liens symboliques, octets binaires dissimulés dans un fichier texte et fichiers source surdimensionnés sans revue. Les motifs de secrets ne constituent pas un audit de sécurité exhaustif.

Le packaging Windows utilise directement `System.IO.Compression.ZipFile` et vérifie la présence de `.codex-plugin/plugin.json`, `.mcp.json` et du manifeste dans le ZIP. La vérification `npm run verify:release -- --strict` s’utilise sur une extraction propre : elle refuse les fichiers supplémentaires non couverts. Sans `--strict`, elle peut contrôler les sources installées même si des dépendances générées sont présentes.

Les données de test restent dans les répertoires de tests. Aucune n’est copiée par l’installation normale dans le workspace. Une archive source peut contenir des tests sans que l’application fournisse un faux mode de démonstration.

Run `npm run audit:public` separately on a clean release extraction. A developer checkout containing installed dependencies is intentionally rejected by the filesystem audit. No GitHub Actions workflow is currently versioned in this repository; when CI is configured, it should use `Build-Release.ps1` to audit a clean stage without weakening that boundary.
