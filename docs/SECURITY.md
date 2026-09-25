# Security

> RC3 : pour le travail dans la scène déjà ouverte, les nouveaux outils physiques/animation, la télémétrie et leurs limites, consulter [Scène ouverte et debug](LIVE-SCENE.md). Le cycle ci-dessous décrit le runtime et les outils historiques.

## Local boundaries implemented by the plugin

- The control bridge listener binds to IPv4 loopback and authenticates each session with a random token.
- The panel targets the local WebRTC signal/media endpoints; it does not contact a remote Nucleus or cloud catalog.
- Session credentials are passed to the panel through private widget metadata and redacted from ordinary tool results and error messages.
- A session is associated with a verified Kit process identity. The stop path refuses to terminate an unverified or mismatched process.
- Requested USD root stages must remain below the session workspace root; reparse points and escape paths are rejected or skipped.
- Camera persistence is explicit and isolated from temporary camera navigation.

## Limits that remain outside the plugin

- A loopback target does not configure Windows Firewall. Enforce your own LAN policy if strict network isolation matters.
- The root-stage check does not validate every file resolved by USD. Referenced assets can still originate outside the selected root.
- Any actor with local access to the active Codex/Desktop session may be able to interact with the panel.
- The external Kit, bridge, GPU driver, NVIDIA SDK, and their update channels have their own security and licence responsibilities.
- No claim is made here about remote streaming, cloud tenancy, or Nucleus hardening.

## Secrets and logs

Never commit or publish:

- NVIDIA, npm, GitHub, cloud, or API tokens;
- WebRTC bearer values or bridge control tokens;
- local workspace paths, screenshots, browser traces, Kit logs, PID files, or session recordings; or
- generated `mcp/web-dist/` output.

The public gate in `npm run audit:public` scans the staged Git index when one is available; in an extracted release/source tree it audits the source tree directly and rejects generated/dependency directories. It is not a substitute for protecting local runtime logs or workspaces.

## Reporting a vulnerability

Do not open a public issue containing a credential, local path, or exploit reproduction that would expose another user. Contact the repository owner through an agreed private channel and provide a minimal redacted report.
