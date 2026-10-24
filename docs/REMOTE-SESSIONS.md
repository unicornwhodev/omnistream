# Existing remote Omniverse sessions

The remote viewer attaches to an already running, compatible NVIDIA Kit WebRTC
server. A single studio, navigation and viewport serve local and remote sessions.
Select the session in the **Session** selector. The existing external runtime
keeps ownership of its process and GPU; disconnecting the viewer leaves it running.
OmniStream does not allocate another GPU or upload the stage on attachment.

For the same scene, camera, timeline and configuration tools to work remotely,
install the authenticated control facade described below on that host. A profile
with video alone is explicitly reported as missing its control connection. Video
reception and successful control requests are checked independently.

The controller and panel must both include the remote-session tools. Declare up
to 16 operator-owned profiles in `remoteSessions` in the existing local
`omnistream.json`. The controller rereads and validates these profiles on listing,
attachment and signaling requests. Changing or removing an attached profile
closes its signaling channels and invalidates the attachment; reconnect explicitly
to the updated profile. Invalid configuration fails closed. Other runtime settings
still require a controller reload. Tools accept profile identities;
they cannot select an arbitrary URL or supply credentials.

## Private Tailscale network

This mode supports a Colab or RunPod runtime behind NAT without requiring public
Kit ports or a TURN service. Install and authenticate Tailscale separately on the
PC and remote host. A restricted host can use Tailscale userspace networking;
verify TCP and UDP forwarding on that actual host before calling it qualified.
Keep its incoming traffic blocked until the network policy permits only the
operator PC and the selected Kit signaling/media ports.

Example with documentation-only private addresses:

```json
{
  "remoteSessions": [{
    "id": "private-kit",
    "label": "Existing private Kit",
    "provider": "colab",
    "mediaConnectivity": "tailscale",
    "signalingUrl": "ws://100.78.12.34:49100/sign_in",
    "mediaServer": "100.78.12.34",
    "mediaPort": 47998
  }]
}
```

Signaling and media must name the same IPv4 peer within Tailscale's address
range. Before opening a signaling socket, the controller checks the local
Tailscale CLI for a running network and that exact online peer. The network
provides authenticated WireGuard encryption. WS is allowed only in this explicit
private mode; the browser receives signaling through private app-only MCP
metadata. No application bearer is invented for a Kit server that has no bearer
authentication. A server that also requires a bearer can use `streamTokenEnv`.
External ICE servers are rejected for this mode.

## Public WSS / direct or TURN media

For another existing host, use a credential-free `wss://` signaling endpoint
ending in `/sign_in`. Query strings, notebook URLs, user information and inline
secrets are rejected. Set `streamTokenEnv` to the name of an
`OMNISTREAM_REMOTE_...` environment variable containing the actual server bearer.

`mediaConnectivity: "direct"` requires an actual routable media path. Colab and
RunPod profiles require either `"tailscale"` or `"relay"`; an HTTPS/TCP provider
proxy alone does not establish a WebRTC media route.

For `"relay"`, also set `iceServersEnv` and `serverIceConfigured: true`. The named
environment variable contains an array of standard ICE servers, including a
TCP TURN URL and its username/credential. Configure the compatible server-side
ICE path separately. Client ICE configuration alone does not add TURN support
to an older Kit. ICE credentials remain in private panel metadata.

## Acceptance and recovery

Choose the existing profile in **Session**, then **Connecter**.
An attachment or successful signaling exchange is not proof of video. Verify a
decoded image with nonzero dimensions, progressing media time and visible
native viewport input in the actual Codex panel. Check camera, timeline,
configuration and preflight against the same remote Kit. Requests never silently
fall back to the local controller while a remote session is selected.

The shared stream profile requests 1920 × 1080 at 30 fps, up to 60 Mb/s, with
dynamic resolution reduction disabled. This is a requested policy, not a quality
certificate. The panel displays the received dimensions, frame rate, measured
bitrate and RTT. Missing measurements remain unknown. Source resolution and
browser zoom are separate from received video dimensions. Check all three when
qualifying fine vegetation, flames or smoke. Scientific image outputs must use
verified native captures; a WebRTC screenshot is proof of the live interface.

The pinned NVIDIA SDK 6.6.0 Direct wrapper omits two underlying downstream
parameters. `web/sdk/ov-web-rtc-quality.mjs` forwards `maxBitrateKbps` and
`dynamicStreamingMode` during the build. The adapter fails if its exact source
match changes. Its regression test executes the actual vendor request method.
No SDK internals are accessed through the live browser page.

Reconnect explicitly after a failed negotiation. A stale attachment cannot
close a replacement. SDK teardown must complete before another connection;
the viewer never requests termination of the external application. After a
Colab reset, recheck its runtime, network identity, scene archive hash, policy
and profile before reconnecting. The notebook execution proxy token is not a
video credential and must never be copied into a stream profile or report.

## Authenticated remote commands

`mcp/remote-control-host.mjs` runs beside the external Kit. It binds only to
loopback and exposes a bounded HTTP facade over the original authenticated
loopback control worker. Its private configuration names `tokenFile` and
`bridgeSettingsFile`; launch requires `--control-authorized`. Keep both files
outside source control. The approved private relay must route only the fixed
control path from the approved operator peer.

A Tailscale profile may name `controlTokenEnv` or `controlTokenFile` (one only).
The latter must be an absolute path to a regular private file on the controller
machine. Credentials and credential paths never enter browser metadata or
public errors. The media, signaling and control connection bind to the same
validated peer. No arbitrary Python execution or external process termination
is exposed by the facade.

Configuration validates the existing remote workspace, USD stage and camera
without opening or modifying the stage. Launch applies the validated settings
to that same Kit and opens the stage only if its path changes. Camera, timeline,
scene inspection, bounded edits and telemetry use the normal studio tools.
Process start/stop remains owned by the external host. Remote file logs report
their absence explicitly when that host has no log export capability.

Mutations are serialized and carry request identities. A result whose completion
is uncertain blocks subsequent mutations while allowing reads for diagnosis;
repeating the same identity cannot execute it twice. Test interruptions and
recovery on the actual host before accepting a production connection.

## Compression choice

The common **Connexion** details expose **Compression vidéo** for both local
and remote sessions. H.264 remains the initial compatibility choice. H.265 and
AV1 appear only when the browser advertises them; the Kit host must also support
the selected codec. Disconnect video before changing it. A requested format is
not proof of successful decoding: verify the codec reported with received video
statistics. A failed negotiation does not silently fall back or claim success.
