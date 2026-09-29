# Configuration

This configuration prepares and launches a managed Kit runtime. A correction to the scene already open does not require reloading or changing these paths; see [Open scene](LIVE-SCENE.md).

## Canonical layout

OmniStream uses one local, non-secret configuration file:

```text
%LOCALAPPDATA%\OmniStream\config\omnistream.json
```

`OMNISTREAM_HOME` can relocate the entire OmniStream state root. The installer sets it only after a custom/default installation is complete.

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
|---|---|---|
| `OMNISTREAM_HOME` | Relocates config/log/state/cache/external roots. | platform default |
| `OMNISTREAM_KIT_ROOT` | Overrides the external Kit App Template root. | `kitRoot` |
| `OMNISTREAM_WORKSPACE_ROOT` | Default bounded workspace shown to the panel. | `workspaceRoot` |
| `OMNISTREAM_ASSET_ROOTS` | Additional local asset roots, separated by the OS path delimiter. | `assetRoots` |
| `OMNISTREAM_STREAM_KIT_RELATIVE_PATH` | Streaming `.kit` file below the built release root. | `streamKitRelativePath` |
| `OMNISTREAM_SIGNALING_PORT` | WebRTC signaling port. | `signalingPort` / `49100` |
| `OMNISTREAM_MEDIA_PORT` | WebRTC media stream port. | `mediaPort` / `47998` |

`runtimeChannel` records how the external Kit project was selected (`Production`, `Feature`, or `Existing`). It is diagnostic metadata; by itself it does not download or license NVIDIA software.

When ports are overridden, the MCP launcher passes the same values to Kit's modern `omni.kit.livestream.app` primary-stream settings, and the panel reads those same runtime values. The three layers therefore stay synchronized.

## Workspace boundary

`workspaceRoot` must be an existing local directory. Stage discovery/loading accepts only existing `.usd`, `.usda`, `.usdc`, or `.usdz` files below that root after path resolution. Symbolic links, junctions, and reparse-point escapes are rejected or skipped.

A root USD file may still reference external files through USD resolution. This boundary prevents an MCP tool from selecting a root stage outside the workspace; it is not a complete asset supply-chain sandbox.

## Asset roots

`assetRoots` are explicit local inventory roots. Discovery does not contact Nucleus or a remote catalogue. For migration only, OmniStream can read an old sibling `content` folder beside the selected Kit root if one already exists, but it is not the canonical storage location and is never created automatically.
