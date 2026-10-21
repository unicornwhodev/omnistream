import assert from "node:assert/strict";
import test from "node:test";
import { SessionPreparation, CONFIGURATION_CHANGED, CONTROLLER_INCOMPATIBLE } from "../../test-results/panel-state/session-preparation.js";

// Explicit synthetic transport for state tests. This does not qualify Kit/video.
const config = (overrides = {}) => ({
  name: "State test", workspaceRoot: "test-workspace", stagePath: "test.usda",
  kitRoot: "test-kit", initialTimeSeconds: 0, rateMultiplier: 1,
  loop: false, playEveryFrame: false, autoPlay: false, cameraPath: "",
  ...overrides,
});
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
function transport({ ready = true, legacy = false } = {}) {
  const calls = [];
  let stored;
  let counter = 0;
  return { calls, call: async (name, args) => {
    calls.push({ name, args });
    if (name === "configure_omniverse_simulation") {
      stored = config({ ...args, ...(legacy ? {} : { configurationId: `test-id-${++counter}` }) });
      return { configuration: stored };
    }
    return { configuration: stored, ready, checks: [], failed: ready ? [] : ["runtime"] };
  } };
}

test("empty preparation blocks launch and never labels it ready", async () => {
  const state = new SessionPreparation();
  let starts = 0;
  assert.equal(state.label(), "À configurer");
  assert.equal(await state.launch(true, async () => ++starts), null);
  assert.equal(starts, 0);
});
test("validated normalized snapshot and matching preflight enable exact guarded launch", async () => {
  const state = new SessionPreparation();
  const host = transport();
  const result = await state.validate(config({ name: "One snapshot", stagePath: "normalized.usda" }), host.call);
  assert.equal(result.preflight.ready, true);
  assert.equal(state.label(), "Prêt à lancer");
  assert.equal(state.canLaunch(false), false);
  assert.equal(state.label(false, false), "Préflight bloqué");
  await state.launch(true, async (snapshot, args) => {
    assert.deepEqual(snapshot, result.configuration);
    assert.deepEqual(args, { expectedConfigurationId: result.configuration.configurationId });
    assert.equal(Object.isFrozen(snapshot), true);
  });
});
const edits = {
  name: "New name", workspaceRoot: "new-workspace", stagePath: "new.usda",
  kitRoot: "new-kit", initialTimeSeconds: 2, rateMultiplier: 2,
  loop: true, playEveryFrame: true, autoPlay: true, cameraPath: "/World/Camera",
};
for (const [field, value] of Object.entries(edits)) {
  test(`editing ${field} invalidates before another launch; revalidation accepts only new snapshot`, async () => {
    const state = new SessionPreparation();
    const host = transport();
    await state.validate(config(), host.call);
    const previousId = state.state.validated.configurationId;
    state.edit();
    assert.equal(state.state.preflight, null);
    assert.equal(state.current, false);
    assert.equal(state.label(), "Modifications à valider");
    let starts = 0;
    await state.launch(true, async () => ++starts);
    assert.equal(starts, 0);
    await state.validate(config({ [field]: value }), host.call);
    assert.notEqual(state.state.validated.configurationId, previousId);
    await state.launch(true, async (snapshot) => {
      assert.equal(snapshot[field], value);
      starts++;
    });
    assert.equal(starts, 1);
  });
}
test("failed validation clears prior success and makes no preflight/launch call", async () => {
  const state = new SessionPreparation();
  const host = transport();
  await state.validate(config(), host.call);
  await assert.rejects(state.validate(config(), async () => { throw Error("Invalid USD"); }), /Invalid USD/);
  assert.equal(state.state.preflight, null);
  assert.equal(state.canLaunch(), false);
  assert.equal(state.state.operation, null);
});
test("blocked preflight never starts a runtime", async () => {
  const state = new SessionPreparation();
  await state.validate(config(), transport({ ready: false }).call);
  assert.equal(state.label(), "Préflight bloqué");
  let starts = 0;
  await state.launch(true, async () => ++starts);
  assert.equal(starts, 0);
});
test("late configuration response cannot normalize or validate a more recent draft", async () => {
  const state = new SessionPreparation();
  const reply = deferred();
  const calls = [];
  let normalized = 0;
  const pending = state.validate(config(), async (name) => { calls.push(name); return reply.promise; }, () => normalized++);
  state.edit();
  reply.resolve({ configuration: config({ configurationId: "obsolete" }) });
  assert.equal(await pending, null);
  assert.equal(normalized, 0);
  assert.equal(state.state.validated, null);
  assert.deepEqual(calls, ["configure_omniverse_simulation"]);
});
test("late preflight response cannot restore ready state after editing", async () => {
  const state = new SessionPreparation();
  const reply = deferred();
  const configuration = config({ configurationId: "old" });
  const pending = state.validate(config(), async (name) =>
    name === "configure_omniverse_simulation" ? { configuration } : reply.promise,
    () => state.edit());
  reply.resolve({ configuration, ready: true, checks: [], failed: [] });
  assert.equal(await pending, null);
  assert.equal(state.state.preflight, null);
  assert.equal(state.canLaunch(), false);
});
test("old poll is ignored; current observation of a replacement invalidates preparation", async () => {
  const state = new SessionPreparation();
  const oldVersion = state.state.version;
  await state.validate(config(), transport().call);
  const snapshot = state.state.validated;
  state.observe(config({ configurationId: "other" }), oldVersion);
  assert.equal(state.canLaunch(), true);
  state.observe(config({ configurationId: "other" }), state.state.version);
  assert.equal(state.canLaunch(), false);
  assert.equal(state.state.validated, snapshot, "Observation must not overwrite the draft reference");
  assert.equal(state.state.issue, CONFIGURATION_CHANGED);
});
test("preflight for another controller configuration is rejected", async () => {
  const state = new SessionPreparation();
  await assert.rejects(state.validate(config(), async (name) => ({
    configuration: config({ configurationId: name === "configure_omniverse_simulation" ? "a" : "b" }),
    ready: true, checks: [], failed: [],
  })), { message: CONFIGURATION_CHANGED });
  assert.equal(state.canLaunch(), false);
});
test("double click and a concurrent validation admit exactly one start", async () => {
  const state = new SessionPreparation();
  await state.validate(config(), transport().call);
  const result = deferred();
  let starts = 0;
  const start = async () => { starts++; return result.promise; };
  const first = state.launch(true, start);
  const second = state.launch(true, start);
  assert.equal(await second, null);
  assert.equal(await state.validate(config(), transport().call), null);
  assert.equal(starts, 1);
  result.resolve("started");
  assert.equal(await first, "started");
  assert.equal(state.state.operation, null);
});
test("uncertain/rejected launch requires observation and revalidation, never an automatic retry", async () => {
  const state = new SessionPreparation();
  await state.validate(config(), transport().call);
  let starts = 0;
  await assert.rejects(state.launch(true, async () => { starts++; throw Error("simulation_configuration_changed"); }));
  await state.launch(true, async () => ++starts);
  assert.equal(starts, 1);
  assert.equal(state.canLaunch(), false);
});
test("legacy controller is explicit incompatibility; no launch and no false ready label", async () => {
  const state = new SessionPreparation();
  const host = transport({ legacy: true });
  await assert.rejects(state.validate(config(), host.call), { message: CONTROLLER_INCOMPATIBLE });
  assert.equal(state.state.issue, CONTROLLER_INCOMPATIBLE);
  assert.equal(state.canLaunch(), false);
  assert.equal(host.calls.length, 1);
});
test("startup hydration cannot overwrite an edited draft or an in-flight validation", async () => {
  const state = new SessionPreparation();
  assert.equal(state.canHydrate(), true);
  state.edit();
  assert.equal(state.canHydrate(), false);
  const fresh = new SessionPreparation();
  const response = deferred();
  const pending = fresh.validate(config(), async () => response.promise);
  assert.equal(fresh.canHydrate(), false);
  response.reject(Error("test failed request"));
  await assert.rejects(pending);
});

test("reopening seals the complete controller snapshot against late runtime defaults without granting launch readiness", () => {
  const state = new SessionPreparation();
  const draft = config({ workspaceRoot: "D:/qualification/fireviewer" });
  state.finishHydration();
  // A watchdog created at mount can finish after controller hydration. Its
  // stale empty-field closure must no longer admit the operator default root.
  if (state.canHydrate()) draft.workspaceRoot = "D:/operator/default";
  assert.equal(draft.workspaceRoot, "D:/qualification/fireviewer");
  assert.equal(state.state.validated, null);
  assert.equal(state.state.preflight, null);
  assert.equal(state.label(), "À configurer");
  assert.equal(state.canLaunch(), false);
});
