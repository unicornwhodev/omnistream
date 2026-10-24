import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { panelResourceUri } from "../mcp/panel-resource.mjs";

test("panel identity changes for CSS and JavaScript fixes and is stable for identical content", t => {
  const root = mkdtempSync(path.join(os.tmpdir(), "omnistream-panel-identity-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  assert.match(panelResourceUri(root), /panel-unbuilt\.html$/);
  mkdirSync(path.join(root, "assets"));
  writeFileSync(path.join(root, "index.html"), "<div id=root></div>");
  writeFileSync(path.join(root, "assets/omniverse-panel.js"), "console.log('fixture');");
  writeFileSync(path.join(root, "assets/omniverse-panel.css"), ".viewport-overlay{z-index:2}");
  const first = panelResourceUri(root);
  assert.match(first, /^ui:\/\/omnistream-for-codex\/panel-[a-f0-9]{20}\.html$/);
  assert.equal(panelResourceUri(root), first);
  writeFileSync(path.join(root, "assets/omniverse-panel.css"), ".viewport-overlay{z-index:3}");
  const cssChanged = panelResourceUri(root);
  assert.notEqual(cssChanged, first);
  writeFileSync(path.join(root, "assets/omniverse-panel.js"), "console.log('updated fixture');");
  assert.notEqual(panelResourceUri(root), cssChanged);
});
