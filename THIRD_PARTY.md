# Third-party and distribution notice

The OmniStream release includes the **project-owned** `omnistream.codex.bridge` source code, but it does not include NVIDIA Omniverse Kit/Kit SDK binaries, NVIDIA extension caches, the Kit App Template checkout, `@nvidia/ov-web-rtc`, `web/node_modules`, or a generated WebRTC panel bundle containing that SDK.

The Windows installer obtains those external dependencies directly on the user's machine from NVIDIA's official GitHub repository, registry, and Kit tooling. Nothing in this repository grants a licence to NVIDIA software or authorizes redistribution beyond the terms NVIDIA grants to the user/operator.

`mcp/web-dist/` is generated locally after the WebRTC SDK is retrieved and is ignored by the source/release builder. The release also contains no copied NVIDIA example React components; the project UI imports the external `@nvidia/ov-web-rtc` package only after the operator obtains it locally from NVIDIA.

No open-source licence has been selected for OmniStream itself. Public visibility alone does not grant reuse, modification, or redistribution rights.
