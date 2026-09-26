# Configuration

Cette configuration sert à préparer et lancer un runtime Kit géré. Une correction sur la scène déjà ouverte n’exige pas de recharger ni de modifier ces chemins ; voir [Scène ouverte](LIVE-SCENE.md).

## Canonical layout

OmniStream uses one local non-secret configuration file:

```text
%LOCALAPPDATA%\OmniStream\config\omnistream.json
```

`OMNISTREAM_HOME` may relocate the whole OmniStream state root. The installer sets it only when a custom/default installation is completed.

Example:

```json
{
  "schemaVersion": 2,
  "kitRoot": "<LOCALAPPDATA>\\OmniStream\\external\\kit-app-template",
  "workspaceRoot": "<USERPROFILE>\\Documents\\OmniStream\\Workspace",
  "assetRoots": [
    "<USERPROFILE>\\Documents\\OmniStream\\Assets"
  ],
  "streamKitRelativePath": "apps/my_omnistream_streaming.kit",
  "signalingPort": 49100,
  "mediaPort": 47998,
  "runtimeChannel": "Production"
}
```

The bridge settings prefix is intentionally canonical and is **not** a user setting: `--/exts/omnistream_codex_bridge/`.

## Environment overrides

| Variable | Effect | Config fallback |
| --- | --- | --- |
| `OMNISTREAM_HOME` | Relocates config/log/state/cache/external roots. | platform default |
| `OMNISTREAM_KIT_ROOT` | Overrides the external Kit App Template root. | `kitRoot` |
| `OMNISTREAM_WORKSPACE_ROOT` | Default bounded workspace shown to the panel. | `workspaceRoot` |
| `OMNISTREAM_ASSET_ROOTS` | Additional local asset roots, separated by the OS path delimiter. | `assetRoots` |
| `OMNISTREAM_STREAM_KIT_RELATIVE_PATH` | Streaming `.kit` below the built release root. | `streamKitRelativePath` |
| `OMNISTREAM_SIGNALING_PORT` | WebRTC signaling port. | `signalingPort` / `49100` |
| `OMNISTREAM_MEDIA_PORT` | WebRTC media stream port. | `mediaPort` / `47998` |

`runtimeChannel` records how the external Kit project was selected (`Production`, `Feature`, or `Existing`). It is diagnostic metadata; it does not download or license NVIDIA software on its own.

When ports are overridden, the MCP launcher passes the same values to Kit's modern `omni.kit.livestream.app` primary stream settings, and the panel reads those same runtime values. The three layers therefore stay synchronized.

## Workspace boundary

`workspaceRoot` must be an existing local directory. Stage discovery/loading accepts only existing `.usd`, `.usda`, `.usdc`, or `.usdz` files below that root after path resolution. Symbolic links, junctions, and reparse-point escapes are rejected or skipped.

A root USD can still reference external files through USD resolution. This boundary prevents the MCP tool from selecting a root stage outside the workspace; it is not a complete asset supply-chain sandbox.

## Asset roots

`assetRoots` are explicit, local inventory roots. Discovery does not contact Nucleus or a remote catalogue. For migration only, OmniStream can read an old sibling `content` folder beside the selected Kit root if one already exists, but it is not the canonical storage location and is never created automatically.
