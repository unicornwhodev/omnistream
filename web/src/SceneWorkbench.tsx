import { useEffect, useRef, useState } from "react";
import { useConfirm } from "./Confirmation";
import { Icon } from "./Icon";
import "./scene.css";

type Data = Record<string, any>;
export type SceneCall = (
  name: string,
  args: Record<string, unknown>,
) => Promise<Data>;
const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function useLiveScene(call: SceneCall, enabled = true) {
  const callRef = useRef(call);
  callRef.current = call;
  const cursor = useRef(0);
  const cacheId = useRef<string>();
  const [live, setLive] = useState<Data>({ stale: true, events: [] });
  const [events, setEvents] = useState<Data[]>([]);
  useEffect(() => {
    if (!enabled) {
      setLive({ stale: true, events: [], latest: null });
      return;
    }
    let active = true;
    let timer: number;
    async function poll() {
      try {
        if (document.visibilityState === "visible") {
          const data = await callRef.current("read_omniverse_live_telemetry", {
            afterSequence: cursor.current,
            limit: 100,
          });
          if (!active) return;
          if (
            cacheId.current &&
            data.cacheId &&
            cacheId.current !== data.cacheId
          ) {
            cursor.current = 0;
            setEvents([]);
          }
          cursor.current = data.nextSequence || 0;
          cacheId.current = data.cacheId;
          setLive(data);
          const fresh = (data.events || []).filter(
            (e: Data) => e.kind !== "telemetry",
          );
          if (fresh.length) setEvents((old) => [...old, ...fresh].slice(-150));
        }
      } catch (e) {
        if (active)
          setLive((old) => ({ ...old, stale: true, error: message(e) }));
      } finally {
        if (active) timer = window.setTimeout(() => void poll(), 1000);
      }
    }
    void poll();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [enabled]);
  return { live, events };
}

export function LiveSceneStrip({ live }: { live: Data }) {
  const snapshot = live.latest || {};
  return (
    <section
      className="live-scene-strip"
      aria-label="Télémétrie de la scène ouverte"
    >
      <span className={live.stale ? "live-state stale" : "live-state"}>
        {live.stale
          ? "Télémétrie indisponible / ancienne"
          : "Télémétrie active"}
      </span>
      <span>
        Scène{" "}
        <strong>{snapshot.stageId ? snapshot.stageId.slice(0, 6) : "—"}</strong>
      </span>
      <span>
        Révision <strong>{snapshot.revision ?? "—"}</strong>
      </span>
      <span>
        Intervalle Kit{" "}
        <strong>
          {snapshot.kitUpdateMs == null ? "—" : `${snapshot.kitUpdateMs} ms`}
        </strong>
      </span>
      <span>
        Âge{" "}
        <strong>
          {live.ageMs === null || live.ageMs === undefined
            ? "—"
            : `${live.ageMs} ms`}
        </strong>
      </span>
    </section>
  );
}

type Props = {
  call: SceneCall;
  live: Data;
  events: Data[];
  debug?: boolean;
  available: boolean;
  externalBusy?: boolean;
  onBusyChange?: (busy: boolean) => void;
  report: (text: string, error?: boolean) => void;
};
function VectorInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number[];
  onChange: (v: number[]) => void;
}) {
  return (
    <fieldset className="vector-input">
      <legend>{label}</legend>
      <div>
        {value.map((v, i) => (
          <label key={i}>
            <span>{["X", "Y", "Z"][i]}</span>
            <input
              aria-label={`${label} ${["X", "Y", "Z"][i]}`}
              type="number"
              step="any"
              value={Number.isNaN(v) ? "" : v}
              onChange={(e) =>
                onChange(
                  value.map((n, j) => (j === i ? e.target.valueAsNumber : n)),
                )
              }
            />
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function SceneWorkbench({
  call,
  live,
  events,
  debug = false,
  available,
  externalBusy = false,
  onBusyChange,
  report,
}: Props) {
  const confirm = useConfirm();
  const [scene, setScene] = useState<Data | null>(null);
  const [prim, setPrim] = useState<Data | null>(null);
  const [selected, setSelected] = useState("");
  const [path, setPath] = useState("/");
  const [offset, setOffset] = useState(0);
  const [localBusy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const busy = localBusy || externalBusy || !available;
  const [error, setError] = useState("");
  const [operation, setOperation] = useState("rigid_body");
  const [preview, setPreview] = useState<Data | null>(null);
  const [diagnostics, setDiagnostics] = useState<Data | null>(null);
  const [mode, setMode] = useState("animation");
  const [duration, setDuration] = useState(60);
  const [mass, setMass] = useState<number>(Number.NaN);
  const [kinematic, setKinematic] = useState(false);
  const [collider, setCollider] = useState(true);
  const [translation, setTranslation] = useState([NaN, NaN, NaN]);
  const [rotation, setRotation] = useState([NaN, NaN, NaN]);
  const [scale, setScale] = useState([NaN, NaN, NaN]);
  const [keyText, setKeyText] = useState("");
  const [keyTime, setKeyTime] = useState("");
  const [fps, setFps] = useState<number>(NaN);
  const [end, setEnd] = useState<number>(NaN);
  const [start, setStart] = useState<number>(NaN);
  const [gravity, setGravity] = useState([NaN, NaN, NaN]);
  const [gravityMagnitude, setGravityMagnitude] = useState<number>(NaN);
  const [physicsPath, setPhysicsPath] = useState("");
  const [exportPath, setExportPath] = useState("");
  const [watchName, setWatchName] = useState("");
  const [search, setSearch] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const snapshot = live.latest || {};
  const currentStage = scene?.stageId;
  const staleScene = Boolean(
    scene &&
    snapshot.stageId &&
    (snapshot.stageId !== scene.stageId || snapshot.revision > scene.revision),
  );
  const [now, setNow] = useState(Date.now());
  const currentPreview =
    preview &&
    !staleScene &&
    preview.revision === scene?.revision &&
    now < preview.expiresAt;
  useEffect(() => {
    if (!preview) return;
    const t = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(t);
  }, [preview]);
  useEffect(() => {
    if (!live.stale && scene && snapshot.stageId !== scene.stageId) {
      setScene(null);
      setPrim(null);
      setSelected("");
      setDiagnostics(null);
      setPreview(null);
      setConfirmed(false);
      setPath("/");
      setOffset(0);
    }
  }, [snapshot.stageId, scene?.stageId, live.stale]);
  useEffect(() => {
    onBusyChange?.(localBusy);
  }, [localBusy, onBusyChange]);
  useEffect(() => () => onBusyChange?.(false), [onBusyChange]);

  async function task(action: () => Promise<void>) {
    if (busy || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(message(e));
      report(message(e), true);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }
  async function inspect(parent = path, page = offset) {
    const data = await call("inspect_omniverse_scene", {
      parentPath: parent,
      offset: page,
      limit: 40,
    });
    if (scene?.stageId !== data.stageId) {
      setPrim(null);
      setSelected("");
      setDiagnostics(null);
    }
    setScene(data);
    setStart(data.startSeconds);
    setEnd(data.endSeconds);
    setFps(data.timeCodesPerSecond);
    setPath(parent);
    setOffset(page);
    setPreview(null);
    setConfirmed(false);
    return data;
  }
  async function choose(primPath: string) {
    if (!scene) return;
    const data = await call("inspect_omniverse_prim", {
      stageId: scene.stageId,
      primPath,
    });
    setSelected(primPath);
    setPrim(data);
    const attrs = data.attributes || [];
    const value = (name: string) =>
      attrs.find((a: Data) => a.name === name)?.value;
    setMass(
      typeof value("physics:mass") === "number" ? value("physics:mass") : NaN,
    );
    setKinematic(value("physics:kinematicEnabled") === true);
    setCollider(value("physics:collisionEnabled") === true);
    setTranslation(data.editableTrs?.translation || [NaN, NaN, NaN]);
    setRotation(data.editableTrs?.rotation || [NaN, NaN, NaN]);
    setScale(data.editableTrs?.scale || [NaN, NaN, NaN]);
    setKeyText("");
    setKeyTime("");
    setGravity(
      Array.isArray(value("physics:gravityDirection"))
        ? value("physics:gravityDirection")
        : [NaN, NaN, NaN],
    );
    setGravityMagnitude(
      typeof value("physics:gravityMagnitude") === "number"
        ? value("physics:gravityMagnitude")
        : NaN,
    );
    setPhysicsPath(data.type === "PhysicsScene" ? primPath : "");
    setWatchName("");
    setPreview(null);
    setConfirmed(false);
  }
  useEffect(() => {
    setPreview(null);
    setConfirmed(false);
  }, [
    selected,
    operation,
    mass,
    kinematic,
    collider,
    translation,
    rotation,
    scale,
    keyText,
    fps,
    start,
    end,
    gravity,
    gravityMagnitude,
    physicsPath,
  ]);

  function ops(): Data[] {
    if (operation === "physics_scene")
      return [
        {
          op: operation,
          primPath: physicsPath,
          gravityDirection: gravity,
          gravityMagnitude,
        },
      ];
    if (operation === "playback_range")
      return [
        {
          op: operation,
          startSeconds: start,
          endSeconds: end,
          framesPerSecond: fps,
        },
      ];
    if (!selected)
      throw new Error(
        "Sélectionnez un objet dans la scène avant de préparer cette modification.",
      );
    if (operation === "rigid_body")
      return [{ op: operation, primPath: selected, mass, kinematic, collider }];
    if (operation === "collider")
      return [{ op: operation, primPath: selected, enabled: collider }];
    if (operation === "transform")
      return [
        { op: operation, primPath: selected, translation, rotation, scale },
      ];
    if (operation === "animate_transform")
      return [{ op: operation, primPath: selected, keys: JSON.parse(keyText) }];
    throw new Error("Opération non reconnue");
  }

  return (
    <section
      className="scene-workbench"
      aria-label={debug ? "Diagnostic de scène" : "Atelier de scène"}
      aria-busy={busy}
    >
      <div className="scene-heading">
        <div>
          <h3>
            {debug
              ? "Observer & diagnostiquer"
              : "Travailler dans la scène ouverte"}
          </h3>
          <p>
            Sans rechargement. Corrections dans une couche de session séparée.
          </p>
        </div>
      </div>
      {!available && (
        <div className="connection-notice">
          <Icon name="info" />
          <div>
            <strong>Bridge de contrôle indisponible</strong>
            <p>
              Démarrez Kit et attendez sa connexion avant d’inspecter ou de
              modifier une scène.
            </p>
          </div>
        </div>
      )}
      <div className="scene-toolbar">
        <button
          disabled={busy}
          onClick={() =>
            void task(async () => {
              await inspect();
            })
          }
        >
          Inspecter la scène
        </button>
        <button
          disabled={busy || !scene}
          onClick={() =>
            void task(async () => {
              const d = await call("diagnose_omniverse_scene", {
                stageId: currentStage,
                maxPrims: 1000,
              });
              setDiagnostics(d);
            })
          }
        >
          Diagnostiquer
        </button>
      </div>
      {error && (
        <p className="scene-error" role="alert">
          {error}
        </p>
      )}
      {staleScene && (
        <p className="scene-warning">
          La scène a changé. Actualisez l’inspection avant de préparer ou
          appliquer une correction.
        </p>
      )}
      {!scene && (
        <div className="scene-empty">
          <strong>Votre scène reste dans Omniverse.</strong>
          <p>
            Après le démarrage du runtime, inspectez les objets pour configurer
            la physique, préparer une animation ou suivre ses paramètres.
          </p>
        </div>
      )}
      {scene && (
        <>
          <div className="scene-metadata">
            <span>
              Rév. <b>{scene.revision}</b>
            </span>
            <span>
              Axe vertical <b>{scene.upAxis}</b>
            </span>
            <span>
              1 unité = <b>{scene.metersPerUnit} m</b>
            </span>
            <span>
              PhysX{" "}
              <b>
                {scene.capabilities?.rigidBodySimulation
                  ? "disponible"
                  : "absent"}
              </b>
            </span>
          </div>
          <div className="scene-breadcrumb">
            <button
              disabled={busy || path === "/"}
              onClick={() =>
                void task(async () => {
                  await inspect(
                    path.split("/").slice(0, -1).join("/") || "/",
                    0,
                  );
                })
              }
            >
              Remonter
            </button>
            <code>{path}</code>
          </div>
          <div
            className="scene-tree"
            role="list"
            aria-label="Objets de la scène"
          >
            {scene.prims?.length ? (
              scene.prims.map((row: Data) => (
                <div
                  role="listitem"
                  key={row.path}
                  className={selected === row.path ? "selected" : ""}
                >
                  <button
                    onClick={() => void task(() => choose(row.path))}
                    disabled={busy}
                  >
                    <strong>{row.name}</strong>
                    <small>
                      {row.type || "Prim"}
                      {row.rigidBody ? " · corps rigide" : ""}
                      {row.collider ? " · collider" : ""}
                    </small>
                  </button>
                  {row.hasChildren && (
                    <button
                      aria-label={`Ouvrir ${row.path}`}
                      disabled={busy}
                      onClick={() =>
                        void task(async () => {
                          await inspect(row.path, 0);
                        })
                      }
                    >
                      Ouvrir
                    </button>
                  )}
                </div>
              ))
            ) : (
              <p>Aucun enfant direct dans ce prim.</p>
            )}
          </div>
          <div className="scene-pagination">
            <button
              disabled={busy || !offset}
              onClick={() =>
                void task(async () => {
                  await inspect(path, Math.max(0, offset - 40));
                })
              }
            >
              Précédents
            </button>
            <span>
              {scene.prims?.length
                ? `${offset + 1}–${offset + scene.prims.length}`
                : "0 objet"}
            </span>
            <button
              disabled={busy || scene.nextOffset === null}
              onClick={() =>
                void task(async () => {
                  await inspect(path, scene.nextOffset);
                })
              }
            >
              Suivants
            </button>
          </div>
        </>
      )}
      {prim && (
        <details className="scene-details">
          <summary>Inspecteur · {selected}</summary>
          <dl>
            {prim.attributes?.map((attr: Data) => (
              <div key={attr.name}>
                <dt>
                  {attr.name}
                  <small>
                    {attr.type} · {attr.timeSampleCount} clé(s)
                  </small>
                </dt>
                <dd>{JSON.stringify(attr.value)}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
      {!debug && scene && (
        <>
          <div className="scene-section">
            <h4>Configurer ou corriger</h4>
            <label>
              Opération
              <select
                value={operation}
                disabled={busy}
                onChange={(e) => setOperation(e.target.value)}
              >
                <option value="rigid_body">Corps rigide</option>
                <option value="collider">Collision de l’objet</option>
                <option value="physics_scene">Scène physique / gravité</option>
                <option value="transform">Transformation locale</option>
                <option value="animate_transform">
                  Animation par clés TRS
                </option>
                <option value="playback_range">Plage de lecture</option>
              </select>
            </label>
            {selected && (
              <p className="scene-target">
                Cible : <code>{selected}</code>
              </p>
            )}
            {operation === "rigid_body" && (
              <>
                <label>
                  Masse (unités de masse du stage)
                  <input
                    type="number"
                    min="0.000001"
                    step="any"
                    value={Number.isFinite(mass) ? mass : ""}
                    onChange={(e) => setMass(e.target.valueAsNumber)}
                  />
                </label>
                <label className="scene-check">
                  <input
                    type="checkbox"
                    checked={kinematic}
                    onChange={(e) => setKinematic(e.target.checked)}
                  />
                  Cinématique (mouvement animé, pas de chute libre)
                </label>
              </>
            )}
            {(operation === "rigid_body" || operation === "collider") && (
              <label className="scene-check">
                <input
                  type="checkbox"
                  checked={collider}
                  onChange={(e) => setCollider(e.target.checked)}
                />
                Activer le collider sur cette géométrie
              </label>
            )}
            {operation === "physics_scene" && (
              <>
                <label>
                  Chemin du prim PhysicsScene
                  <input
                    value={physicsPath}
                    onChange={(e) => setPhysicsPath(e.target.value)}
                  />
                </label>
                <VectorInput
                  label="Direction de gravité"
                  value={gravity}
                  onChange={setGravity}
                />
                <label>
                  Gravité (unités scène / s²)
                  <input
                    type="number"
                    step="any"
                    value={
                      Number.isFinite(gravityMagnitude) ? gravityMagnitude : ""
                    }
                    onChange={(e) =>
                      setGravityMagnitude(e.target.valueAsNumber)
                    }
                  />
                </label>
                <p className="scene-help">
                  Saisissez la gravité en unités du stage par seconde au carré.
                  Les valeurs existantes sont lues uniquement sur le prim
                  PhysicsScene sélectionné.
                </p>
              </>
            )}
            {operation === "transform" && (
              <>
                <VectorInput
                  label="Position locale"
                  value={translation}
                  onChange={setTranslation}
                />
                <VectorInput
                  label="Rotation XYZ (degrés)"
                  value={rotation}
                  onChange={setRotation}
                />
                <VectorInput
                  label="Échelle"
                  value={scale}
                  onChange={setScale}
                />
              </>
            )}
            {operation === "animate_transform" && (
              <>
                <p className="scene-help">
                  Aucune animation préremplie. Définissez vos clés ou capturez
                  la transformation de l’objet sélectionné.
                </p>
                <div className="scene-grid">
                  <label>
                    Temps de la nouvelle clé (s)
                    <input
                      type="number"
                      min="0"
                      step="any"
                      value={keyTime}
                      onChange={(e) => setKeyTime(e.target.value)}
                    />
                  </label>
                  <button
                    disabled={busy || !prim?.editableTrs || !keyTime.trim()}
                    onClick={() =>
                      void task(async () => {
                        const t = Number(keyTime);
                        if (!Number.isFinite(t) || t < 0)
                          throw new Error("Temps de clé invalide.");
                        const existing = keyText.trim()
                          ? JSON.parse(keyText)
                          : [];
                        if (
                          !Array.isArray(existing) ||
                          existing.length >= 120 ||
                          existing.some((k: Data) => k.timeSeconds === t)
                        )
                          throw new Error(
                            "Utilisez un temps distinct ; 120 clés maximum.",
                          );
                        const actual = await call("inspect_omniverse_prim", {
                          stageId: currentStage,
                          primPath: selected,
                        });
                        if (!actual.editableTrs)
                          throw new Error(
                            "La pile de transformations ne peut pas être capturée comme TRS simple.",
                          );
                        setKeyText(
                          JSON.stringify(
                            [
                              ...existing,
                              { timeSeconds: t, ...actual.editableTrs },
                            ].sort((a, b) => a.timeSeconds - b.timeSeconds),
                            null,
                            2,
                          ),
                        );
                      })
                    }
                  >
                    Capturer la pose actuelle
                  </button>
                </div>
                <label>
                  Clés TRS · secondes / degrés
                  <textarea
                    className="scene-code"
                    rows={12}
                    spellCheck={false}
                    value={keyText}
                    onChange={(e) => setKeyText(e.target.value)}
                  />
                </label>
                <p className="scene-help">
                  Chaque clé contient timeSeconds, translation, rotation et
                  scale. Deux clés au minimum ; temps strictement croissants.
                  L’aperçu affiche exactement les valeurs à appliquer. Un corps
                  animé doit être cinématique.
                </p>
              </>
            )}
            {operation === "playback_range" && (
              <div className="scene-grid">
                <label>
                  Début (secondes)
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={Number.isFinite(start) ? start : ""}
                    onChange={(e) => setStart(e.target.valueAsNumber)}
                  />
                </label>
                <label>
                  Fin (secondes)
                  <input
                    type="number"
                    min="0.01"
                    step="any"
                    value={Number.isFinite(end) ? end : ""}
                    onChange={(e) => setEnd(e.target.valueAsNumber)}
                  />
                </label>
                <label>
                  Images / seconde
                  <input
                    type="number"
                    min="1"
                    max="240"
                    value={Number.isFinite(fps) ? fps : ""}
                    onChange={(e) => setFps(e.target.valueAsNumber)}
                  />
                </label>
              </div>
            )}
            {scene.capabilities?.authoring !== true && (
              <p className="scene-warning">
                Cette scène est hors du workspace autorisé. Les corrections sont
                désactivées.
              </p>
            )}
            <p className="scene-help">
              Mettez la lecture en pause avant l’aperçu. Arrêtez la simulation
              pour les changements physiques. Aucun fichier source n’est
              enregistré.
            </p>
            <button
              className="scene-primary"
              disabled={
                busy || staleScene || scene.capabilities?.authoring !== true
              }
              onClick={() =>
                void task(async () => {
                  const data = await call("preview_omniverse_scene_patch", {
                    stageId: currentStage,
                    expectedRevision: scene.revision,
                    label: `${operation} · ${selected || physicsPath}`,
                    operations: ops(),
                  });
                  setPreview({
                    ...data,
                    expiresAt: Date.now() + data.expiresInSeconds * 1000,
                  });
                  setNow(Date.now());
                  setConfirmed(false);
                  report(
                    "Aperçu validé. Vérifiez les changements avant application.",
                  );
                })
              }
            >
              Préparer l’aperçu
            </button>
            {preview && (
              <div className="scene-preview">
                <h4>{preview.operationCount} modification(s) · aperçu</h4>
                <p className={currentPreview ? "scene-help" : "scene-warning"}>
                  {currentPreview
                    ? `Valide encore ${Math.max(0, Math.ceil((preview.expiresAt - now) / 1000))} s`
                    : "Aperçu expiré ou scène modifiée. Préparez un nouvel aperçu."}
                </p>
                {preview.warnings?.map((w: string) => (
                  <p className="scene-warning" key={w}>
                    {w}
                  </p>
                ))}
                <details>
                  <summary>Changements exacts</summary>
                  <pre>{JSON.stringify(preview.operations, null, 2)}</pre>
                </details>
                <label className="scene-check">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />
                  J’ai vérifié la cible et les changements.
                </label>
                <button
                  className="scene-primary"
                  disabled={busy || !confirmed || !currentPreview}
                  onClick={() =>
                    void task(async () => {
                      await call("apply_omniverse_scene_patch", {
                        stageId: currentStage,
                        expectedRevision: preview.revision,
                        previewId: preview.previewId,
                      });
                      await inspect();
                      report(
                        "Correction appliquée dans la session, sans modifier le USD source.",
                      );
                    })
                  }
                >
                  Appliquer à la scène
                </button>
              </div>
            )}
          </div>
          <div className="scene-section">
            <h4>Exécuter la scène actuelle</h4>
            <div className="scene-grid">
              <label>
                Mode
                <select value={mode} onChange={(e) => setMode(e.target.value)}>
                  <option value="animation">Animation / timeline</option>
                  <option
                    value="physics"
                    disabled={!scene.capabilities?.rigidBodySimulation}
                  >
                    Physique (PhysX)
                  </option>
                </select>
              </label>
              <label>
                Limite réelle (secondes)
                <input
                  type="number"
                  min="1"
                  max="3600"
                  value={Number.isFinite(duration) ? duration : ""}
                  onChange={(e) => setDuration(e.target.valueAsNumber)}
                />
              </label>
            </div>
            <p className="scene-help">
              Retour au début et boucle désactivée. Kit met en pause au délai
              limite. Le mode animation ne désactive pas une physique déjà
              présente.
            </p>
            <div className="scene-toolbar">
              <button
                className="scene-primary"
                disabled={
                  busy ||
                  staleScene ||
                  !Number.isFinite(duration) ||
                  duration < 1 ||
                  duration > 3600
                }
                onClick={() =>
                  void task(async () => {
                    await call("run_omniverse_scene", {
                      stageId: currentStage,
                      mode,
                      wallTimeLimitSeconds: duration,
                      resetToStart: true,
                    });
                    report("Exécution demandée sur la scène ouverte.");
                  })
                }
              >
                Exécuter
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  void task(async () => {
                    await call("control_omniverse_simulation", {
                      action: "pause",
                    });
                  })
                }
              >
                Pause
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  void task(async () => {
                    await call("control_omniverse_simulation", {
                      action: "stop",
                    });
                    await inspect();
                  })
                }
              >
                Stop
              </button>
            </div>
          </div>
          <details className="scene-details">
            <summary>Annuler / exporter les corrections</summary>
            <p>
              Arrêtez la simulation avant d’annuler. L’export produit une couche
              USD, pas une scène autonome.
            </p>
            <button
              disabled={busy || !scene.undoDepth || staleScene}
              onClick={() =>
                void task(async () => {
                  await call("undo_omniverse_scene_patch", {
                    stageId: currentStage,
                    expectedRevision: scene.revision,
                  });
                  await inspect();
                  report("Dernière correction annulée.");
                })
              }
            >
              Annuler la dernière correction
            </button>
            <label>
              Nouveau fichier .usda dans le workspace
              <input
                value={exportPath}
                onChange={(e) => setExportPath(e.target.value)}
              />
            </label>
            <button
              disabled={
                busy ||
                staleScene ||
                !scene.hasSessionEdits ||
                !exportPath.trim()
              }
              onClick={() =>
                void task(async () => {
                  if (
                    !(await confirm({
                      title: "Exporter les corrections",
                      message: `Créer le fichier ${exportPath} dans le workspace autorisé ? L’export contient des overrides, pas une scène autonome.`,
                      confirmLabel: "Créer le fichier",
                    }))
                  )
                    return;
                  const data = await call("export_omniverse_scene_patch", {
                    stageId: currentStage,
                    expectedRevision: scene.revision,
                    relativePath: exportPath,
                    confirm: true,
                  });
                  report(`Couche exportée : ${data.exported}`);
                })
              }
            >
              Exporter la couche (sans écrasement)
            </button>
            <button
              className="scene-danger"
              disabled={busy || staleScene || !scene.hasSessionEdits}
              onClick={() =>
                void task(async () => {
                  if (
                    !(await confirm({
                      title: "Abandonner les corrections",
                      message:
                        "Supprimer toutes les corrections de session OmniStream ? Cette action est irréversible ; les fichiers source restent intacts.",
                      destructive: true,
                      confirmLabel: "Abandonner",
                    }))
                  )
                    return;
                  await call("discard_omniverse_scene_edits", {
                    stageId: currentStage,
                    expectedRevision: scene.revision,
                    confirm: true,
                  });
                  await inspect();
                })
              }
            >
              Abandonner les corrections
            </button>
          </details>
        </>
      )}
      {diagnostics && (
        <div className="scene-section">
          <h4>Diagnostic structurel</h4>
          {(live.stale ||
            snapshot.revision !== diagnostics.revision ||
            snapshot.stageId !== diagnostics.stageId) && (
            <p className="scene-warning">
              Diagnostic conservé, mais non confirmé pour l’état actuel.
              Relancez l’inspection avant de conclure.
            </p>
          )}
          <p>
            {diagnostics.counts?.prims} objets examinés ·{" "}
            {diagnostics.counts?.rigidBodies} corps rigides ·{" "}
            {diagnostics.counts?.animatedPrims} objets animés
          </p>
          {diagnostics.scanCapped && (
            <p className="scene-warning">
              Inspection partielle : limite atteinte.
            </p>
          )}
          {diagnostics.issues?.length ? (
            diagnostics.issues.map((issue: Data, i: number) => (
              <div key={i} className={`scene-issue ${issue.severity}`}>
                <strong>{issue.code}</strong>
                <code>{issue.primPath}</code>
                <p>{issue.message}</p>
              </div>
            ))
          ) : (
            <p>
              Aucune anomalie détectée dans le périmètre inspecté. Ce n’est pas
              une validation du solveur.
            </p>
          )}
        </div>
      )}
      {debug && (
        <>
          <div className="scene-section">
            <h4>Paramètres surveillés</h4>
            <p>
              Échantillonnage Kit : 4 Hz. Lecture de ce panneau : 1 Hz,
              suspendue lorsqu’il est masqué.
            </p>
            <label>
              Attribut de l’objet sélectionné
              <input
                value={watchName}
                onChange={(e) => setWatchName(e.target.value)}
                list="watch-attributes"
              />
              <datalist id="watch-attributes">
                {prim?.attributes
                  ?.filter((a: Data) => !a.type?.endsWith("[]"))
                  .map((a: Data) => (
                    <option key={a.name} value={a.name} />
                  ))}
              </datalist>
            </label>
            <div className="scene-toolbar">
              <button
                disabled={
                  busy || !selected || !scene || !watchName.trim() || live.stale
                }
                onClick={() =>
                  void task(async () => {
                    const properties = [
                      ...(snapshot.watches || []).map((w: Data) => ({
                        primPath: w.primPath,
                        attribute: w.attribute,
                      })),
                      { primPath: selected, attribute: watchName },
                    ];
                    const unique = properties.filter(
                      (p: Data, i: number) =>
                        properties.findIndex(
                          (other: Data) =>
                            other.primPath === p.primPath &&
                            other.attribute === p.attribute,
                        ) === i,
                    );
                    if (unique.length > 16)
                      throw new Error(
                        "La surveillance est limitée à 16 attributs.",
                      );
                    await call("configure_omniverse_scene_watch", {
                      stageId: currentStage,
                      properties: unique,
                      pauseOnNonFinite: true,
                    });
                    report(
                      "Surveillance activée avec pause sur valeur non finie.",
                    );
                  })
                }
              >
                Surveiller cet attribut
              </button>
              <button
                disabled={busy || !scene}
                onClick={() =>
                  void task(async () => {
                    await call("configure_omniverse_scene_watch", {
                      stageId: currentStage,
                      properties: [],
                    });
                  })
                }
              >
                Vider
              </button>
            </div>
            <div className="watch-values">
              {snapshot.watches?.length ? (
                snapshot.watches.map((w: Data, i: number) => (
                  <div key={i}>
                    <code>
                      {w.primPath}
                      <br />
                      {w.attribute}
                    </code>
                    <strong>
                      {w.available === false
                        ? "Indisponible"
                        : JSON.stringify(w.value)}
                      {live.stale ? " · valeur ancienne" : ""}
                    </strong>
                  </div>
                ))
              ) : (
                <p>Aucun attribut suivi.</p>
              )}
            </div>
            <p className="scene-help">
              Les valeurs sont celles du USD. Un solveur écrivant uniquement
              dans Fabric peut ne pas les actualiser.
            </p>
          </div>
          <div className="scene-section">
            <h4>Journal du bridge et de Kit</h4>
            <label>
              Filtrer les événements
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                aria-label="Rechercher dans les événements reçus"
              />
            </label>
            {live.cursorGap && (
              <p className="scene-warning">
                Des événements plus anciens ont quitté le tampon borné.
              </p>
            )}
            <div
              className="scene-log"
              role="log"
              aria-label="Événements récents"
            >
              {events
                .filter((e) =>
                  JSON.stringify(e)
                    .toLowerCase()
                    .includes(search.toLowerCase()),
                )
                .slice(-80)
                .map((e) => (
                  <div key={e.sequence}>
                    <time>
                      {new Date(e.atUnixMs).toLocaleTimeString("fr-FR", {
                        hour12: false,
                      })}
                    </time>
                    <strong>{e.kind}</strong>
                    <span>{e.data.message || JSON.stringify(e.data)}</span>
                  </div>
                ))}
              {!events.length && <p>Aucun événement reçu du runtime.</p>}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
