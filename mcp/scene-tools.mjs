// Explicit, bounded scene-edit API. No script execution or raw USD ingestion.
const object = (properties, required = []) => ({ type: "object", properties, required, additionalProperties: false });
const str = (maxLength = 512) => ({ type: "string", minLength: 1, maxLength });
const num = (minimum, maximum) => ({ type: "number", minimum, maximum });
const int = (minimum, maximum) => ({ type: "integer", minimum, maximum });
const bool = { type: "boolean" };
const vec = (min, max) => ({ type: "array", minItems: 3, maxItems: 3, items: num(min, max) });
const primPath = { ...str(), pattern: "^/(?:[A-Za-z_][A-Za-z0-9_]*)(?:/[A-Za-z_][A-Za-z0-9_]*)*$" };
const trs = { translation: vec(-1e6, 1e6), rotation: vec(-36000, 36000), scale: vec(0.0001, 10000) };
const fields = {
  transform: { primPath, ...trs },
  animate_transform: { primPath, keys: { type: "array", minItems: 2, maxItems: 120, items: object({ timeSeconds: num(0, 1e6), ...trs }, ["timeSeconds", ...Object.keys(trs)]) } },
  rigid_body: { primPath, mass: num(1e-6, 1e9), kinematic: bool, collider: bool },
  collider: { primPath, enabled: bool },
  physics_scene: { primPath, gravityDirection: vec(-1, 1), gravityMagnitude: num(0, 1e6) },
  attribute: { primPath, attribute: { type: "string", enum: ["physics:mass", "physics:density", "physics:rigidBodyEnabled", "physics:kinematicEnabled", "physics:collisionEnabled", "physics:velocity", "physics:angularVelocity", "physics:gravityMagnitude", "physics:gravityDirection", "physics:staticFriction", "physics:dynamicFriction", "physics:restitution"] }, value: { oneOf: [num(-1e9, 1e9), bool, vec(-1e6, 1e6)] } },
  playback_range: { startSeconds: num(0, 1e6), endSeconds: num(0, 1e6), framesPerSecond: num(1, 240) }
};
export const operationSchema = { oneOf: Object.entries(fields).map(([op, props]) => object({ op: { const: op }, ...props }, ["op", ...Object.keys(props)])) };
const stage = { stageId: str(80) };
const versioned = { ...stage, expectedRevision: int(0, Number.MAX_SAFE_INTEGER) };
const commands = [
  ["inspect_omniverse_scene", "scene.inspect", "Inspect the currently open managed Kit stage without reloading. Returns stageId/revision, paginated direct children, units and actual physics capability. Call first before any scene edit.", object({ stageId: str(80), parentPath: { ...str(), default: "/" }, offset: int(0, 1e6), limit: int(1, 100) }), true],
  ["inspect_omniverse_prim", "scene.prim", "Inspect a selected scene prim's attributes, values, schemas and local transform. Values are bounded and evaluated at current timeline time.", object({ ...stage, primPath }, ["stageId", "primPath"]), true],
  ["preview_omniverse_scene_patch", "scene.preview", "Validate a proposed scene correction on an isolated USD stage. Requires paused playback; physical edits require stopped playback. Returns an expiring previewId, warnings and operations; does not alter the live stage. TRS replaces the local transform stack; angles are XYZ degrees, distances are stage units, mass is stage mass units (normally kg).", object({ ...versioned, label: str(120), operations: { type: "array", minItems: 1, maxItems: 32, items: operationSchema } }, ["stageId", "expectedRevision", "operations"]), true],
  ["apply_omniverse_scene_patch", "scene.apply", "Apply an exact validated preview to an undoable session override layer. Requires matching stage/revision and unexpired preview. Never saves source USD. Pause animation; stop before physical changes.", object({ ...versioned, previewId: str(80) }, ["stageId", "expectedRevision", "previewId"]), false],
  ["undo_omniverse_scene_patch", "scene.undo", "Undo the last OmniStream scene correction only, preserving other scene layers. Stop playback first. Does not rewind a physics solver state.", object(versioned, ["stageId", "expectedRevision"]), false],
  ["discard_omniverse_scene_edits", "scene.discard", "Explicitly discard all OmniStream scene corrections and undo history. Stop playback first; this never deletes source files. Export valuable edits first.", object({ ...versioned, confirm: { const: true } }, ["stageId", "expectedRevision", "confirm"]), false, true],
  ["export_omniverse_scene_patch", "scene.export", "After user approval, export managed corrections to a NEW .usda override layer inside the authorized workspace. Requires confirm:true. No overwrite, no standalone/flattened export and no redistribution of referenced assets.", object({ ...versioned, relativePath: str(), confirm: { const: true } }, ["stageId", "expectedRevision", "relativePath", "confirm"]), false],
  ["configure_omniverse_scene_watch", "scene.watch", "Watch up to 16 existing USD attributes at 4 Hz and optionally pause on non-finite values. Small scalar/vector values only; Fabric-only solver state is not claimed as USD telemetry.", object({ ...stage, properties: { type: "array", maxItems: 16, items: object({ primPath, attribute: str(120) }, ["primPath", "attribute"]) }, pauseOnNonFinite: bool }, ["stageId", "properties"]), false],
  ["diagnose_omniverse_scene", "scene.diagnose", "Read-only bounded structural diagnosis: physics capability, rigid bodies, collision schemas, dynamic/keyframe conflicts and invalid masses. Not a solver-convergence or GPU benchmark.", object({ ...stage, maxPrims: int(1, 5000) }, ["stageId"]), true],
  ["run_omniverse_scene", "scene.run", "Play the CURRENT stage without opening/reloading USD. Physics mode requires detected omni.physx and configured bodies/scene. The Kit-local watchdog pauses at the wall-time limit even with the panel closed. Both modes use the same global Kit timeline: animation does NOT disable existing physics. Loops are disabled. This does not guarantee deterministic stepping.", object({ ...stage, mode: { type: "string", enum: ["animation", "physics"] }, wallTimeLimitSeconds: num(1, 3600), resetToStart: bool }, ["stageId", "mode"]), false],
];
export const sceneRoutes = new Map(commands.map(([name, method, description, inputSchema, readOnlyHint, destructiveHint = false]) => [name, { name, method, description, inputSchema, readOnlyHint, destructiveHint }]));
export const sceneTools = [...sceneRoutes.values()].map(({ method, readOnlyHint, destructiveHint, ...descriptor }) => ({ ...descriptor, title: descriptor.name.replaceAll("_", " "), _meta: { "openai/widgetAccessible": true, ui: { visibility: ["model", "app"] } }, annotations: { readOnlyHint, destructiveHint, openWorldHint: true } }));
export const liveTool = { _meta: { "openai/widgetAccessible": true, ui: { visibility: ["model", "app"] } }, title: "Read live Omniverse telemetry", name: "read_omniverse_live_telemetry", description: "Read cached Kit-pushed telemetry and cursor-based events/logs without blocking on a Kit RPC. Reports ageMs/stale, dropped events and connection state. Kit sampling is 4 Hz; UI polling is normally 1 Hz, NOT hard real-time. Codex must call this tool again to observe later changes.", inputSchema: object({ afterSequence: int(0, Number.MAX_SAFE_INTEGER), limit: int(1, 100) }), annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false } };

