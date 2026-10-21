export type SimulationConfiguration = {
  name: string;
  workspaceRoot: string;
  stagePath: string;
  kitRoot?: string;
  initialTimeSeconds: number;
  rateMultiplier: number;
  loop: boolean;
  playEveryFrame: boolean;
  autoPlay: boolean;
  cameraPath?: string;
  configuredAt?: string;
  configurationId?: string;
};

export type PreflightSnapshot = {
  ready: boolean;
  configurationId?: string;
  checks: { id: string; ok: boolean; label: string; detail: string; severity?: string }[];
  failed: string[];
};

type Operation = "validate" | "preflight" | "launch";
export type PreparationState = {
  version: number;
  draftRevision: number;
  validated: Readonly<SimulationConfiguration> | null;
  validatedRevision: number | null;
  requiresValidation: boolean;
  preflight: PreflightSnapshot | null;
  operation: Operation | null;
  issue: string | null;
};
type Ticket = { id: number; revision: number };
export type PreparationTransport = (name: string, args: Record<string, unknown>) => Promise<Record<string, unknown>>;

export const CONFIGURATION_CHANGED = "La configuration a changé. Validez et vérifiez de nouveau avant de lancer.";
export const CONTROLLER_INCOMPATIBLE = "Le contrôleur ne fournit pas l'identité de configuration requise. Mettez à jour le panneau et le contrôleur ensemble.";

const record = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : null;

export function parseConfiguration(value: unknown): SimulationConfiguration | null {
  const config = record(value);
  if (!config || typeof config.workspaceRoot !== "string" || typeof config.stagePath !== "string") return null;
  return {
    name: typeof config.name === "string" ? config.name : "Simulation",
    workspaceRoot: config.workspaceRoot,
    stagePath: config.stagePath,
    kitRoot: typeof config.kitRoot === "string" ? config.kitRoot : "",
    initialTimeSeconds: typeof config.initialTimeSeconds === "number" ? config.initialTimeSeconds : 0,
    rateMultiplier: typeof config.rateMultiplier === "number" ? config.rateMultiplier : 1,
    loop: config.loop === true,
    playEveryFrame: config.playEveryFrame === true,
    autoPlay: config.autoPlay === true,
    cameraPath: typeof config.cameraPath === "string" ? config.cameraPath : "",
    configuredAt: typeof config.configuredAt === "string" ? config.configuredAt : undefined,
    configurationId: typeof config.configurationId === "string" && config.configurationId.trim()
      ? config.configurationId : undefined,
  };
}

export function initialPreparation(): PreparationState {
  return { version: 0, draftRevision: 0, validated: null, validatedRevision: null,
    requiresValidation: false, preflight: null, operation: null, issue: null };
}

/** The same controller is used by React and the asynchronous behaviour tests. */
export class SessionPreparation {
  state: PreparationState = initialPreparation();
  private nextTicket = 0;
  private active: Ticket | null = null;
  private initialHydrationComplete = false;
  private readonly publish: (state: PreparationState) => void;
  constructor(publish: (state: PreparationState) => void = () => {}) {
    this.publish = publish;
  }

  private update(change: Partial<PreparationState>) {
    this.state = { ...this.state, ...change, version: this.state.version + 1 };
    this.publish(this.state);
  }

  get current() {
    return this.state.validated !== null &&
      this.state.validatedRevision === this.state.draftRevision &&
      !this.state.requiresValidation;
  }

  canLaunch(available = true) {
    return available && !this.active && this.current &&
      Boolean(this.state.validated?.configurationId) &&
      this.state.preflight?.ready === true &&
      this.state.preflight.configurationId === this.state.validated?.configurationId;
  }

  label(runtimeActive = false, available = true) {
    if (runtimeActive) return "Runtime actif";
    if (this.state.operation) return "Vérification en cours";
    if (this.state.requiresValidation) return "Modifications à valider";
    if (!this.current) return "À configurer";
    if (!available) return "Préflight bloqué";
    if (this.state.preflight?.ready === false) return "Préflight bloqué";
    return this.canLaunch() ? "Prêt à lancer" : "À configurer";
  }

  edit() {
    this.update({ draftRevision: this.state.draftRevision + 1, requiresValidation: true,
      preflight: null, issue: null });
  }

  /** Initial hydration may fill untouched inputs, but is not a new preflight. */
  canHydrate() {
    return !this.initialHydrationComplete && this.state.draftRevision === 0 && !this.active && !this.state.validated;
  }

