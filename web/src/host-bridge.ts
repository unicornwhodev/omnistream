import { App as McpApp } from '@modelcontextprotocol/ext-apps';

type ToolArguments = Record<string, unknown>;
type ToolCaller = (name: string, args: ToolArguments) => Promise<unknown>;
type HostPhase = 'offline' | 'initializing' | 'mcp' | 'legacy' | 'failed';
type Client = {
  connect: () => Promise<void>;
  callServerTool: (params: { name: string; arguments: ToolArguments }) => Promise<unknown>;
};

/** Request the expanded host surface once after initialization. A rejected
 * display request must not disable scene control or the Apps handshake. */
export async function requestExpandedDisplay(app: Pick<McpApp, 'getHostContext' | 'requestDisplayMode'>) {
  const context = app.getHostContext();
  if (context?.displayMode === 'fullscreen' ||
      (context?.availableDisplayModes && !context.availableDisplayModes.includes('fullscreen'))) return;
  try { await app.requestDisplayMode({ mode: 'fullscreen' }, { timeout: 5_000 }); }
  catch { /* Hosts may keep the current surface; controller readiness is independent. */ }
}

/** App hosts require the Apps handshake before any tool call.
 * Only the explicitly marked standalone developer harness keeps its shim. */
export function createHostBridge(client: Client, environment: {
  embedded: boolean;
  legacyCallTool?: ToolCaller;
  onPhase?: (phase: HostPhase) => void;
}) {
  let phase: HostPhase = environment.embedded ? 'initializing' : environment.legacyCallTool ? 'legacy' : 'offline';
  let pending: Promise<boolean> | null = null;
  const setPhase = (value: HostPhase) => { phase = value; environment.onPhase?.(value); };
  return {
    get phase() { return phase; },
    isReady: () => phase === 'mcp' || phase === 'legacy',
    start(): Promise<boolean> {
      if (!environment.embedded) return Promise.resolve(phase === 'legacy');
      if (!pending) pending = client.connect().then(() => {
        setPhase('mcp'); return true;
      }).catch(() => { setPhase('failed'); return false; });
      return pending;
    },
    async callTool(name: string, args: ToolArguments): Promise<unknown> {
      if (phase === 'mcp') return client.callServerTool({ name, arguments: args });
      if (phase === 'legacy' && environment.legacyCallTool) return environment.legacyCallTool(name, args);
      throw new Error('La connexion MCP Apps au contrôleur n’est pas initialisée. Rouvrez le panneau après avoir rechargé le plugin.');
    },
  };
}

let shared: ReturnType<typeof createHostBridge> | undefined;
function hostBridge() {
  if (shared) return shared;
  const hostWindow = window as Window & { __OMNISTREAM_PANEL_HARNESS__?: boolean; openai?: { callTool?: ToolCaller } };
  // Native hosts can expose a top-level WebView. parent === window is not proof
  // that this is the standalone harness and must never skip initialization.
  const standaloneHarness = hostWindow.__OMNISTREAM_PANEL_HARNESS__ === true && window.parent === window;
  const embedded = !standaloneHarness;
  const legacyCallTool = hostWindow.openai?.callTool?.bind(hostWindow.openai);
  const app = embedded ? new McpApp({ name: 'OmniStream for Codex', version: '1.0.0-rc4' }, { availableDisplayModes: ['inline', 'fullscreen'] }, { autoResize: true, strict: true }) : null;
  // Register before connect. Initial output is followed by authoritative reads
  // once the handshake has made the controller ready.
  const syncDisplayMode = () => {
    const mode = app?.getHostContext()?.displayMode;
    document.documentElement.dataset.omnistreamDisplayMode = mode || 'unknown';
  };
  if (app) {
    app.ontoolresult = () => {};
    app.addEventListener('hostcontextchanged', syncDisplayMode);
  }
  shared = createHostBridge({
    connect: async () => {
      if (!app) return;
      await app.connect(undefined, { timeout: 15_000 });
      syncDisplayMode();
      void requestExpandedDisplay(app);
    },
    callServerTool: params => {
      if (!app) return Promise.reject(new Error('Contrôleur MCP Apps indisponible.'));
      // Cold Kit startup can outlast the SDK's default request timeout.
      return app.callServerTool(params, { timeout: 180_000 });
    },
  }, {
    embedded, legacyCallTool,
    onPhase(phase) {
      document.documentElement.dataset.omnistreamHostBridge = phase;
      window.dispatchEvent(new Event('omnistream:host-bridge'));
    },
  });
  return shared;
}

export const startHostBridge = () => hostBridge().start();
export const isHostBridgeReady = () => hostBridge().isReady();
export const callHostTool = (name: string, args: ToolArguments) => hostBridge().callTool(name, args);
