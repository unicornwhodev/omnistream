import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

/** Hosts cache a UI resource by URI. A changed production bundle must have a
 * new identity, including CSS-only fixes. The source-only checkout stays usable
 * for setup/status tools before its first frontend build. */
export function panelResourceUri(webDist) {
  const files = ["index.html", "assets/omniverse-panel.js", "assets/omniverse-panel.css"];
  if (files.some(file => !existsSync(path.join(webDist, file))))
    return "ui://omnistream-for-codex/panel-unbuilt.html";
  const hash = createHash("sha256");
  for (const file of files) {
    const bytes = readFileSync(path.join(webDist, file));
    hash.update(`${file}:${bytes.length}:`);
    hash.update(bytes);
  }
  return `ui://omnistream-for-codex/panel-${hash.digest("hex").slice(0, 20)}.html`;
}
