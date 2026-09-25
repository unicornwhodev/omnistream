export class OperationClientTimeoutError extends Error {
  constructor(operationName, timeoutMs) {
    super(operationName + " is still completing after " + timeoutMs + " ms.");
    this.name = "OperationClientTimeoutError";
    this.code = "client_timeout";
    this.operationName = operationName;
    this.timeoutMs = timeoutMs;
  }
}

export class OperationInProgressError extends Error {
  constructor(operationName) {
    super("An Omniverse operation is already in progress: " + operationName + ".");
    this.name = "OperationInProgressError";
    this.code = "operation_in_progress";
    this.operationName = operationName;
  }
}

function clientView(completion, operationName, clientTimeoutMs) {
  if (!clientTimeoutMs) return completion;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new OperationClientTimeoutError(operationName, clientTimeoutMs)), clientTimeoutMs);
    completion.then(
      (value) => {
        clearTimeout(timeout);
        resolve(value);
      },
      (error) => {
        clearTimeout(timeout);
        reject(error);
      }
    );
  });
}

/**
 * Serializes state-changing Kit work. A caller-facing timeout only affects the
 * client view: the completion promise and queue entry continue until the
 * underlying operation has a definite result.
 */
export class SerialOperationQueue {
  constructor({ onActiveChange = () => {} } = {}) {
    this.tail = Promise.resolve();
    this.active = null;
    this.queuedCount = 0;
    this.admissionClosed = false;
    this.onActiveChange = onActiveChange;
  }

  get busy() {
    return this.queuedCount > 0;
  }

  get activeName() {
    return this.active?.name || null;
  }

  get isAdmissionClosed() {
    return this.admissionClosed;
  }

  closeAdmission() {
    this.admissionClosed = true;
  }

  openAdmission() {
    this.admissionClosed = false;
  }

  assertIdle() {
    if (this.busy) throw new OperationInProgressError(this.activeName || "queued operation");
  }

  enqueue(name, work, { clientTimeoutMs = 0, allowWhenClosed = false } = {}) {
    if (typeof name !== "string" || !name) throw new Error("Operation name is required.");
    if (typeof work !== "function") throw new Error("Operation work callback is required.");
    if (this.admissionClosed && !allowWhenClosed) {
      throw new OperationInProgressError(this.activeName || "runtime shutdown or stop");
    }
    this.queuedCount += 1;
    const operation = { name, queuedAt: new Date().toISOString(), startedAt: null };
    const execute = this.tail.then(async () => {
      this.active = operation;
      operation.startedAt = new Date().toISOString();
      this.onActiveChange(this.active);
      try {
        return await work(operation);
      } finally {
        this.active = null;
        this.queuedCount -= 1;
        this.onActiveChange(null);
      }
    });
    // Later entries must execute even if this operation fails. Keep an
    // internal rejection observer so a client timeout never produces an
    // unhandled rejection when completion arrives later.
    this.tail = execute.catch(() => {});
    void execute.catch(() => {});
    const client = clientView(execute, name, clientTimeoutMs);
    // Keep a rejection observer even if the MCP caller has not yet attached a
    // handler when its bounded client view expires. The queue completion still
    // runs and remains available to lifecycle code.
    void client.catch(() => {});
    return {
      operation,
      completion: execute,
      client
    };
  }

  async drain() {
    await this.tail;
  }
}
