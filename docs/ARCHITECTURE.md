# Architecture

> RC3 : pour le travail dans la scène déjà ouverte, les nouveaux outils physiques/animation, la télémétrie et leurs limites, consulter [Scène ouverte et debug](LIVE-SCENE.md). Le cycle ci-dessous décrit le runtime et les outils historiques.

```mermaid
flowchart LR
  Codex["Codex Desktop"] -->|"MCP resource + tool calls"| MCP["Node MCP server\nOmniStream for Codex"]
  MCP -->|"private widget metadata\nWebRTC bearer"| Panel["Codex panel\nlocal WebRTC client"]
  Panel <-->|"loopback signaling/media"| Kit["NVIDIA Kit runtime\nexternal, --no-window"]
  MCP -->|"authenticated JSONL\nephemeral loopback port"| Bridge["omnistream.codex.bridge\nOmniStream source"]
  Bridge --> Kit
  MCP -->|"validated root-stage paths"| USD["Configured local USD workspace"]
  Assets["Configured local asset roots"] --> MCP
```

## Ownership boundaries

- **Codex panel** — OmniStream source; displays actual decoded Kit frames and relays native viewport input.
- **MCP server** — OmniStream source; owns only the Kit process it starts, validates stage paths, serializes mutations, redacts credentials, and gates safe stop.
- **`omnistream.codex.bridge`** — OmniStream source; installed into the user's external Kit checkout. It connects outbound to an authenticated ephemeral loopback server and performs stage/timeline/camera commands inside Kit.
- **NVIDIA Kit runtime and WebRTC SDK** — external dependencies retrieved on the user's machine from NVIDIA. They are not present in OmniStream release archives.
- **Workspace/assets** — user-selected local files; their paths live in local config, not the plugin manifest/source.

## Simulation orchestration model

OmniStream separates a **validated simulation configuration** from a **tracked runtime run**. `configure_omniverse_simulation` stores the bounded workspace/stage and session playback policy without touching Kit. `launch_omniverse_simulation` snapshots that configuration and executes runtime start/readiness, stage open, and session configuration as one serialized side-effect operation. Only after every launch step completes is a `runId` published.

`supervise_omniverse_simulation` is the canonical aggregated read model consumed by Codex and the panel. `control_omniverse_simulation` is the canonical bounded write model for playback. Lower-level lifecycle/stage/timeline tools remain available for diagnostics and compatibility, but normal workflows do not need to manually compose them.

This separation prevents UI configuration edits from silently changing a running simulation and prevents another mutation from interleaving during a launch sequence. A timeout with an uncertain effect is recorded on the managed session and closes the normal mutation path until reconciled.

## Stream configuration

The MCP runtime chooses the signaling/media ports once and passes the same values to Kit at launch using `omni.kit.livestream.app` primary stream settings. Runtime status returns those values to the React panel, which uses them to connect. This removes the previous split-brain risk where Kit and the client could silently use different ports.

## Persistence contract

Timeline operations and camera navigation are session operations. OmniStream does not create cameras. Temporary camera movement is authored in the USD session layer and tracked as dirty. Selecting another camera is refused while that temporary pose is unsaved. `save_omniverse_camera` is the single explicit persistence operation: after confirmation, it writes the selected camera pose to a writable source layer and removes OmniStream's temporary session override.

## Network and credential contract

The control bridge uses `127.0.0.1`, an ephemeral port, and a random per-session token supplied through the child process environment. The WebRTC bearer is sent to the panel only through private widget metadata. Secrets are not placed in public tool results, process arguments, normalized config, or user-facing logs.
