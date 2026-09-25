import {
  AppStreamer,
  EventAction,
  EventStatus,
  StreamStatus,
  StreamType,
  type DirectConfig,
  type StreamEvent,
} from "@nvidia/ov-web-rtc";
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { Icon, type IconName } from "./Icon";
import { ErrorBoundary } from "./ErrorBoundary";
import { ConfirmationProvider, useConfirm } from "./Confirmation";
import { parseToolResult, observedState } from "./tool-result.mjs";
import { SceneWorkbench, LiveSceneStrip, useLiveScene } from "./SceneWorkbench";

declare global {
  interface Window {
    openai?: {
      callTool?: (
        name: string,
        args: Record<string, unknown>,
      ) => Promise<unknown>;
      toolResponseMetadata?: unknown;
    };
  }
}

type RuntimeStatus = {
  kitRoot?: string;
  releaseRoot?: string;
  runtimeReady?: boolean;
  processAlive?: boolean;
  processId?: number | null;
  processOwnership?: string;
  stagePath?: string;
  workspaceRoot?: string;
  defaultWorkspaceRoot?: string;
  assetRoots?: string[];
  omnistreamHome?: string;
  logsRoot?: string;
  streamListening?: boolean;
  controlBridgeConnected?: boolean;
  message?: string;
  signalingHost?: string;
  signalingPort?: number;
  mediaPort?: number;
  requiresBearerAuthentication?: boolean;
  networkBoundary?: string;
  lifecyclePhase?: string;
  operationInProgress?: string | null;
  simulationRunId?: string | null;
  simulationRunStartedAt?: string | null;
  simulationRunName?: string | null;
  simulationConfigured?: boolean;
  pluginVersion?: string;
  runtimeChannel?: string | null;
};

type TimelineState = {
  currentTime?: number;
  startTime?: number;
  endTime?: number;
  timeCodesPerSecond?: number;
  targetFrameRate?: number;
  rateMultiplier?: number;
  isPlaying?: boolean;
};

type Camera = {
  path: string;
  label?: string;
};

type AssetSource = {
  label: string;
  path: string;
  stageCount: number;
  stageCapped: boolean;
  assetCount: number;
  assetCapped: boolean;
};

type AssetDiscoveryStatus = {
  kind: string;
  configuredRootCount: number;
  legacyContentDetected: boolean;
  message: string;
};

type SimulationState = Record<string, unknown> & {
  stagePath?: string;
  state?: string;
  timeSeconds?: number;
  rateMultiplier?: number;
  targetFramerate?: number;
  timeline?: TimelineState;
  cameras?: Camera[];
  camera?: Camera;
  selectedCamera?: string | null;
  controlBridgeConnected?: boolean;
  loop?: boolean;
  playEveryFrame?: boolean;
  initialTimeSeconds?: number;
  cameraDirty?: boolean;
  message?: string;
};

type SimulationConfiguration = {
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
};

type SupervisionSnapshot = {
  configuration?: SimulationConfiguration | null;
  run?: {
    runId: string;
    name: string;
    startedAt: string;
    uptimeSeconds?: number;
  } | null;
  runtime?: RuntimeStatus;
  simulation?: SimulationState | null;
  health?: Record<string, string>;
  simulationError?: string;
};

type PreflightCheck = {
  id: string;
  ok: boolean;
  label: string;
  detail: string;
  severity?: string;
};
type PreflightSnapshot = {
  ready: boolean;
  checks: PreflightCheck[];
  failed: string[];
};
type RuntimeLogResult = {
  available?: boolean;
  file?: string;
  lines?: string[];
};
type RuntimeLogsSnapshot = {
  stream?: string;
  lineLimit?: number;
  runtimeActive?: boolean;
  logs?: { stdout?: RuntimeLogResult; stderr?: RuntimeLogResult };
};
type JournalEntry = {
  id: number;
  at: string;
  tone: NoticeTone;
  message: string;
};

type PanelTab =
  "configure" | "launch" | "monitor" | "control" | "scene" | "debug";

type ConnectionTone = "neutral" | "working" | "live" | "error";
type NoticeTone = "neutral" | "working" | "error" | "success";

const DEFAULT_WORKSPACE = "";
// Cold Kit startup includes Composer, RTX, the WebRTC service, and the
// authenticated local control bridge.  The real runtime test uses the same
// bound so the panel does not mistake a normal first launch for a failure.
const KIT_READY_TIMEOUT_MS = 120_000;
const KIT_POLL_MS = 1_000;
const KIT_PROGRESS_INTERVAL_MS = 5_000;
// The SDK has its own connectivity timeout, but its promise can still remain
// pending when its internal reconnect state gets stuck.  Keep the panel's
// visible connection state bounded independently of that SDK behavior.
const APP_STREAM_CONNECT_TIMEOUT_MS = 75_000;
const APP_STREAM_CONNECT_TIMEOUT_ERROR =
  "La connexion WebRTC locale a dépassé le délai du panneau. Vérifiez que Kit est toujours actif, puis actualisez ou relancez le flux.";
const APP_STREAM_PENDING_NEGOTIATION_ERROR =
  "La négociation WebRTC précédente se ferme encore dans le SDK. Attendez sa fin avant de démarrer ou de rattacher un nouveau flux. Si elle reste bloquée, fermez puis rouvrez le panneau ou arrêtez Kit avant de réessayer.";
const SDK_STREAM_RETIRE_POLL_MS = 250;
const RUNTIME_WATCHDOG_INTERVAL_MS = 1_000;
const TOOL_NAMES = {
  configureSimulation: "configure_omniverse_simulation",
  preflightSimulation: "preflight_omniverse_simulation",
  launchSimulation: "launch_omniverse_simulation",
  superviseSimulation: "supervise_omniverse_simulation",
  runtimeLogs: "read_omnistream_runtime_logs",
  controlSimulation: "control_omniverse_simulation",
  attachStream: "attach_omniverse_stream",
  loadStage: "load_omniverse_stage",
  simulationState: "get_omniverse_simulation_state",
  timeline: "control_omniverse_timeline",
  cameras: "list_omniverse_cameras",
  selectCamera: "select_omniverse_camera",
  navigateCamera: "navigate_omniverse_camera",
  saveCamera: "save_omniverse_camera",
} as const;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function errorText(value: unknown) {
  if (value instanceof Error) return value.message;
  if (typeof value === "string") return value;
  return "La commande n'a pas abouti.";
}

function toolData(response: unknown): Record<string, unknown> {
  return parseToolResult(response);
}

function metadataFromEnvelope(value: unknown): Record<string, unknown> {
  const root = asRecord(value);
  if (!root) return {};
  const envelopes = [
    root,
    asRecord(root.result),
    asRecord(root.mcp_tool_result),
    asRecord(root.call_tool_result),
    asRecord(root.tool_result),
  ].filter((candidate): candidate is Record<string, unknown> =>
    Boolean(candidate),
  );

  for (const envelope of envelopes) {
    const metadata = asRecord(envelope._meta) ?? asRecord(envelope.metadata);
    if (metadata) return metadata;
  }
  return root;
}

function responseMeta(response: unknown): Record<string, unknown> {
  const fallback = metadataFromEnvelope(response);
  const canonical = metadataFromEnvelope(window.openai?.toolResponseMetadata);
  return { ...fallback, ...canonical };
}

function privateWidgetMetadata(): Record<string, unknown> {
  // The reattach bearer is intentionally accepted only from the host's
  // canonical private metadata slot, never from the tool result envelope.
  return metadataFromEnvelope(window.openai?.toolResponseMetadata);
}

async function callHostTool(name: string, args: Record<string, unknown>) {
  const callTool = window.openai?.callTool;
  if (!callTool)
    throw new Error(
      "Le pont d'outils Codex n'est pas disponible dans ce panneau.",
    );
  return callTool.call(window.openai, name, args);
}

function isSuccessful(event: StreamEvent) {
  return (
    event.action === EventAction.START && event.status === EventStatus.SUCCESS
  );
}

function loopbackHost(value: unknown) {
  return value === "127.0.0.1" || value === "::1" ? value : "127.0.0.1";
}

function isManagedActiveRuntime(runtime: RuntimeStatus) {
  return (
    runtime.processAlive === true &&
    runtime.processOwnership === "owned" &&
    runtime.streamListening === true &&
    runtime.controlBridgeConnected === true
  );
}

function numberOr(value: string, fallback: number) {
  const parsed = value.trim() ? Number(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : fallback;
}

function delay(milliseconds: number) {
  return new Promise<void>((resolve) =>
    window.setTimeout(resolve, milliseconds),
  );
}

function readCameras(value: unknown): Camera[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item === "string") return [{ path: item }];
    const camera = asRecord(item);
    return camera && typeof camera.path === "string"
      ? [
          {
            path: camera.path,
            ...(typeof camera.label === "string"
              ? { label: camera.label }
              : {}),
          },
        ]
      : [];
  });
}

function readAssetSources(value: unknown): AssetSource[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const source = asRecord(item);
    if (
      !source ||
      typeof source.label !== "string" ||
      typeof source.path !== "string" ||
      typeof source.stageCount !== "number" ||
      typeof source.stageCapped !== "boolean" ||
      typeof source.assetCount !== "number" ||
      typeof source.assetCapped !== "boolean"
    )
      return [];
    return [
      {
        label: source.label,
        path: source.path,
        stageCount: source.stageCount,
        stageCapped: source.stageCapped,
        assetCount: source.assetCount,
        assetCapped: source.assetCapped,
      },
    ];
  });
}

function compactPath(value: string | undefined, empty = "—") {
  if (!value) return empty;
  const normalized = value.replaceAll("\\", "/");
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length <= 3) return value;
  return `…/${parts.slice(-3).join("/")}`;
}

function healthTone(value: string | undefined) {
  if (value === "ready" || value === "playing") return "ready";
  if (value === "starting" || value === "waiting" || value === "paused")
    return "working";
  if (value === "unavailable" || value === "offline") return "error";
  return "neutral";
}

function StatusPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="status-pill" data-tone={healthTone(value)}>
      <span aria-hidden="true" />
      {label}
      <strong>{observedState(value)}</strong>
    </span>
  );
}

function ToggleControl({
  label,
  detail,
  checked,
  onChange,
  disabled = false,
}: {
  label: string;
  detail: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="toggle-row">
      <span>
        <strong>{label}</strong>
        <small>{detail}</small>
      </span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        disabled={disabled}
      />
      <span className="toggle-track" aria-hidden="true">
        <span />
      </span>
    </label>
  );
}