export function validateSchema(value, s, label = "arguments") {
  if (s.oneOf) {
    let successes = 0;
    for (const option of s.oneOf) { try { validateSchema(value, option, label); successes++; } catch {} }
    if (successes !== 1) throw new TypeError(`${label} must match exactly one allowed shape`);
    return value;
  }
  if (Object.hasOwn(s, "const") && value !== s.const) throw new TypeError(`${label} has an invalid constant`);
  if (s.enum && !s.enum.includes(value)) throw new TypeError(`${label} is not an allowed value`);
  if (s.type === "object") {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new TypeError(`${label} must be an object`);
    for (const k of s.required || []) if (!Object.hasOwn(value, k)) throw new TypeError(`${label}.${k} is required`);
    for (const [k, v] of Object.entries(value)) {
      if (!Object.hasOwn(s.properties, k)) throw new TypeError(`${label}.${k} is not allowed`);
      validateSchema(v, s.properties[k], `${label}.${k}`);
    }
  } else if (s.type === "array") {
    if (!Array.isArray(value) || value.length < (s.minItems || 0) || value.length > (s.maxItems ?? Infinity)) throw new TypeError(`${label} has an invalid array length`);
    value.forEach((v, i) => validateSchema(v, s.items, `${label}[${i}]`));
  } else if (s.type === "string") {
    if (typeof value !== "string" || value.length < (s.minLength || 0) || value.length > (s.maxLength ?? Infinity) || (s.pattern && !new RegExp(s.pattern).test(value))) throw new TypeError(`${label} has an invalid string`);
  } else if (s.type === "number" || s.type === "integer") {
    if (typeof value !== "number" || !Number.isFinite(value) || value < s.minimum || value > s.maximum || (s.type === "integer" && !Number.isInteger(value))) throw new TypeError(`${label} is not a bounded ${s.type}`);
  } else if (s.type === "boolean" && typeof value !== "boolean") throw new TypeError(`${label} must be boolean`);
  return value;
}
