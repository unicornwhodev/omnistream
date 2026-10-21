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

Existing remote Kit streams use a separate `remoteSessions` allowlist. See
[Remote sessions](REMOTE-SESSIONS.md) for private Tailscale and WSS/ICE profiles,
credential boundaries, and the required real-video qualification.

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

## Local MCP signaling for an embedded host

To negotiate the native Kit WebRTC stream through the existing MCP Apps bridge:

```json
"panelSignalingTransport": "mcp"
```

This opt-in setting is read when the MCP controller starts. Reload the controller
and reopen its panel after changing it. The panel and controller must come from
the same candidate. The default, `"websocket"`, retains direct/WSS signaling.

Only SDP/ICE signaling travels through three app-only MCP tools. The controller
connects to its own authenticated Kit signaling endpoint on 127.0.0.1; the caller
cannot supply another host, port or bearer. Channel responses are private app
metadata, excluded from normal tool content. Exchanges have message/queue bounds,
sequence acknowledgements, a 30-second idle expiry and a two-channel limit.
Stopping or replacing the owned runtime invalidates its channels.

The NVIDIA SDK remains unchanged. Actual RTX video and native viewport input
still use WebRTC; no image polling or substitute renderer is introduced. This
mode needs no public relay, tunnel, certificate or additional trust. An existing
`signalingTls` configuration can remain in the file but its helper is inactive
while MCP signaling is selected. This setting does not certify a given host's
video or native input: observe those in the actual Codex panel.

## Local WSS signaling for a host that requires TLS

Some Codex distributions filter HTTP/WS origins from widget CSP. On Windows,
an explicitly configured TLS relay can wrap Kit's unchanged loopback signaling:

```json
"signalingTls": {
  "port": 49101,
  "certificateThumbprint": "<40-HEX-CHARACTER-THUMBPRINT>"
}
```

The certificate must already exist with its private key in CurrentUser/My,
identify localhost, have serverAuth usage, be valid and non-CA, and pass the
Windows trust check. Creating or trusting a certificate is a separate,
explicitly authorized setup step. OmniStream never installs trust or skips
certificate validation automatically.

The relay listens only on 127.0.0.1. The panel uses WSS localhost and the
unmodified NVIDIA SDK; Kit signaling/media ports and the runtime channel stay
the same. Preflight checks certificate trust and relay-port availability.
The controller owns the helper and closes its input pipe after safe Kit stop.
Removing `signalingTls` restores the original direct signaling contract;
that direct contract remains blocked in hosts that require HTTPS/WSS.

## Workspace boundary

`workspaceRoot` must be an existing local directory. Stage discovery/loading accepts only existing `.usd`, `.usda`, `.usdc`, or `.usdz` files below that root after path resolution. Symbolic links, junctions, and reparse-point escapes are rejected or skipped.

A root USD file may still reference external files through USD resolution. This boundary prevents an MCP tool from selecting a root stage outside the workspace; it is not a complete asset supply-chain sandbox.

## Asset roots

`assetRoots` are explicit local inventory roots. Discovery does not contact Nucleus or a remote catalogue. For migration only, OmniStream can read an old sibling `content` folder beside the selected Kit root if one already exists, but it is not the canonical storage location and is never created automatically.