  /** A complete controller snapshot wins over later runtime-default replies. */
  finishHydration() {
    this.initialHydrationComplete = true;
  }

  observe(value: unknown, observationVersion: number) {
    if (observationVersion !== this.state.version || this.active || !this.current) return;
    const config = parseConfiguration(value);
    if (config?.configurationId !== this.state.validated?.configurationId) {
      this.update({ requiresValidation: true, preflight: null,
        issue: config && !config.configurationId ? CONTROLLER_INCOMPATIBLE : CONFIGURATION_CHANGED });
    }
  }

  private begin(operation: Operation): Ticket | null {
    if (this.active) return null;
    const ticket = { id: ++this.nextTicket, revision: this.state.draftRevision };
    this.active = ticket;
    this.update({ operation, issue: null,
      ...(operation === "validate" ? { validated: null, validatedRevision: null, preflight: null } : {}) });
    return ticket;
  }

  private matches(ticket: Ticket) {
    return this.active?.id === ticket.id && ticket.revision === this.state.draftRevision;
  }

  private finish(ticket: Ticket) {
    if (this.active?.id !== ticket.id) return;
    this.active = null;
    this.update({ operation: null });
  }

  private async readPreflight(ticket: Ticket, transport: PreparationTransport) {
    const data = await transport("preflight_omniverse_simulation", {});
    if (!this.matches(ticket)) return null;
    const checked = parseConfiguration(data.configuration);
    if (!checked?.configurationId) throw new Error(CONTROLLER_INCOMPATIBLE);
    if (checked.configurationId !== this.state.validated?.configurationId) throw new Error(CONFIGURATION_CHANGED);
    const snapshot: PreflightSnapshot = {
      ready: data.ready === true,
      configurationId: checked.configurationId,
      checks: Array.isArray(data.checks) ? data.checks.flatMap((item) => {
        const row = record(item);
        return row && typeof row.id === "string" && typeof row.ok === "boolean" &&
          typeof row.label === "string" && typeof row.detail === "string"
          ? [{ id: row.id, ok: row.ok, label: row.label, detail: row.detail,
            severity: typeof row.severity === "string" ? row.severity : undefined }] : [];
      }) : [],
      failed: Array.isArray(data.failed) ? data.failed.filter((item): item is string => typeof item === "string") : [],
    };
    this.update({ preflight: snapshot });
    return snapshot;
  }

  async validate(args: Record<string, unknown>, transport: PreparationTransport,
    onNormalized: (config: SimulationConfiguration) => void = () => {}) {
    const ticket = this.begin("validate");
    if (!ticket) return null;
    try {
      const data = await transport("configure_omniverse_simulation", { ...args });
      if (!this.matches(ticket)) return null;
      const config = parseConfiguration(data.configuration);
      if (!config) throw new Error("Le contrôleur n'a pas renvoyé de configuration valide.");
      this.update({ validated: Object.freeze(config), validatedRevision: ticket.revision,
        requiresValidation: false });
      onNormalized(config);
      if (!config.configurationId) throw new Error(CONTROLLER_INCOMPATIBLE);
      const preflight = await this.readPreflight(ticket, transport);
      return preflight ? { configuration: config, preflight } : null;
    } catch (error) {
      if (!this.matches(ticket)) return null;
      this.update({ requiresValidation: true, preflight: null, issue: String(error instanceof Error ? error.message : error) });
      throw error;
    } finally {
      this.finish(ticket);
    }
  }

  async verify(transport: PreparationTransport) {
    if (!this.current) throw new Error("Validez d'abord le brouillon actuel.");
    const ticket = this.begin("preflight");
    if (!ticket) return null;
    this.update({ preflight: null });
    try {
      return await this.readPreflight(ticket, transport);
    } catch (error) {
      if (!this.matches(ticket)) return null;
      this.update({ requiresValidation: true, preflight: null, issue: String(error instanceof Error ? error.message : error) });
      throw error;
    } finally {
      this.finish(ticket);
    }
  }

  async launch<T>(available: boolean,
    start: (config: Readonly<SimulationConfiguration>, args: { expectedConfigurationId: string }) => Promise<T>) {
    if (!this.canLaunch(available)) return null;
    const config = this.state.validated!;
    const ticket = this.begin("launch")!;
    try {
      return await start(config, { expectedConfigurationId: config.configurationId! });
    } catch (error) {
      this.update({ requiresValidation: true, preflight: null, issue: String(error instanceof Error ? error.message : error) });
      throw error;
    } finally {
      this.finish(ticket);
    }
  }
}