function App() {
  const confirm = useConfirm();
  const [hostReady, setHostReady] = useState(Boolean(window.openai?.callTool));
  const [hostError, setHostError] = useState("");
  const [lastObservedAt, setLastObservedAt] = useState<number | null>(null);
  const supervisionBusy = useRef(false);
  const [workbenchBusy, setWorkbenchBusy] = useState(false);
  const sceneCall = async (name: string, args: Record<string, unknown>) =>
    toolData(await callHostTool(name, args));
  const { live: liveScene, events: sceneEvents } = useLiveScene(
    sceneCall,
    hostReady,
  );
  const streamer = useRef<AppStreamer | null>(null);
  const streamEpoch = useRef(0);
  const connectInFlight = useRef<{
    epoch: number;
    promise: Promise<void>;
  } | null>(null);
  const pendingSdkConnect = useRef<Promise<StreamEvent> | null>(null);
  const pendingSdkStreamer = useRef<AppStreamer | null>(null);
  const pendingSdkRetirement = useRef<Promise<void> | null>(null);
  const sessionFlowEpoch = useRef(0);
  const initialAttachAttempted = useRef(false);
  const runtimeWatchdog = useRef<number | null>(null);
  const runtimeWatchdogEpoch = useRef(0);
  const runtimeWatchdogBusy = useRef(false);
  const pendingStagePath = useRef("");
  const connectionIsLive = useRef(false);
  const videoFrameSeen = useRef(false);
  const viewportFrameRef = useRef<HTMLDivElement | null>(null);
  const viewportGuardCleanup = useRef<(() => void) | null>(null);
  const [kitRoot, setKitRoot] = useState("");
  const [workspaceRoot, setWorkspaceRoot] = useState(DEFAULT_WORKSPACE);
  const [stagePath, setStagePath] = useState("");
  const [stages, setStages] = useState<string[]>([]);
  const [assets, setAssets] = useState<string[]>([]);
  const [assetSources, setAssetSources] = useState<AssetSource[]>([]);
  const [, setAssetDiscovery] = useState<AssetDiscoveryStatus | null>(null);
  const [runtime, setRuntime] = useState<RuntimeStatus>({});
  const [simulation, setSimulation] = useState<SimulationState>({});
  const [connectionTone, setConnectionTone] =
    useState<ConnectionTone>("neutral");
  const [hasVideoFrame, setHasVideoFrame] = useState(false);
  const [noticeTone, setNoticeTone] = useState<NoticeTone>("neutral");
  const [status, setStatus] = useState("Connexion au contrôleur non vérifiée.");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [stats, setStats] = useState("");
  const [seekTime, setSeekTime] = useState("0");
  const [rateMultiplier, setRateMultiplier] = useState("1");
  const [activeTab, setActiveTab] = useState<PanelTab>("configure");
  const [simulationName, setSimulationName] = useState("");
  const [initialTime, setInitialTime] = useState("0");
  const [loopEnabled, setLoopEnabled] = useState(false);
  const [playEveryFrame, setPlayEveryFrame] = useState(false);
  const [autoPlay, setAutoPlay] = useState(false);
  const [launchCameraPath, setLaunchCameraPath] = useState("");
  const [configuredSimulation, setConfiguredSimulation] =
    useState<SimulationConfiguration | null>(null);
  const [supervision, setSupervision] = useState<SupervisionSnapshot>({});
  const [preflight, setPreflight] = useState<PreflightSnapshot | null>(null);
  const [runtimeLogs, setRuntimeLogs] = useState<RuntimeLogsSnapshot | null>(
    null,
  );
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const journalCounter = useRef(0);

  const busy = busyAction !== null || workbenchBusy || !hostReady;
  const controlAvailable = Boolean(
    hostReady &&
    !hostError &&
    runtime.processAlive === true &&
    runtime.controlBridgeConnected === true &&
    !supervision.simulationError,
  );
  const selectedCamera =
    controlAvailable && typeof simulation.selectedCamera === "string"
      ? simulation.selectedCamera
      : "";
  const cameras = readCameras(simulation.cameras);
  const timeline = asRecord(simulation.timeline) as TimelineState | null;
  const timelineState =
    controlAvailable && typeof simulation.state === "string"
      ? simulation.state
      : undefined;
  const currentTime = !controlAvailable
    ? undefined
    : typeof simulation.timeSeconds === "number"
      ? simulation.timeSeconds
      : timeline?.currentTime;
  const currentRate = !controlAvailable
    ? undefined
    : typeof simulation.rateMultiplier === "number"
      ? simulation.rateMultiplier
      : timeline?.rateMultiplier;

  const report = (message: string, tone: NoticeTone = "neutral") => {
    setStatus(message);
    setNoticeTone(tone);
    const entry: JournalEntry = {
      id: ++journalCounter.current,
      at: new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
      tone,
      message,
    };
    setJournal((previous) => [...previous.slice(-39), entry]);
  };

  const mergeSimulation = (data: Record<string, unknown>) => {
    const camera = asRecord(data.camera);
    const returnedCameraPath =
      typeof camera?.path === "string" ? camera.path : undefined;
    setSimulation((previous) => ({
      ...previous,
      ...data,
      ...(returnedCameraPath && typeof data.selectedCamera !== "string"
        ? { selectedCamera: returnedCameraPath }
        : {}),
    }));
    setRuntime((previous) => ({
      ...previous,
      ...(typeof data.stagePath === "string"
        ? { stagePath: data.stagePath }
        : {}),
      ...(typeof data.controlBridgeConnected === "boolean"
        ? { controlBridgeConnected: data.controlBridgeConnected }
        : {}),
    }));
  };

  const syncConfiguration = (value: unknown) => {
    const config = asRecord(value);
    if (
      !config ||
      typeof config.workspaceRoot !== "string" ||
      typeof config.stagePath !== "string"
    )
      return;
    const normalized: SimulationConfiguration = {
      name: typeof config.name === "string" ? config.name : "Simulation",
      workspaceRoot: config.workspaceRoot,
      stagePath: config.stagePath,
      kitRoot: typeof config.kitRoot === "string" ? config.kitRoot : "",
      initialTimeSeconds:
        typeof config.initialTimeSeconds === "number"
          ? config.initialTimeSeconds
          : 0,
      rateMultiplier:
        typeof config.rateMultiplier === "number" ? config.rateMultiplier : 1,
      loop: config.loop === true,
      playEveryFrame: config.playEveryFrame === true,
      autoPlay: config.autoPlay === true,
      cameraPath:
        typeof config.cameraPath === "string" ? config.cameraPath : "",
      configuredAt:
        typeof config.configuredAt === "string"
          ? config.configuredAt
          : undefined,
    };
    setConfiguredSimulation(normalized);
    setSimulationName(normalized.name);
    setWorkspaceRoot(normalized.workspaceRoot);
    setStagePath(normalized.stagePath);
    if (normalized.kitRoot) setKitRoot(normalized.kitRoot);
    setInitialTime(String(normalized.initialTimeSeconds));
    setRateMultiplier(String(normalized.rateMultiplier));
    setLoopEnabled(normalized.loop);
    setPlayEveryFrame(normalized.playEveryFrame);
    setAutoPlay(normalized.autoPlay);
    setLaunchCameraPath(normalized.cameraPath || "");
  };

  const currentConfigurationArgs = () => ({
    name: simulationName.trim() || "Simulation",
    workspaceRoot: workspaceRoot.trim(),
    stagePath: stagePath.trim(),
    ...(kitRoot.trim() ? { kitRoot: kitRoot.trim() } : {}),
    initialTimeSeconds: numberOr(initialTime, 0),
    rateMultiplier: numberOr(rateMultiplier, 1),
    loop: loopEnabled,
    playEveryFrame,
    autoPlay,
    ...(launchCameraPath.trim() ? { cameraPath: launchCameraPath.trim() } : {}),
  });

  const applySupervision = (data: Record<string, unknown>) => {
    const runtimeData = asRecord(data.runtime);
    const simulationData = asRecord(data.simulation);
    if (runtimeData)
      setRuntime((previous) => ({
        ...previous,
        ...(runtimeData as RuntimeStatus),
      }));
    if (simulationData) mergeSimulation(simulationData);
    // Polling must never overwrite a configuration the user is typing.
    if (data.configuration)
      setConfiguredSimulation(data.configuration as SimulationConfiguration);
    setSupervision({
      configuration:
        (asRecord(
          data.configuration,
        ) as unknown as SimulationConfiguration | null) ?? null,
      run: (asRecord(data.run) as SupervisionSnapshot["run"]) ?? null,
      runtime: (runtimeData as RuntimeStatus | null) ?? undefined,
      simulation: (simulationData as SimulationState | null) ?? null,
      health:
        (asRecord(data.health) as Record<string, string> | null) ?? undefined,
      simulationError:
        typeof data.simulationError === "string"
          ? data.simulationError
          : undefined,
    });
  };

  const callSimulationTool = async (
    tool: string,
    args: Record<string, unknown>,
    pendingMessage: string,
    successMessage: string,
  ) => {
    setBusyAction(tool);
    report(pendingMessage, "working");
    try {
      const data = toolData(await callHostTool(tool, args));
      mergeSimulation(data);
      report(
        typeof data.message === "string" ? data.message : successMessage,
        "success",
      );
      return data;
    } catch (error) {
      report(errorText(error), "error");
      return null;
    } finally {
      setBusyAction(null);
    }
  };

  const readRuntimeStatus = async () => {
    const current = toolData(
      await callHostTool("get_omniverse_stream_status", {}),
    ) as RuntimeStatus;
    setRuntime(current);
    setLastObservedAt(Date.now());
    setHostError("");
    if (
      !kitRoot.trim() &&
      typeof current.kitRoot === "string" &&
      current.kitRoot.trim()
    )
      setKitRoot(current.kitRoot);
    if (
      !workspaceRoot.trim() &&
      typeof current.defaultWorkspaceRoot === "string" &&
      current.defaultWorkspaceRoot.trim()
    ) {
      setWorkspaceRoot(current.defaultWorkspaceRoot);
    }
    return current;
  };

  const refreshRuntime = async (announce = true) => {
    if (announce) {
      setBusyAction("refresh-runtime");
      report("Actualisation de l'état du runtime…", "working");
    }
    try {
      const current = await readRuntimeStatus();
      // The bridge is intentionally late in a cold Kit boot.  Do not flood it
      // with rejected simulation-state requests while it is still starting.
      if (current.processAlive && current.controlBridgeConnected) {
        try {
          const state = toolData(
            await callHostTool(TOOL_NAMES.simulationState, {}),
          );
          mergeSimulation(state);
        } catch (error) {
          if (announce) report(errorText(error), "error");
          return current;
        }
      }
      if (announce)
        report(current.message || "Statut Kit mis à jour.", "success");
      return current;
    } catch (error) {
      setHostError(errorText(error));
      setSimulation({});
      setSupervision({});
      if (announce) report(errorText(error), "error");
      return {};
    } finally {
      if (announce) setBusyAction(null);
    }
  };

  const waitForKitReady = async () => {
    const startedAt = Date.now();
    const deadline = startedAt + KIT_READY_TIMEOUT_MS;
    let nextProgressAt = startedAt + KIT_PROGRESS_INTERVAL_MS;
    let lastRuntime: RuntimeStatus = {};

    while (Date.now() < deadline) {
      const current = await readRuntimeStatus();
      lastRuntime = current;
      if (!current.processAlive) {
        throw new Error(
          "Le runtime Kit s'est arrêté avant que le flux WebRTC local soit prêt.",
        );
      }
      if (
        current.processAlive &&
        current.streamListening &&
        current.controlBridgeConnected
      )
        return current;

      if (Date.now() >= nextProgressAt) {
        const waitingFor = !current.streamListening
          ? "le serveur WebRTC"
          : "le pont de contrôle";
        const elapsedSeconds = Math.floor((Date.now() - startedAt) / 1_000);
        report(
          `Préparation de Kit… attente de ${waitingFor} (${elapsedSeconds}s / ${KIT_READY_TIMEOUT_MS / 1_000}s).`,
          "working",
        );
        nextProgressAt += KIT_PROGRESS_INTERVAL_MS;
      }
      await delay(KIT_POLL_MS);
    }

    throw new Error(
      lastRuntime.message ||
        "Kit n'a pas rendu le flux WebRTC et le pont de contrôle disponibles dans le délai de démarrage.",
    );
  };

  const setViewportInputActive = (active: boolean) => {
    if (!streamer.current || !connectionIsLive.current) return;
    void streamer.current
      .sendMessage({
        event_type: "setViewportInputActive",
        payload: { active },
      })
      .catch(() => undefined);
  };

  const markVideoFrameReady = () => {
    const video =
      viewportFrameRef.current?.querySelector<HTMLVideoElement>(
        "#remote-video",
      );
    if (
      !streamer.current ||
      !video ||
      videoFrameSeen.current ||
      video.videoWidth <= 0 ||
      video.videoHeight <= 0 ||
      video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA
    )
      return;

    videoFrameSeen.current = true;
    connectionIsLive.current = true;
    setHasVideoFrame(true);
    setConnectionTone("live");
    report(
      "Flux RTX de Kit actif. Placez le focus dans la scène pour les interactions natives.",
      "success",
    );
  };

  const stopRuntimeWatchdog = () => {
    runtimeWatchdogEpoch.current += 1;
    runtimeWatchdogBusy.current = false;
    if (runtimeWatchdog.current !== null) {
      window.clearInterval(runtimeWatchdog.current);
      runtimeWatchdog.current = null;
    }
  };

  const hasPendingSdkNegotiation = () =>
    pendingSdkConnect.current !== null || pendingSdkRetirement.current !== null;

  const retireStreamer = (candidate: AppStreamer | null) => {
    if (!candidate) return Promise.resolve();
    if (pendingSdkRetirement.current) return pendingSdkRetirement.current;

    const pendingConnection =
      pendingSdkStreamer.current === candidate
        ? pendingSdkConnect.current
        : null;
    if (pendingConnection) {
      // ov-web-rtc reports IN_PROGRESS while STARTING and does not cancel the
      // underlying connect. Request termination now, then retain the barrier
      // until that original promise settles and the SDK has no stream left.
      void candidate.terminate(false).catch(() => undefined);
    }

    const retirement = (
      pendingConnection
        ? pendingConnection.catch(() => undefined)
        : Promise.resolve()
    )
      .then(async () => {
        while (candidate.streamStatus === StreamStatus.STARTING)
          await delay(SDK_STREAM_RETIRE_POLL_MS);
        if (candidate.streamStatus !== StreamStatus.NONE)
          void candidate.terminate(false).catch(() => undefined);
        while (candidate.streamStatus !== StreamStatus.NONE)
          await delay(SDK_STREAM_RETIRE_POLL_MS);
      })
      .finally(() => {
        if (pendingSdkRetirement.current === retirement)
          pendingSdkRetirement.current = null;
        if (pendingSdkConnect.current === pendingConnection) {
          pendingSdkConnect.current = null;
          pendingSdkStreamer.current = null;
        }
      });

    pendingSdkRetirement.current = retirement;
    return retirement;
  };

  const invalidateStream = () => {
    const previousStreamer = streamer.current;
    streamEpoch.current += 1;
    streamer.current = null;
    connectionIsLive.current = false;
    videoFrameSeen.current = false;
    setHasVideoFrame(false);
    setStats("");
    viewportGuardCleanup.current?.();
    viewportGuardCleanup.current = null;
    if (previousStreamer) void retireStreamer(previousStreamer);
  };

  const startRuntimeWatchdog = () => {
    stopRuntimeWatchdog();
    const watchdogEpoch = runtimeWatchdogEpoch.current;
    const checkRuntime = async () => {
      if (
        runtimeWatchdogBusy.current ||
        runtimeWatchdogEpoch.current !== watchdogEpoch
      )
        return;
      runtimeWatchdogBusy.current = true;
      try {
        const current = await readRuntimeStatus();
        if (
          runtimeWatchdogEpoch.current !== watchdogEpoch ||
          current.processAlive
        )
          return;

        stopRuntimeWatchdog();
        invalidateStream();
        setSimulation({});
        setConnectionTone("neutral");
        report(
          "Le runtime Kit a été arrêté hors de ce panneau. Démarrez Kit caché pour une nouvelle session.",
          "error",
        );
      } catch {
        // A transient status read must not tear down a still-running local
        // viewport. The next bounded watchdog pass will retry.
      } finally {
        runtimeWatchdogBusy.current = false;
      }
    };

    void checkRuntime();
    runtimeWatchdog.current = window.setInterval(() => {
      void checkRuntime();
    }, RUNTIME_WATCHDOG_INTERVAL_MS);
  };

  const installViewportFocusGuard = () => {
    const viewportRoot = viewportFrameRef.current;
    const video =
      viewportRoot?.querySelector<HTMLVideoElement>("#remote-video");
    if (!viewportRoot || !video) return;

    viewportGuardCleanup.current?.();
    const restoreFocusability = () => {
      if (video.tabIndex !== 0) video.tabIndex = 0;
      if (video.getAttribute("tabindex") !== "0")
        video.setAttribute("tabindex", "0");
      if (video.style.outline === "none") video.style.removeProperty("outline");
    };
    const allowStandardTab = (event: KeyboardEvent) => {
      if (event.key === "Tab") event.stopPropagation();
    };
    const observer = new MutationObserver(restoreFocusability);

    restoreFocusability();
    observer.observe(video, {
      attributes: true,
      attributeFilter: ["tabindex", "style"],
    });
    viewportRoot.addEventListener("keydown", allowStandardTab, {
      capture: true,
    });
    viewportGuardCleanup.current = () => {
      observer.disconnect();
      viewportRoot.removeEventListener("keydown", allowStandardTab, {
        capture: true,
      });
    };
  };

  const connect = (
    streamAccessToken: string,
    currentRuntime: RuntimeStatus,
  ) => {
    const activeAttempt = connectInFlight.current;
    if (activeAttempt) {
      return activeAttempt.epoch === streamEpoch.current
        ? activeAttempt.promise
        : Promise.reject(new Error(APP_STREAM_PENDING_NEGOTIATION_ERROR));
    }
    if (hasPendingSdkNegotiation())
      return Promise.reject(new Error(APP_STREAM_PENDING_NEGOTIATION_ERROR));
    if (!streamAccessToken)
      return Promise.reject(
        new Error("Le jeton WebRTC de cette session Kit est absent."),
      );

    const epoch = ++streamEpoch.current;
    const currentStreamer = new AppStreamer();
    streamer.current = currentStreamer;
    const isCurrentStream = () =>
      streamEpoch.current === epoch && streamer.current === currentStreamer;
    const attempt = (async () => {
      setConnectionTone("working");
      report("Connexion au flux RTX local…", "working");
      const config: DirectConfig = {
        videoElementId: "remote-video",
        signalingServer: loopbackHost(currentRuntime.signalingHost),
        signalingPort:
          typeof currentRuntime.signalingPort === "number"
            ? currentRuntime.signalingPort
            : 49100,
        mediaServer: "127.0.0.1",
        mediaPort:
          typeof currentRuntime.mediaPort === "number"
            ? currentRuntime.mediaPort
            : 47998,
        width: 1280,
        height: 720,
        fps: 30,
        authenticate: true,
        accessToken: streamAccessToken,
        nativeTouchEvents: false,
        maxReconnects: 5,
        reconnectDelay: 1_500,
        connectivityTimeout: 10_000,
        onStart: (event) => {
          if (!isCurrentStream()) {
            void retireStreamer(currentStreamer);
            return;
          }
          if (isSuccessful(event)) {
            report(
              "Flux WebRTC négocié ; attente de la première image RTX…",
              "working",
            );
          } else if (event.status === EventStatus.WARNING) {
            report(
              String(event.info || "Nouvelle tentative WebRTC locale…"),
              "working",
            );
          } else if (event.status === EventStatus.ERROR) {
            setConnectionTone("error");
            report(
              String(event.info || "La négociation WebRTC a échoué."),
              "error",
            );
          }
        },
        onStop: () => {
          if (!isCurrentStream()) return;
          connectionIsLive.current = false;
          videoFrameSeen.current = false;
          setHasVideoFrame(false);
          setConnectionTone("error");
          report(
            "Le flux WebRTC s'est arrêté. Le panneau vérifie l'état du runtime Kit.",
            "error",
          );
        },
        onTerminate: () => {
          if (!isCurrentStream()) return;
          connectionIsLive.current = false;
          videoFrameSeen.current = false;
          setHasVideoFrame(false);
          setConnectionTone("error");
          report(
            "La connexion WebRTC est terminée. Le panneau vérifie l'état du runtime Kit.",
            "error",
          );
        },
        onStreamStats: (event) => {
          if (!isCurrentStream()) return;
          const data = event.data?.stats;
          if (data)
            setStats(
              `${String(data.streamingResolutionWidth)} × ${String(data.streamingResolutionHeight)} · ${String(data.fps)} fps · ${String(Math.round(data.currentBitrate || 0))} Mbps`,
            );
        },
        onCustomEvent: (event) => {
          if (!isCurrentStream()) return;
          const message = event as {
            event_type?: string;
            eventType?: string;
            payload?: Record<string, unknown>;
          };
          const type = message.event_type || message.eventType || "";
          const payload = message.payload || {};
          if (
            type === "codexRuntimeStatus" ||
            type === "codexSimulationState" ||
            type === "codexStageResult"
          ) {
            mergeSimulation(payload);
          }
          if (type === "codexRuntimeError") {
            if (typeof payload.message === "string") {
              report(payload.message, "error");
            } else if (
              payload.operation === "openStage" &&
              payload.code === "stage_load_timeout"
            ) {
              report(
                "La scène USD a dépassé le délai de préparation de Kit. Le runtime reste actif ; réessayez le chargement une fois RTX prêt.",
                "error",
              );
            } else if (typeof payload.code === "string") {
              report(
                `Kit a signalé une erreur de session : ${payload.code}.`,
                "error",
              );
            } else {
              report("Kit a signalé une erreur de session.", "error");
            }
          }
        },
      };

      let connectTimeout: number | undefined;
      try {
        const sdkConnection = currentStreamer.connect({
          streamSource: StreamType.DIRECT,
          streamConfig: config,
        });
        pendingSdkConnect.current = sdkConnection;
        pendingSdkStreamer.current = currentStreamer;
        void sdkConnection
          .finally(() => {
            if (pendingSdkConnect.current === sdkConnection) {
              pendingSdkConnect.current = null;
              pendingSdkStreamer.current = null;
            }
          })
          .catch(() => undefined);
        const timeout = new Promise<never>((_resolve, reject) => {
          connectTimeout = window.setTimeout(() => {
            reject(new Error(APP_STREAM_CONNECT_TIMEOUT_ERROR));
          }, APP_STREAM_CONNECT_TIMEOUT_MS);
        });
        const event = await Promise.race([sdkConnection, timeout]);
        if (!isCurrentStream()) return;
        if (event.status === EventStatus.ERROR) {
          setConnectionTone("error");
          throw new Error(
            String(event.info || "La connexion au flux a échoué."),
          );
        }
        installViewportFocusGuard();
        window.requestAnimationFrame(() => {
          installViewportFocusGuard();
          markVideoFrameReady();
        });
      } catch (error) {
        if (isCurrentStream()) {
          invalidateStream();
          setConnectionTone("error");
        }
        throw error;
      } finally {
        if (connectTimeout !== undefined) window.clearTimeout(connectTimeout);
      }
    })();

    const attemptRecord = { epoch, promise: attempt };
    connectInFlight.current = attemptRecord;
    void attempt
      .finally(() => {
        if (connectInFlight.current === attemptRecord)
          connectInFlight.current = null;
      })
      .catch(() => undefined);
    return attempt;
  };

  const attachExistingRuntime = async (
    current: RuntimeStatus,
    flowEpoch: number,
  ) => {
    if (
      initialAttachAttempted.current ||
      sessionFlowEpoch.current !== flowEpoch ||
      !isManagedActiveRuntime(current)
    )
      return;

    initialAttachAttempted.current = true;
    setBusyAction("attach-runtime");
    setConnectionTone("working");
    report(
      "Runtime Kit existant détecté ; reconnexion sécurisée au flux RTX…",
      "working",
    );
    try {
      if (hasPendingSdkNegotiation())
        throw new Error(APP_STREAM_PENDING_NEGOTIATION_ERROR);
      const response = await callHostTool(TOOL_NAMES.attachStream, {});
      // A Start/Stop action supersedes the mount-time reattach.  Never let a
      // late bearer response create a second SDK connection for that action.
      if (sessionFlowEpoch.current !== flowEpoch) return;

      const attachedRuntime = toolData(response) as RuntimeStatus;
      if (!isManagedActiveRuntime(attachedRuntime)) {
        throw new Error(
          "Le runtime Kit existant n'est plus prêt pour une reconnexion WebRTC sécurisée.",
        );
      }
      const meta = privateWidgetMetadata();
      const streamAccessToken = meta["omnistream/streamAccessToken"];
      if (typeof streamAccessToken !== "string" || !streamAccessToken) {
        throw new Error(
          "Le runtime Kit existant n'a pas renvoyé le bearer WebRTC privé requis pour le panneau.",
        );
      }

      setRuntime((previous) => ({ ...previous, ...attachedRuntime }));
      startRuntimeWatchdog();
      await connect(streamAccessToken, attachedRuntime);
    } catch (error) {
      if (sessionFlowEpoch.current !== flowEpoch) return;
      stopRuntimeWatchdog();
      if (!connectionIsLive.current) invalidateStream();
      setConnectionTone("error");
      report(errorText(error), "error");
    } finally {
      setBusyAction((active) => (active === "attach-runtime" ? null : active));
    }
  };

  const loadStage = async (path = stagePath.trim()) => {
    if (!path) {
      report(
        "Saisissez ou sélectionnez un fichier USD sous le dossier de travail.",
        "error",
      );
      return;
    }
    if (
      simulation.stagePath &&
      !(await confirm({
        title: "Ouvrir un autre fichier USD",
        message:
          "Le chargement remplace la scène ouverte. Exportez les corrections et enregistrez les poses caméra à conserver avant de continuer.",
        confirmLabel: "Charger la scène",
        destructive: true,
      }))
    )
      return;
    const data = await callSimulationTool(
      TOOL_NAMES.loadStage,
      { stagePath: path },
      "Chargement de la scène USD…",
      "Scène USD chargée.",
    );
    if (data && typeof data.stagePath === "string")
      setStagePath(data.stagePath);
  };

  const start = async () => {
    sessionFlowEpoch.current += 1;
    stopRuntimeWatchdog();
    invalidateStream();
    setBusyAction("start");
    setConnectionTone("working");
    report("Démarrage de Kit sans fenêtre native…", "working");
    try {
      if (hasPendingSdkNegotiation())
        throw new Error(APP_STREAM_PENDING_NEGOTIATION_ERROR);
      const response = await callHostTool("start_omniverse_stream", {
        workspaceRoot,
        ...(kitRoot.trim() ? { kitRoot: kitRoot.trim() } : {}),
      });
      const current = toolData(response) as RuntimeStatus;
      const meta = responseMeta(response);
      setRuntime((previous) => ({ ...previous, ...current }));
      const streamAccessToken = meta["omnistream/streamAccessToken"];
      if (typeof streamAccessToken !== "string" || !streamAccessToken) {
        throw new Error(
          "Kit a démarré sans renvoyer le jeton WebRTC de cette session.",
        );
      }
      pendingStagePath.current = stagePath.trim();
      if (!pendingStagePath.current) {
        report(
          "Démarrage de Kit sans fenêtre native… aucune scène USD n'est encore sélectionnée.",
          "working",
        );
      }
      const readyRuntime = await waitForKitReady();
      startRuntimeWatchdog();
      await connect(streamAccessToken, readyRuntime);
      if (pendingStagePath.current) {
        const requestedStage = pendingStagePath.current;
        pendingStagePath.current = "";
        await loadStage(requestedStage);
      } else {
        report(
          "Connexion vidéo demandée. Chargez une scène USD ; l’état vidéo sera confirmé à réception d’une image.",
          "neutral",
        );
      }
    } catch (error) {
      stopRuntimeWatchdog();
      if (!connectionIsLive.current) invalidateStream();
      setConnectionTone("error");
      report(errorText(error), "error");
    } finally {
      setBusyAction(null);
    }
  };

  const stop = async () => {
    if (
      !(await confirm({
        title: "Arrêter Kit",
        message:
          "Arrêter le runtime Omniverse géré par cette session ? Toute correction de session ou caméra non exportée sera perdue. Mettez seulement en pause pour conserver la scène ouverte.",
        confirmLabel: "Arrêter le runtime",
        destructive: true,
      }))
    )
      return;
    sessionFlowEpoch.current += 1;
    setBusyAction("stop");
    report("Arrêt du runtime Kit caché…", "working");
    try {
      stopRuntimeWatchdog();
      invalidateStream();
      const current = toolData(
        await callHostTool("stop_omniverse_stream", {}),
      ) as RuntimeStatus;
      setRuntime(current);
      setSimulation({});
      setConnectionTone("neutral");
      report(current.message || "Runtime Kit arrêté.", "success");
    } catch (error) {
      report(errorText(error), "error");
    } finally {
      setBusyAction(null);
    }
  };

  const findStages = async (root = workspaceRoot) => {
    setBusyAction("find-stages");
    report("Recherche des scènes USD autorisées…", "working");
    try {
      const data = toolData(
        await callHostTool("list_workspace_usd_stages", {
          workspaceRoot: root,
        }),
      );
      const available = Array.isArray(data.stages)
        ? data.stages.filter((item): item is string => typeof item === "string")
        : [];
      const availableAssets = Array.isArray(data.assets)
        ? data.assets.filter((item): item is string => typeof item === "string")
        : [];
      setStages(available);
      setAssets(availableAssets);
      report(
        `${available.length}${data.capped === true ? "+" : ""} scène(s) USD et ${availableAssets.length}${data.assetsCapped === true ? "+" : ""} asset(s) locaux trouvés.`,
        "success",
      );
    } catch (error) {
      report(errorText(error), "error");
    } finally {
      setBusyAction(null);
    }
  };

  const discoverLocalAssets = async () => {
    setBusyAction("discover-assets");
    report("Détection des racines d’assets OmniStream…", "working");
    try {
      const data = toolData(
        await callHostTool("discover_omniverse_local_assets", {}),
      );
      setAssetSources(readAssetSources(data.sources));
      const discovery = asRecord(data.discovery);
      setAssetDiscovery(
        discovery &&
          typeof discovery.kind === "string" &&
          typeof discovery.configuredRootCount === "number" &&
          typeof discovery.legacyContentDetected === "boolean" &&
          typeof discovery.message === "string"
          ? {
              kind: discovery.kind,
              configuredRootCount: discovery.configuredRootCount,
              legacyContentDetected: discovery.legacyContentDetected,
              message: discovery.message,
            }
          : null,
      );
      const sources = readAssetSources(data.sources);
      report(
        `${sources.length} source(s) locale(s) OmniStream détectée(s).`,
        "success",
      );
    } catch (error) {
      report(errorText(error), "error");
    } finally {
      setBusyAction(null);
    }
  };

  const useAssetSource = (source: AssetSource) => {
    setWorkspaceRoot(source.path);
    setStagePath("");
    setStages([]);
    setAssets([]);
    void findStages(source.path);
  };

  const preflightSimulation = async (announce = true) => {
    if (announce) {
      setBusyAction("preflight-simulation");
      report("Vérification du préflight de simulation…", "working");
    }
    try {
      const data = toolData(
        await callHostTool(TOOL_NAMES.preflightSimulation, {}),
      );
      const checks = Array.isArray(data.checks)
        ? data.checks.flatMap((item) => {
            const row = asRecord(item);
            return row &&
              typeof row.id === "string" &&
              typeof row.ok === "boolean" &&
              typeof row.label === "string" &&
              typeof row.detail === "string"
              ? [
                  {
                    id: row.id,
                    ok: row.ok,
                    label: row.label,
                    detail: row.detail,
                    severity:
                      typeof row.severity === "string"
                        ? row.severity
                        : undefined,
                  },
                ]
              : [];
          })
        : [];
      const snapshot: PreflightSnapshot = {
        ready: data.ready === true,
        checks,
        failed: Array.isArray(data.failed)
          ? data.failed.filter(
              (item): item is string => typeof item === "string",
            )
          : [],
      };
      setPreflight(snapshot);
      if (announce)
        report(
          snapshot.ready
            ? "Préflight validé : la simulation peut être lancée."
            : `Préflight bloqué : ${snapshot.failed.length} contrôle(s) à corriger.`,
          snapshot.ready ? "success" : "error",
        );
      return snapshot;
    } catch (error) {
      setPreflight(null);
      if (announce) report(errorText(error), "error");
      return null;
    } finally {
      if (announce) setBusyAction(null);
    }
  };

  const readRuntimeLogs = async () => {
    setBusyAction("runtime-logs");
    report("Lecture des derniers logs Kit…", "working");
    try {
      const data = toolData(
        await callHostTool(TOOL_NAMES.runtimeLogs, {
          stream: "both",
          lines: 120,
        }),
      );
      setRuntimeLogs(data as unknown as RuntimeLogsSnapshot);
      report(
        data.runtimeActive === true
          ? "Logs du runtime actualisés."
          : "Aucun log de runtime géré n’est disponible pour cette session.",
        data.runtimeActive === true ? "success" : "neutral",
      );
    } catch (error) {
      report(errorText(error), "error");
    } finally {
      setBusyAction(null);
    }
  };

  const configureSimulation = async () => {
    if (!workspaceRoot.trim() || !stagePath.trim()) {
      report(
        "Un workspace et une scène USD sont nécessaires pour configurer une simulation.",
        "error",
      );
      setActiveTab("configure");
      return null;
    }
    setBusyAction("configure-simulation");
    report("Validation de la configuration de simulation…", "working");
    try {
      const data = toolData(
        await callHostTool(
          TOOL_NAMES.configureSimulation,
          currentConfigurationArgs(),
        ),
      );
      syncConfiguration(data.configuration);
      const checked = await preflightSimulation(false);
      report(
        checked?.ready
          ? "Configuration et préflight validés. La simulation peut être lancée."
          : "Configuration validée, mais le préflight signale encore des prérequis à corriger.",
        checked?.ready ? "success" : "error",
      );
      return asRecord(data.configuration);
    } catch (error) {
      report(errorText(error), "error");
      return null;
    } finally {
      setBusyAction(null);
    }
  };

  const launchSimulation = async () => {
    if (!workspaceRoot.trim() || !stagePath.trim()) {
      report("Configurez d'abord le workspace et la scène USD.", "error");
      setActiveTab("configure");
      return;
    }
    sessionFlowEpoch.current += 1;
    stopRuntimeWatchdog();
    invalidateStream();
    setBusyAction("launch-simulation");
    setConnectionTone("working");
    report("Préparation et lancement de la simulation…", "working");
    try {
      if (hasPendingSdkNegotiation())
        throw new Error(APP_STREAM_PENDING_NEGOTIATION_ERROR);
      const configuredData = toolData(
        await callHostTool(
          TOOL_NAMES.configureSimulation,
          currentConfigurationArgs(),
        ),
      );
      syncConfiguration(configuredData.configuration);
      const checked = await preflightSimulation(false);
      if (!checked?.ready) {
        setPreflight(checked);
        setActiveTab("launch");
        throw new Error(
          `Préflight bloqué : ${checked?.failed.length ?? 1} contrôle(s) requis ne sont pas validés.`,
        );
      }
      const response = await callHostTool(TOOL_NAMES.launchSimulation, {});
      const data = toolData(response);
      const meta = responseMeta(response);
      applySupervision(data);
      const runtimeData = asRecord(data.runtime) as RuntimeStatus | null;
      const streamAccessToken = meta["omnistream/streamAccessToken"];
      if (
        !runtimeData ||
        typeof streamAccessToken !== "string" ||
        !streamAccessToken
      ) {
        throw new Error(
          "La simulation a démarré sans métadonnées WebRTC utilisables par le panneau.",
        );
      }
      setRuntime((previous) => ({ ...previous, ...runtimeData }));
      startRuntimeWatchdog();
      await connect(streamAccessToken, runtimeData);
      setActiveTab("monitor");
      report(
        videoFrameSeen.current
          ? "Simulation lancée ; une image du flux RTX a été reçue."
          : "Simulation lancée ; transport négocié, en attente de la première image RTX.",
        videoFrameSeen.current ? "success" : "working",
      );
    } catch (error) {
      stopRuntimeWatchdog();
      if (!connectionIsLive.current) invalidateStream();
      setConnectionTone("error");
      report(errorText(error), "error");
    } finally {
      setBusyAction(null);
    }
  };

  const superviseSimulation = async (announce = true) => {
    if (supervisionBusy.current) return null;
    supervisionBusy.current = true;
    if (announce) {
      setBusyAction("supervise-simulation");
      report("Lecture de la supervision de simulation…", "working");
    }
    try {
      const data = toolData(
        await callHostTool(TOOL_NAMES.superviseSimulation, {}),
      );
      applySupervision(data);
      setLastObservedAt(Date.now());
      setHostError("");
      if (
        !asRecord(data.runtime)?.processAlive ||
        !asRecord(data.runtime)?.controlBridgeConnected
      )
        setSimulation({});
      if (announce) report("Supervision mise à jour.", "success");
      return data;
    } catch (error) {
      setHostError(errorText(error));
      if (announce) report(errorText(error), "error");
      return null;
    } finally {
      supervisionBusy.current = false;
      if (announce) setBusyAction(null);
    }
  };

  const controlSimulation = async (
    action:
      | "play"
      | "pause"
      | "stop"
      | "reset"
      | "step_forward"
      | "step_back"
      | "seek"
      | "set_rate"
      | "set_loop",
    override?: Record<string, unknown>,
  ) => {
    const args: Record<string, unknown> = { action, ...(override || {}) };
    if (action === "seek" && !Object.hasOwn(args, "timeSeconds"))
      args.timeSeconds = numberOr(seekTime, 0);
    if (action === "set_rate" && !Object.hasOwn(args, "rateMultiplier"))
      args.rateMultiplier = numberOr(rateMultiplier, 1);
    if (action === "set_loop" && !Object.hasOwn(args, "loop"))
      args.loop = loopEnabled;
    setBusyAction(`simulation-${action}`);
    report("Commande de simulation en cours…", "working");
    try {
      const data = toolData(
        await callHostTool(TOOL_NAMES.controlSimulation, args),
      );
      const simulationData = asRecord(data.simulation);
      if (simulationData) mergeSimulation(simulationData);
      if (data.configuration)
        setConfiguredSimulation(data.configuration as SimulationConfiguration);
      report(
        typeof simulationData?.message === "string"
          ? simulationData.message
          : "Commande de simulation appliquée.",
        "success",
      );
      void superviseSimulation(false);
    } catch (error) {
      report(errorText(error), "error");
    } finally {
      setBusyAction(null);
    }
  };

  const refreshSimulation = async () => {
    await callSimulationTool(
      TOOL_NAMES.simulationState,
      {},
      "Lecture de l'état de simulation…",
      "État de simulation mis à jour.",
    );
  };

  const listCameras = async () => {
    const data = await callSimulationTool(
      TOOL_NAMES.cameras,
      {},
      "Lecture des caméras de la scène…",
      "Liste des caméras mise à jour.",
    );
    if (!data) return;
    setSimulation((previous) => ({
      ...previous,
      ...data,
      cameras: readCameras(data.cameras),
    }));
  };

  const selectCamera = async (cameraPath: string) => {
    if (!cameraPath) return;
    await callSimulationTool(
      TOOL_NAMES.selectCamera,
      { cameraPath },
      "Sélection de la caméra…",
      "Caméra active sélectionnée.",
    );
  };

  const navigateCamera = async (
    command:
      | { mode: "orbit" | "pan"; horizontal: number; vertical: number }
      | { mode: "dolly"; amount: number },
  ) => {
    await callSimulationTool(
      TOOL_NAMES.navigateCamera,
      command,
      "Déplacement temporaire de la caméra…",
      "Pose de caméra temporairement mise à jour.",
    );
  };

  const saveCamera = async () => {
    if (
      !(await confirm({
        title: "Enregistrer la caméra",
        message:
          "Enregistrer explicitement la pose de la caméra existante sélectionnée dans le USD writable ? Cette action écrit le fichier source.",
        confirmLabel: "Enregistrer dans le USD",
      }))
    )
      return;
    await callSimulationTool(
      TOOL_NAMES.saveCamera,
      {},
      "Enregistrement explicite de la caméra…",
      "Pose de caméra enregistrée.",
    );
  };

  useEffect(() => {
    const check = () => setHostReady(Boolean(window.openai?.callTool));
    const timer = window.setInterval(check, 1000);
    window.addEventListener("openai:set_globals", check);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("openai:set_globals", check);
    };
  }, []);

  useEffect(() => {
    if (!hostReady) return;
    const initialFlowEpoch = sessionFlowEpoch.current;
    void (async () => {
      const current = await refreshRuntime(false);
      const initial = await superviseSimulation(false);
      if (initial?.configuration) syncConfiguration(initial.configuration);
      await attachExistingRuntime(current, initialFlowEpoch);
    })();
    void discoverLocalAssets();
    const onUnload = () => {
      sessionFlowEpoch.current += 1;
      stopRuntimeWatchdog();
      setViewportInputActive(false);
      invalidateStream();
    };
    window.addEventListener("beforeunload", onUnload);
    return () => {
      window.removeEventListener("beforeunload", onUnload);
      sessionFlowEpoch.current += 1;
      stopRuntimeWatchdog();
      setViewportInputActive(false);
      invalidateStream();
    };
  }, [hostReady]);

  useEffect(() => {
    if (!hostReady || busy) return;
    const poll = () => {
      if (document.visibilityState === "visible")
        void superviseSimulation(false);
    };
    const timer = window.setInterval(poll, 2_500);
    const onVisibility = () => {
      if (document.visibilityState === "visible")
        void superviseSimulation(false);
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [hostReady, busy]);

  useEffect(() => {
    setPreflight(null);
  }, [
    simulationName,
    kitRoot,
    workspaceRoot,
    stagePath,
    initialTime,
    rateMultiplier,
    loopEnabled,
    playEveryFrame,
    autoPlay,
    launchCameraPath,
  ]);

  const numericSeek = numberOr(seekTime, -1);
  const numericRate = numberOr(rateMultiplier, -1);
  const validSeek = numericSeek >= 0;
  const validRate = numericRate >= 0.05 && numericRate <= 8;

  const activeStage =
    controlAvailable && typeof simulation.stagePath === "string"
      ? simulation.stagePath
      : "";
  const observed = hostReady && !hostError && lastObservedAt !== null;
  const health = observed ? supervision.health || {} : {};
  const isSceneObserved = controlAvailable && Boolean(activeStage);
  const viewportState = !hostReady
    ? "Connectez le plugin à Codex"
    : hostError
      ? "Contrôleur indisponible"
      : connectionTone === "working"
        ? "Connexion au flux Omniverse"
        : runtime.processAlive
          ? "Flux vidéo non connecté"
          : "Votre scène apparaîtra ici";
  const tabInfo: Record<PanelTab, [string, string, IconName]> = {
    configure: [
      "Configuration",
      "Chemins et paramètres de lancement",
      "settings",
    ],
    launch: ["Session Kit", "Vérifier, lancer et rattacher le flux", "power"],
    scene: [
      "Scène & propriétés",
      "Inspecter et modifier la scène ouverte",
      "scene",
    ],
    control: ["Lecture & caméra", "Contrôler sans recharger la scène", "play"],
    monitor: ["Supervision", "État du runtime et journaux", "monitor"],
    debug: ["Diagnostic", "Surveiller et analyser les anomalies", "debug"],
  };
  const run = supervision.run;
  const runLabel = run
    ? timelineState === "playing"
      ? "Simulation en cours"
      : timelineState === "paused"
        ? "Simulation en pause"
        : "Simulation chargée"
    : configuredSimulation
      ? "Simulation configurée"
      : "Aucune simulation configurée";
  const configurationReady = Boolean(
    workspaceRoot.trim() &&
    stagePath.trim() &&
    validRate &&
    numberOr(initialTime, -1) >= 0,
  );

  const configurationCurrent = Boolean(
    configuredSimulation &&
    Object.entries(currentConfigurationArgs()).every(
      ([key, value]) =>
        (configuredSimulation as unknown as Record<string, unknown>)[key] ===
        value,
    ),
  );
  const navigate = (tab: PanelTab) => {
    setActiveTab(tab);
    if (window.matchMedia("(max-width: 1150px)").matches)
      window.requestAnimationFrame(() =>
        document
          .getElementById("inspector-panel")
          ?.scrollIntoView({ behavior: "auto", block: "start" }),
      );
  };
  return (
    <main className="studio-shell">
      <header className="studio-header">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            <span />
          </span>
          <div>
            <h1>OmniStream</h1>
            <p>Studio de contrôle Omniverse</p>
          </div>
        </div>
        <div className="header-context">
          <span className={observed ? "host-dot connected" : "host-dot"} />
          {!hostReady
            ? "Codex non connecté"
            : hostError
              ? "Contrôleur indisponible"
              : observed
                ? "Contrôleur local"
                : "Vérification du contrôleur"}
          <span className="version-tag">RC3</span>
        </div>
        <div className="header-health" aria-label="État de la simulation">
          <StatusPill
            label="Runtime"
            value={
              !observed
                ? "unknown"
                : health.runtime ||
                  (runtime.processAlive
                    ? "ready"
                    : runtime.runtimeReady
                      ? "idle"
                      : "offline")
            }
          />
          <StatusPill
            label="Vidéo"
            value={
              !observed
                ? "unknown"
                : hasVideoFrame
                  ? "ready"
                  : connectionTone === "working"
                    ? "starting"
                    : "offline"
            }
          />
          <StatusPill
            label="Bridge"
            value={
              !observed
                ? "unknown"
                : health.bridge ||
                  (runtime.controlBridgeConnected
                    ? "ready"
                    : runtime.processAlive
                      ? "starting"
                      : "offline")
            }
          />
        </div>
      </header>
      <nav className="deck-tabs" aria-label="Navigation du studio">
        {(
          [
            "configure",
            "launch",
            "scene",
            "control",
            "monitor",
            "debug",
          ] as PanelTab[]
        ).map((tab) => (
          <button
            key={tab}
            type="button"
            aria-current={activeTab === tab ? "page" : undefined}
            aria-controls="inspector-panel"
            title={tabInfo[tab][1]}
            className={activeTab === tab ? "active" : ""}
            onClick={() => navigate(tab)}
          >
            <Icon name={tabInfo[tab][2]} />
            <span>
              {
                {
                  configure: "Configurer",
                  launch: "Lancer",
                  scene: "Scène",
                  control: "Contrôler",
                  monitor: "Superviser",
                  debug: "Diagnostic",
                }[tab]
              }
            </span>
          </button>
        ))}
        <div className="rail-foot">
          LOCAL
          <br />
          MCP
        </div>
      </nav>
      <section
        className="viewer-column"
        aria-label="Scène Omniverse Kit en direct"
      >
        <div className="viewer-stage">
          <div className="viewer-titlebar">
            <div>
              <span
                className={`signal-dot ${connectionTone}`}
                aria-hidden="true"
              />
              <strong>
                {run?.name ||
                  configuredSimulation?.name ||
                  "Viewport Omniverse"}
              </strong>
              <small>
                {isSceneObserved ? runLabel : "Aucune scène observée"}
              </small>
            </div>
            <span className="viewer-path" title={activeStage || undefined}>
              {compactPath(activeStage, "Aucun stage chargé")}
            </span>
          </div>
          <div
            ref={viewportFrameRef}
            className="viewport-frame"
            data-viewport-focus-guard="active"
            onPointerEnter={() => setViewportInputActive(true)}
            onPointerLeave={() => setViewportInputActive(false)}
          >
            <video
              id="remote-video"
              className="remote-video"
              autoPlay
              playsInline
              tabIndex={0}
              aria-label="Flux vidéo interactif de la scène Omniverse"
              aria-describedby="viewport-instructions"
              onFocus={() => setViewportInputActive(true)}
              onBlur={() => setViewportInputActive(false)}
              onLoadedData={markVideoFrameReady}
              onCanPlay={markVideoFrameReady}
              onPlaying={markVideoFrameReady}
            />
            {!hasVideoFrame && (
              <div className="viewport-overlay">
                <div className="viewport-glyph">
                  <Icon name="offline" />
                </div>
                <h2>{viewportState}</h2>
                <p>
                  {!hostReady
                    ? "Ouvrez OmniStream depuis le plugin Codex installé sur ce poste. Aucune connexion au runtime n’est disponible dans cette page seule."
                    : hostError
                      ? hostError
                      : runtime.processAlive
                        ? "Kit est actif. Le contrôle de scène et la vidéo ont des connexions distinctes : rattachez le flux depuis Session Kit."
                        : "Choisissez votre fichier USD et un runtime Kit compatible. Le rendu sera transmis directement depuis Omniverse."}
                </p>
                <div className="button-row">
                  <button
                    className="primary"
                    onClick={() =>
                      navigate(runtime.processAlive ? "launch" : "configure")
                    }
                  >
                    <Icon name="settings" />
                    {runtime.processAlive
                      ? "Ouvrir la session"
                      : "Configurer le runtime"}
                  </button>
                  <button
                    disabled={busy}
                    onClick={() => void superviseSimulation()}
                  >
                    <Icon name="refresh" />
                    Vérifier la connexion
                  </button>
                </div>
                <small>
                  Rendu Omniverse uniquement · Aucune scène préchargée
                </small>
              </div>
            )}
            <div
              className="viewport-corner viewport-corner-top"
              aria-hidden="true"
            />
            <div
              className="viewport-corner viewport-corner-bottom"
              aria-hidden="true"
            />
            {hasVideoFrame && <span className="live-badge">RTX LIVE</span>}
          </div>
        </div>

        <div
          className="viewer-transport"
          aria-label="Commandes rapides de lecture"
        >
          <div className="button-row">
            <button
              disabled={busy || !isSceneObserved}
              aria-label="Lecture"
              title="Lire la scène ouverte"
              onClick={() => void controlSimulation("play")}
            >
              <Icon name="play" />
            </button>
            <button
              disabled={busy || !isSceneObserved}
              aria-label="Pause"
              onClick={() => void controlSimulation("pause")}
            >
              <Icon name="pause" />
            </button>
            <button
              disabled={busy || !isSceneObserved}
              aria-label="Arrêter la lecture"
              onClick={() => void controlSimulation("stop")}
            >
              <Icon name="stop" />
            </button>
            <span className="transport-time">
              {typeof currentTime === "number"
                ? `${currentTime.toFixed(3)} s`
                : "Temps non reçu"}
            </span>
          </div>
          <div className="button-row">
            <span className="viewport-origin">
              {hasVideoFrame ? "Vidéo reçue de Kit" : "Aucune vidéo reçue"}
            </span>
            <button
              aria-label="Agrandir le viewport"
              title="Agrandir le viewport"
              onClick={() => {
                const el = viewportFrameRef.current;
                if (el?.requestFullscreen)
                  void el
                    .requestFullscreen()
                    .catch(() =>
                      report("Le plein écran est refusé par l’hôte.", "error"),
                    );
                else
                  report(
                    "Le plein écran n’est pas proposé par cet hôte.",
                    "neutral",
                  );
              }}
            >
              <Icon name="expand" />
            </button>
          </div>
        </div>

        <div className="runtime-strip" aria-label="Télémétrie de simulation">
          <div className="runtime-cell">
            <span>Simulation</span>
            <strong>{observedState(timelineState || "unknown")}</strong>
          </div>
          <div className="runtime-cell">
            <span>Temps</span>
            <strong>
              {typeof currentTime === "number"
                ? `${currentTime.toFixed(2)} s`
                : "—"}
            </strong>
          </div>
          <div className="runtime-cell">
            <span>Cadence cible</span>
            <strong>
              {typeof currentRate === "number"
                ? `${currentRate.toFixed(2)}×`
                : "—"}
            </strong>
          </div>
          <div className="runtime-cell">
            <span>Boucle</span>
            <strong>
              {controlAvailable && typeof simulation.loop === "boolean"
                ? simulation.loop
                  ? "Activée"
                  : "Désactivée"
                : "—"}
            </strong>
          </div>
          <div className="runtime-cell runtime-cell-wide">
            <span>Caméra</span>
            <strong title={selectedCamera || undefined}>
              {compactPath(
                selectedCamera,
                controlAvailable
                  ? "Viewport / aucune caméra sélectionnée"
                  : "Non vérifiée",
              )}
            </strong>
          </div>
          <div className="runtime-cell">
            <span>Session</span>
            <strong>{run?.runId ? run.runId.slice(0, 8) : "—"}</strong>
          </div>
        </div>

        <LiveSceneStrip live={liveScene} />
        <div className="viewer-footer">
          <p id="viewport-instructions" className="viewport-help">
            Cliquez dans le viewport pour les contrôles natifs Kit. Les
            commandes déterministes restent disponibles dans l’onglet Contrôle.
          </p>
          <div
            className="notice-line"
            data-tone={noticeTone}
            aria-live="polite"
            aria-atomic="true"
          >
            <span className="notice-dot" aria-hidden="true" />
            <span>{status}</span>
          </div>
          {stats && <p className="stream-stats">{stats}</p>}
        </div>
      </section>

      <aside
        className="controls-panel"
        id="inspector-panel"
        aria-label="Poste de conduite OmniStream"
        aria-busy={busy}
        onFocusCapture={() => setViewportInputActive(false)}
        onPointerEnter={() => setViewportInputActive(false)}
      >
        <div className="controls-heading">
          <div>
            <h2>{tabInfo[activeTab][0]}</h2>
            <p>{tabInfo[activeTab][1]}</p>
          </div>
          <button
            className="icon-refresh"
            type="button"
            onClick={() => void superviseSimulation()}
            disabled={busy}
            aria-label="Actualiser la supervision"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M20 11a8 8 0 1 0 2 5.2M20 4v7h-7" />
            </svg>
          </button>
        </div>

        <div className="deck-body">
          {!hostReady && (
            <div className="connection-notice" role="status">
              <Icon name="info" />
              <div>
                <strong>Connexion Codex requise</strong>
                <p>
                  Les commandes du runtime restent désactivées tant que le pont
                  MCP n’est pas disponible.
                </p>
              </div>
            </div>
          )}
          {hostError && (
            <div className="scene-error" role="alert">
              {hostError}
            </div>
          )}
          <div hidden={activeTab !== "scene" && activeTab !== "debug"}>
            <SceneWorkbench
              call={sceneCall}
              live={liveScene}
              events={sceneEvents}
              available={controlAvailable}
              externalBusy={busyAction !== null}
              onBusyChange={setWorkbenchBusy}
              debug={activeTab === "debug"}
              report={(text, error) =>
                report(text, error ? "error" : "success")
              }
            />
          </div>
          {activeTab === "configure" && (
            <section className="deck-view" aria-labelledby="configure-title">
              <div className="view-heading">
                <div>
                  <span>01</span>
                  <h3 id="configure-title">Paramètres de session</h3>
                </div>
                <small>
                  {configurationCurrent
                    ? "Validée par le contrôleur"
                    : configuredSimulation
                      ? "Modifications non validées"
                      : "Brouillon"}
                </small>
              </div>
              <p className="view-intro">
                Définissez la scène, le contexte d’exécution et le comportement
                initial. Cette étape ne lance pas Kit et n’écrit pas le USD.
              </p>

              <div className="form-grid">
                <label htmlFor="simulation-name">Nom de simulation</label>
                <input
                  id="simulation-name"
                  value={simulationName}
                  onChange={(event) => setSimulationName(event.target.value)}

                  disabled={busy}
                />

                <label htmlFor="kit-root">Racine Kit</label>
                <input
                  id="kit-root"
                  aria-describedby="kit-root-help"
                  value={kitRoot}
                  onChange={(event) => setKitRoot(event.target.value)}

                  spellCheck={false}
                  disabled={busy || runtime.processAlive}
                />

                <p id="kit-root-help" className="field-help">
                  Racine détectée par l’installateur, ou chemin d’un Kit
                  installé sur ce poste.
                </p>
                <div className="field-row-heading">
                  <label htmlFor="workspace-root">Workspace USD autorisé</label>
                  <button
                    className="text-button"
                    type="button"
                    onClick={() => void discoverLocalAssets()}
                    disabled={busy}
                  >
                    Sources
                  </button>
                </div>
                <input
                  id="workspace-root"
                  value={workspaceRoot}
                  onChange={(event) => setWorkspaceRoot(event.target.value)}

                  spellCheck={false}
                  disabled={busy || runtime.processAlive}
                />

                <div className="field-row-heading">
                  <label htmlFor="stage-path">Stage USD</label>
                  <button
                    className="text-button"
                    type="button"
                    onClick={() => void findStages()}
                    disabled={busy || !workspaceRoot.trim()}
                  >
                    Scanner
                  </button>
                </div>
                <input
                  id="stage-path"
                  list="usd-stages"
                  value={stagePath}
                  onChange={(event) => setStagePath(event.target.value)}

                  spellCheck={false}
                  disabled={busy}
                />
                <datalist id="usd-stages">
                  {stages.map((item) => (
                    <option value={item} key={item} />
                  ))}
                </datalist>

                <label htmlFor="launch-camera">
                  Caméra initiale <em>optionnel</em>
                </label>
                <input
                  id="launch-camera"
                  value={launchCameraPath}
                  onChange={(event) => setLaunchCameraPath(event.target.value)}

                  spellCheck={false}
                  disabled={busy}
                />
              </div>

              {assetSources.length > 0 && (
                <div
                  className="source-strip"
                  aria-label="Sources d’assets locales"
                >
                  {assetSources.slice(0, 4).map((source) => (
                    <button
                      type="button"
                      key={source.path}
                      onClick={() => useAssetSource(source)}
                      disabled={busy}
                      title={source.path}
                    >
                      <strong>{source.label}</strong>
                      <span>
                        {source.stageCount}
                        {source.stageCapped ? "+" : ""} USD
                      </span>
                    </button>
                  ))}
                </div>
              )}

              <div className="config-numbers">
                <div>
                  <label htmlFor="initial-time">Temps initial</label>
                  <input
                    id="initial-time"
                    type="number"
                    min="0"
                    step="0.01"
                    value={initialTime}
                    onChange={(event) => setInitialTime(event.target.value)}
                    disabled={busy}
                  />
                </div>
                <div>
                  <label htmlFor="config-rate">Cadence cible ×</label>
                  <input
                    id="config-rate"
                    type="number"
                    min="0.05"
                    max="8"
                    step="0.05"
                    value={rateMultiplier}
                    onChange={(event) => setRateMultiplier(event.target.value)}
                    disabled={busy}
                  />
                </div>
              </div>

              <div className="toggle-stack">
                <ToggleControl
                  label="Boucle"
                  detail="Répéter la timeline pendant cette session"
                  checked={loopEnabled}
                  onChange={setLoopEnabled}
                  disabled={busy}
                />
                <ToggleControl
                  label="Chaque frame"
                  detail="Éviter le frame skipping pendant la lecture"
                  checked={playEveryFrame}
                  onChange={setPlayEveryFrame}
                  disabled={busy}
                />
                <ToggleControl
                  label="Auto-play"
                  detail="Démarrer la timeline une fois le stage prêt"
                  checked={autoPlay}
                  onChange={setAutoPlay}
                  disabled={busy}
                />
              </div>

              <button
                className="primary action-wide"
                type="button"
                onClick={() => void configureSimulation()}
                disabled={busy || !configurationReady}
              >
                Valider la configuration
              </button>
            </section>
          )}

          {activeTab === "launch" && (
            <section className="deck-view" aria-labelledby="launch-title">
              <div className="view-heading">
                <div>
                  <span>02</span>
                  <h3 id="launch-title">Lancement</h3>
                </div>
                <small>{runtime.processAlive ? "runtime actif" : "prêt"}</small>
              </div>
              <p className="view-intro">
                OmniStream lance Kit sans fenêtre native, charge le stage
                configuré, applique les paramètres de session puis connecte le
                viewport WebRTC.
              </p>

              <div className="launch-summary">
                <div>
                  <span>Simulation</span>
                  <strong>
                    {configuredSimulation?.name || simulationName || "—"}
                  </strong>
                </div>
                <div>
                  <span>Stage</span>
                  <strong title={stagePath}>{compactPath(stagePath)}</strong>
                </div>
                <div>
                  <span>Workspace</span>
                  <strong title={workspaceRoot}>
                    {compactPath(workspaceRoot)}
                  </strong>
                </div>
                <div>
                  <span>Démarrage</span>
                  <strong>
                    {autoPlay ? "Auto-play" : "En pause"} ·{" "}
                    {loopEnabled ? "Loop" : "1 passage"}
                  </strong>
                </div>
              </div>

              <div
                className="preflight-panel"
                data-ready={
                  preflight?.ready === true
                    ? "true"
                    : preflight
                      ? "false"
                      : "unknown"
                }
              >
                <div className="preflight-heading">
                  <div>
                    <span className="preflight-indicator" aria-hidden="true" />
                    <strong>Préflight</strong>
                    <small>
                      {preflight?.ready === true
                        ? "prêt"
                        : preflight
                          ? "bloqué"
                          : "à vérifier"}
                    </small>
                  </div>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => void preflightSimulation()}
                    disabled={busy || !configuredSimulation}
                  >
                    Vérifier
                  </button>
                </div>
                {preflight?.checks?.length ? (
                  <div className="preflight-list">
                    {preflight.checks.map((check) => (
                      <div
                        key={check.id}
                        data-ok={check.ok ? "true" : "false"}
                        title={check.detail}
                      >
                        <span aria-hidden="true">{check.ok ? "✓" : "!"}</span>
                        <strong>{check.label}</strong>
                        <small>{compactPath(check.detail, check.detail)}</small>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="preflight-empty">
                    Validez d’abord la configuration, puis vérifiez le runtime,
                    le stage, le bridge, l’UI et le port WebRTC.
                  </p>
                )}
              </div>

              <button
                className="launch-button"
                type="button"
                onClick={() => void launchSimulation()}
                disabled={busy || !configurationReady || runtime.processAlive}
              >
                <span className="launch-icon" aria-hidden="true">
                  ▶
                </span>
                <span>
                  <strong>Lancer la simulation</strong>
                  <small>Kit + USD + paramètres + WebRTC</small>
                </span>
              </button>

              {runtime.processAlive && (
                <div className="active-session-box">
                  <StatusPill
                    label="Kit"
                    value={
                      runtime.processOwnership === "owned" ? "ready" : "working"
                    }
                  />
                  <p>
                    Un runtime OmniStream est déjà actif. Utilisez
                    Superviser/Contrôler ou arrêtez la session avant un nouveau
                    lancement.
                  </p>
                  <div className="button-row">
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setActiveTab("monitor")}
                    >
                      Superviser
                    </button>
                    <button
                      type="button"
                      className="danger-quiet"
                      onClick={() => void stop()}
                      disabled={busy}
                    >
                      Arrêter Kit
                    </button>
                  </div>
                </div>
              )}

              <details className="advanced-block">
                <summary>Runtime avancé</summary>
                <p>
                  Démarrage du runtime seul, utile pour le diagnostic sans
                  lancer la simulation configurée.
                </p>
                <div className="button-row">
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => void start()}
                    disabled={
                      busy || !workspaceRoot.trim() || runtime.processAlive
                    }
                  >
                    Démarrer Kit seul
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() =>
                      void attachExistingRuntime(
                        runtime,
                        sessionFlowEpoch.current,
                      )
                    }
                    disabled={busy || !isManagedActiveRuntime(runtime)}
                  >
                    Rattacher le flux
                  </button>
                </div>
              </details>
            </section>
          )}

          {activeTab === "monitor" && (
            <section className="deck-view" aria-labelledby="monitor-title">
              <div className="view-heading">
                <div>
                  <span>03</span>
                  <h3 id="monitor-title">Supervision</h3>
                </div>
                <small>
                  {lastObservedAt
                    ? `Lu à ${new Date(lastObservedAt).toLocaleTimeString("fr-FR")}`
                    : "Non vérifié"}
                </small>
              </div>
              <p className="view-intro">
                État consolidé du runtime, du flux, du bridge et de la
                simulation. La vue est actualisée automatiquement pendant une
                session active.
              </p>

              <div className="health-grid">
                {[
                  [
                    "Runtime",
                    !observed
                      ? "unknown"
                      : health.runtime ||
                        (runtime.processAlive ? "ready" : "offline"),
                  ],
                  [
                    "WebRTC",
                    !observed ? "unknown" : hasVideoFrame ? "ready" : "offline",
                  ],
                  [
                    "Bridge",
                    !observed
                      ? "unknown"
                      : health.bridge ||
                        (runtime.controlBridgeConnected ? "ready" : "offline"),
                  ],
                  [
                    "Scène",
                    !observed ? "unknown" : isSceneObserved ? "ready" : "empty",
                  ],
                ].map(([label, value]) => (
                  <div key={label}>
                    <span>{label}</span>
                    <strong data-tone={healthTone(value)}>
                      {observedState(value)}
                    </strong>
                  </div>
                ))}
              </div>

              <div className="monitor-list">
                <div>
                  <span>Run ID</span>
                  <strong>{run?.runId || "—"}</strong>
                </div>
                <div>
                  <span>Processus</span>
                  <strong>
                    {runtime.processId ? `PID ${runtime.processId}` : "—"}
                  </strong>
                </div>
                <div>
                  <span>Cycle de vie</span>
                  <strong>
                    {observed ? runtime.lifecyclePhase || "—" : "—"}
                  </strong>
                </div>
                <div>
                  <span>Timeline</span>
                  <strong>{timelineState || "—"}</strong>
                </div>
                <div>
                  <span>Temps</span>
                  <strong>
                    {typeof currentTime === "number"
                      ? `${currentTime.toFixed(3)} s`
                      : "—"}
                  </strong>
                </div>
                <div>
                  <span>Cadence demandée</span>
                  <strong>
                    {typeof simulation.targetFramerate === "number"
                      ? simulation.targetFramerate.toFixed(1)
                      : "—"}
                  </strong>
                </div>
                <div>
                  <span>Politique de lecture</span>
                  <strong>
                    {controlAvailable &&
                    typeof simulation.playEveryFrame === "boolean"
                      ? simulation.playEveryFrame
                        ? "Chaque image"
                        : "Temps réel"
                      : "—"}
                  </strong>
                </div>
                <div>
                  <span>Stage</span>
                  <strong title={activeStage || undefined}>
                    {compactPath(activeStage)}
                  </strong>
                </div>
              </div>

              <div className="monitor-actions">
                <button
                  className="secondary"
                  type="button"
                  onClick={() => void superviseSimulation()}
                  disabled={busy}
                >
                  Actualiser l’état
                </button>
                <button
                  className="secondary"
                  type="button"
                  onClick={() => void readRuntimeLogs()}
                  disabled={busy}
                >
                  Lire les logs Kit
                </button>
              </div>

              {journal.length > 0 && (
                <details className="diagnostic-block" open>
                  <summary>
                    Journal de session <span>{journal.length}</span>
                  </summary>
                  <div className="event-journal">
                    {[...journal]
                      .reverse()
                      .slice(0, 12)
                      .map((entry) => (
                        <div key={entry.id} data-tone={entry.tone}>
                          <time>{entry.at}</time>
                          <span>{entry.message}</span>
                        </div>
                      ))}
                  </div>
                </details>
              )}

              {runtimeLogs && (
                <details className="diagnostic-block">
                  <summary>
                    Logs runtime{" "}
                    <span>
                      {runtimeLogs.runtimeActive
                        ? "session active"
                        : "aucune session"}
                    </span>
                  </summary>
                  {(["stderr", "stdout"] as const).map((kind) => {
                    const log = runtimeLogs.logs?.[kind];
                    if (!log) return null;
                    return (
                      <div className="log-tail" key={kind}>
                        <header>
                          <strong>{kind}</strong>
                          <span>{log.file || "—"}</span>
                        </header>
                        <pre>
                          {log.lines?.length
                            ? log.lines.join("\n")
                            : "Aucune ligne disponible."}
                        </pre>
                      </div>
                    );
                  })}
                </details>
              )}

              {supervision.simulationError && (
                <p className="monitor-error">{supervision.simulationError}</p>
              )}
            </section>
          )}

          {activeTab === "control" && (
            <section className="deck-view" aria-labelledby="control-title">
              <div className="view-heading">
                <div>
                  <span>04</span>
                  <h3 id="control-title">Contrôle</h3>
                </div>
                <small>{timelineState || "offline"}</small>
              </div>
              <p className="view-intro">
                Contrôlez la simulation active sans arrêter Kit. Les
                modifications de caméra restent temporaires jusqu’à une
                sauvegarde explicitement confirmée.
              </p>

              <div
                className="transport-main"
                aria-label="Transport de simulation"
              >
                <button
                  type="button"
                  onClick={() => void controlSimulation("step_back")}
                  disabled={busy || !controlAvailable}
                  aria-label="Reculer d'une frame"
                >
                  <Icon name="back" />
                </button>
                <button
                  type="button"
                  className="transport-primary"
                  aria-label={
                    timelineState === "playing"
                      ? "Mettre en pause"
                      : "Lire la scène"
                  }
                  onClick={() =>
                    void controlSimulation(
                      timelineState === "playing" ? "pause" : "play",
                    )
                  }
                  disabled={busy || !controlAvailable}
                >
                  <Icon name={timelineState === "playing" ? "pause" : "play"} />
                </button>
                <button
                  type="button"
                  onClick={() => void controlSimulation("stop")}
                  disabled={busy || !controlAvailable}
                  aria-label="Stop playback"
                >
                  <Icon name="stop" />
                </button>
                <button
                  type="button"
                  onClick={() => void controlSimulation("step_forward")}
                  disabled={busy || !controlAvailable}
                  aria-label="Avancer d'une frame"
                >
                  <Icon name="next" />
                </button>
                <button
                  type="button"
                  onClick={() => void controlSimulation("reset")}
                  disabled={busy || !controlAvailable}
                >
                  Reset
                </button>
              </div>

              <div className="scrub-readout">
                <span>
                  {typeof currentTime === "number"
                    ? currentTime.toFixed(3)
                    : "—"}{" "}
                  s
                </span>
                <strong>
                  {typeof currentRate === "number"
                    ? currentRate.toFixed(2)
                    : "—"}
                  ×
                </strong>
              </div>

              <div className="control-fields">
                <div>
                  <label htmlFor="seek-time">Temps cible (s)</label>
                  <div className="inline-control">
                    <input
                      id="seek-time"
                      type="number"
                      min="0"
                      step="0.01"
                      value={seekTime}
                      onChange={(event) => setSeekTime(event.target.value)}
                      disabled={busy || !controlAvailable}
                    />
                    <button
                      type="button"
                      onClick={() => void controlSimulation("seek")}
                      disabled={busy || !controlAvailable || !validSeek}
                    >
                      Go
                    </button>
                  </div>
                </div>
                <div>
                  <label htmlFor="rate-multiplier">Cadence cible ×</label>
                  <div className="inline-control">
                    <input
                      id="rate-multiplier"
                      type="number"
                      min="0.05"
                      max="8"
                      step="0.05"
                      value={rateMultiplier}
                      onChange={(event) =>
                        setRateMultiplier(event.target.value)
                      }
                      disabled={busy || !controlAvailable}
                    />
                    <button
                      type="button"
                      onClick={() => void controlSimulation("set_rate")}
                      disabled={busy || !controlAvailable || !validRate}
                    >
                      Set
                    </button>
                  </div>
                </div>
              </div>

              <ToggleControl
                label="Boucle"
                detail="Appliquée immédiatement à la simulation active"
                checked={simulation.loop ?? loopEnabled}
                onChange={(value) => {
                  setLoopEnabled(value);
                  void controlSimulation("set_loop", { loop: value });
                }}
                disabled={busy || !controlAvailable}
              />

              <details className="advanced-block" open>
                <summary>Caméra</summary>
                <div className="camera-picker">
                  <select
                    id="camera-path"
                    aria-label="Caméra existante"
                    value={selectedCamera}
                    onChange={(event) => void selectCamera(event.target.value)}
                    disabled={busy || !controlAvailable || cameras.length === 0}
                  >
                    <option value="">
                      {cameras.length
                        ? "Choisir une caméra"
                        : "Aucune caméra chargée"}
                    </option>
                    {cameras.map((camera) => (
                      <option key={camera.path} value={camera.path}>
                        {camera.label || camera.path}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => void listCameras()}
                    disabled={busy || !controlAvailable}
                  >
                    Lister
                  </button>
                </div>
                <div
                  className="camera-grid"
                  aria-label="Navigation temporaire de caméra"
                >
                  <button
                    type="button"
                    onClick={() =>
                      void navigateCamera({
                        mode: "orbit",
                        horizontal: -0.25,
                        vertical: 0,
                      })
                    }
                    disabled={busy || !controlAvailable}
                  >
                    Orbit ←
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void navigateCamera({
                        mode: "orbit",
                        horizontal: 0.25,
                        vertical: 0,
                      })
                    }
                    disabled={busy || !controlAvailable}
                  >
                    Orbit →
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void navigateCamera({
                        mode: "pan",
                        horizontal: -0.25,
                        vertical: 0,
                      })
                    }
                    disabled={busy || !controlAvailable}
                  >
                    Pan ←
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void navigateCamera({
                        mode: "pan",
                        horizontal: 0.25,
                        vertical: 0,
                      })
                    }
                    disabled={busy || !controlAvailable}
                  >
                    Pan →
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void navigateCamera({
                        mode: "pan",
                        horizontal: 0,
                        vertical: 0.25,
                      })
                    }
                    disabled={busy || !controlAvailable}
                  >
                    Pan ↑
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void navigateCamera({
                        mode: "pan",
                        horizontal: 0,
                        vertical: -0.25,
                      })
                    }
                    disabled={busy || !controlAvailable}
                  >
                    Pan ↓
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void navigateCamera({ mode: "dolly", amount: -0.5 })
                    }
                    disabled={busy || !controlAvailable}
                  >
                    Dolly +
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void navigateCamera({ mode: "dolly", amount: 0.5 })
                    }
                    disabled={busy || !controlAvailable}
                  >
                    Dolly −
                  </button>
                </div>
                <button
                  className="save-button"
                  type="button"
                  onClick={() => void saveCamera()}
                  disabled={busy || !controlAvailable || !selectedCamera}
                >
                  Sauvegarder explicitement la pose
                </button>
              </details>

              <details className="advanced-block">
                <summary>Stage & assets</summary>
                <div className="button-row">
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => void loadStage()}
                    disabled={busy || !controlAvailable || !stagePath.trim()}
                  >
                    Recharger le stage
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => void refreshSimulation()}
                    disabled={busy || !controlAvailable}
                  >
                    Relire l’état brut
                  </button>
                </div>
                {assets.length > 0 && (
                  <p className="advanced-note">
                    {assets.length} assets indexés dans le workspace actif.
                  </p>
                )}
              </details>
            </section>
          )}
        </div>

        <footer className="security-note">
          <span className="lock-mark" aria-hidden="true">
            ●
          </span>
          <span>
            OmniStream {runtime.pluginVersion || "1.0.0-rc3"} ·{" "}
            {runtime.runtimeChannel || "runtime local"} · workspace borné ·
            bridge loopback authentifié · aucun runtime NVIDIA redistribué.
          </span>
        </footer>
      </aside>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <ConfirmationProvider>
      <App />
    </ConfirmationProvider>
  </ErrorBoundary>,
);
