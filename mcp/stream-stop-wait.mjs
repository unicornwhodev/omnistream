function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function assertInteger(value, label, minimum, maximum) {
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new Error(label + " must be an integer between " + minimum + " and " + maximum + ".");
  }
  return value;
}

/**
 * Wait for a local endpoint to stop responding. The probe is intentionally
 * supplied by the caller so this helper has no authority to terminate a
 * process; it only observes the endpoint that the tracked session used.
 */
export async function waitForTcpStop(probe, {
  timeoutMs = 20_000,
  pollMs = 250
} = {}) {
  if (typeof probe !== "function") throw new Error("A TCP probe callback is required.");
  assertInteger(timeoutMs, "timeoutMs", 1, 180_000);
  assertInteger(pollMs, "pollMs", 1, 10_000);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!(await probe())) return true;
    await delay(Math.min(pollMs, Math.max(1, deadline - Date.now())));
  }
  return !(await probe());
}
