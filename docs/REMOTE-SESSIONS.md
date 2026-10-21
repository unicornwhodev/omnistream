# Existing remote Omniverse sessions

The remote viewer attaches to an already running, compatible NVIDIA Kit WebRTC
server. It does not allocate a GPU, start a cloud instance, upload a stage, stop
the external runtime, or expose the local USD control bridge. Disconnecting the
viewer leaves the remote scene and GPU running.

The controller and panel must both include the remote-session tools. Declare up
to 16 operator-owned profiles in `remoteSessions` in the existing local
`omnistream.json`, then reload the controller. Tools accept profile identities;
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

Select **Session distante**, choose the profile, then **Rattacher le flux distant**.
An attachment or successful signaling exchange is not proof of video. Verify a
decoded image with nonzero dimensions, progressing media time and visible
native viewport input in the actual Codex panel. Preserve the local form draft
when switching modes. Local Kit mutations remain blocked while a remote viewer
attachment exists.

Reconnect explicitly after a failed negotiation. A stale attachment cannot
close a replacement. SDK teardown must complete before another connection;
the viewer never requests termination of the external application. After a
Colab reset, recheck its runtime, network identity, scene archive hash, policy
and profile before reconnecting. The notebook execution proxy token is not a
video credential and must never be copied into a stream profile or report.
