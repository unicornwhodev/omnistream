import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

const webRoot = resolve(import.meta.dirname, "..");
const pluginRoot = resolve(webRoot, "..");
// Normalize layout whitespace only; source contracts are not substitutes for a built-bundle check.
const source = readFileSync(resolve(webRoot, "src", "main.tsx"), "utf8").replace(/\s+/g, " ");
const css = readFileSync(resolve(webRoot, "src", "index.css"), "utf8").replace(/\s+/g, " ");
const bundlePath = resolve(pluginRoot, "mcp", "web-dist", "assets", "omniverse-panel.js");
const attachSource = source.slice(source.indexOf("const attachExistingRuntime"), source.indexOf("const loadStage"));
const invalidateSource = source.slice(source.indexOf("const invalidateStream"), source.indexOf("const startRuntimeWatchdog"));

const sourceOnly = process.argv.includes("--source-only");
if (!sourceOnly) assert.ok(existsSync(bundlePath), "Le bundle servi est absent. Exécutez npm run test:web depuis la racine du plugin.");
const bundle = sourceOnly ? null : readFileSync(bundlePath, "utf8");
const matchBundle = (pattern, message) => { if (bundle !== null) assert.match(bundle, pattern, message); };
const rejectBundle = (pattern, message) => { if (bundle !== null) assert.doesNotMatch(bundle, pattern, message); };

for (const tool of [
  "configure_omniverse_simulation",
  "launch_omniverse_simulation",
  "supervise_omniverse_simulation",
  "control_omniverse_simulation",
  "attach_omniverse_stream",
  "load_omniverse_stage",
  "get_omniverse_simulation_state",
  "list_omniverse_cameras",
  "select_omniverse_camera",
  "navigate_omniverse_camera",
  "save_omniverse_camera"
]) {
  assert.match(source, new RegExp(tool), `Le source doit appeler ${tool}.`);
  matchBundle(new RegExp(tool), `Le bundle servi doit appeler ${tool}.`);
}


assert.match(source, /Navigation du studio/, "Le panneau doit présenter le poste de conduite de simulation.");
for (const phase of ["Configurer", "Lancer", "Superviser", "Contrôler"]) {
  assert.match(source, new RegExp(phase), `Le panneau doit exposer la phase ${phase}.`);
  matchBundle(new RegExp(phase), `Le bundle servi doit exposer la phase ${phase}.`);
}
assert.match(source, /superviseSimulation\(false\)/, "Le panneau doit rafraîchir la supervision sans bruit utilisateur.");
assert.match(source, /setInterval\([\s\S]*?superviseSimulation\(false\)/, "Une session active doit être supervisée périodiquement.");
assert.match(css, /\.deck-tabs/, "Les outils du studio doivent avoir une navigation dédiée.");
assert.match(css, /\.health-grid/, "La supervision doit avoir une grille de santé lisible.");
assert.match(css, /\.transport-main/, "Le contrôle doit avoir un transport de simulation dédié.");

assert.match(source, /toolResponseMetadata/, "Le panneau doit prioriser les métadonnées canoniques du widget.");
assert.match(source, /metadataFromEnvelope/, "Le panneau doit accepter les enveloppes host de métadonnées.");
assert.match(source, /installViewportFocusGuard/, "Le focus du viewport doit être restauré après le SDK.");
assert.match(source, /attributeFilter: \["tabindex", "style"\]/, "Un MutationObserver doit réparer les mutations SDK du viewport.");
assert.match(source, /viewportRoot\.addEventListener\(\s*"keydown",\s*allowStandardTab,\s*\{\s*capture: true,?\s*\},?\s*\)/, "Le Tab doit être gardé au niveau capture du viewport uniquement.");
assert.match(source, /if \(event\.key === "Tab"\) event\.stopPropagation\(\);/, "Le Tab doit éviter le handler SDK sans empêcher sa navigation native.");
assert.doesNotMatch(source, /document\.addEventListener\("keydown"/, "Le panneau ne doit pas installer de raccourci clavier global.");
assert.match(source, /data-viewport-focus-guard="active"/, "Le viewport doit être marqué comme surface à focus restauré.");
assert.match(source, /mode: "dolly"; amount: number/, "Le déplacement dolly doit avoir un contrat distinct.");
assert.match(source, /mode: "orbit" \| "pan"; horizontal: number; vertical: number/, "Orbit et pan doivent porter uniquement leurs deux deltas.");
assert.doesNotMatch(source, /navigateCamera\("orbit"/, "Les boutons ne doivent plus appeler le contrat caméra historique.");
assert.match(source, /toolResponseMetadata/, "Le bearer doit lire les métadonnées widget canoniques.");
assert.match(source, /const response = await callHostTool\(TOOL_NAMES\.attachStream, \{\}\);/, "Le panneau doit demander un bearer privé pour le runtime Kit déjà géré.");
assert.match(attachSource, /const meta = privateWidgetMetadata\(\);[\s\S]*?meta\["omnistream\/streamAccessToken"\]/, "Le bearer de reattach doit venir uniquement des métadonnées privées canoniques.");
assert.doesNotMatch(attachSource, /responseMeta\(response\)/, "Le reattach ne doit jamais accepter le bearer depuis l'enveloppe d'outil publique.");
assert.match(source, /function isManagedActiveRuntime\(runtime: RuntimeStatus\)[\s\S]*?processOwnership === "owned"[\s\S]*?streamListening === true[\s\S]*?controlBridgeConnected === true/, "Le reattach doit rester borné à une session Kit gérée, vivante et complètement prête.");
assert.match(source, /const initialFlowEpoch = sessionFlowEpoch\.current;[\s\S]*?const current = await refreshRuntime\(false\);[\s\S]*?await attachExistingRuntime\(current, initialFlowEpoch\);/, "Le reattach doit suivre le premier statut lu au montage.");
assert.match(source, /sessionFlowEpoch\.current !== flowEpoch/, "Une action Start ou Stop doit invalider un reattach tardif.");
assert.match(source, /connectInFlight\.current/, "Le panneau doit sérialiser les tentatives AppStreamer concurrentes.");
assert.match(source, /pendingSdkConnect\.current/, "Une négociation SDK non réglée doit rester une barrière distincte.");
assert.match(source, /pendingSdkRetirement\.current/, "Une terminaison SDK en cours doit empêcher une nouvelle instance AppStreamer.");
assert.match(source, /while \(candidate\.streamStatus === StreamStatus\.STARTING\)/, "Le panneau doit attendre la sortie de STARTING avant de libérer une négociation SDK annulée.");
assert.doesNotMatch(invalidateSource, /connectInFlight\.current = null/, "L'invalidation ne doit pas libérer une négociation SDK encore en cours.");
assert.match(source, /const APP_STREAM_PENDING_NEGOTIATION_ERROR = "La négociation WebRTC précédente se ferme encore dans le SDK/, "Un Start ou reattach concurrent doit recevoir une erreur de nettoyage actionnable.");
assert.match(source, /const KIT_READY_TIMEOUT_MS = 120_000;/, "Le panneau doit tolérer un démarrage Kit à froid borné.");
assert.match(source, /const APP_STREAM_CONNECT_TIMEOUT_MS = 75_000;/, "La promesse AppStreamer.connect doit avoir une borne propre au panneau.");
assert.match(source, /const APP_STREAM_CONNECT_TIMEOUT_ERROR = "La connexion WebRTC locale a dépassé le délai du panneau/, "Le timeout SDK doit exposer un message terminal stable et actionnable.");
assert.match(source, /Promise\.race\(\[sdkConnection, timeout\]\)/, "Le timeout doit réellement borner AppStreamer.connect plutôt que seulement son état visuel.");
assert.match(source, /if \(hasPendingSdkNegotiation\(\)\) throw new Error\(APP_STREAM_PENDING_NEGOTIATION_ERROR\);/, "Start et reattach doivent refuser une nouvelle connexion tant que le SDK termine la précédente.");
assert.match(source, /return \(\) => \{[\s\S]*?sessionFlowEpoch\.current \+= 1;/, "Le démontage React doit invalider un reattach tardif.");
assert.match(source, /current\.processAlive && current\.streamListening && current\.controlBridgeConnected/, "Le flux ne doit être connecté qu'après la disponibilité WebRTC et du bridge.");
assert.match(source, /EventStatus\.WARNING/, "Les tentatives WebRTC intermédiaires doivent garder un état de connexion explicite.");
assert.match(source, /streamEpoch\.current/, "Les callbacks d'une tentative WebRTC obsolète doivent être ignorés.");
assert.match(source, /videoFrameSeen\.current/, "L’état hors ligne doit dépendre d'une vraie frame vidéo reçue.");
assert.match(source, /const DEFAULT_WORKSPACE = "";/, "Le dépôt public ne doit pas préremplir un chemin de workspace personnel.");
assert.match(source, /value=\{kitRoot\}/, "Le panneau doit permettre un Kit root portable sans chemin machine intégré.");
assert.match(source, /kitRoot: kitRoot\.trim\(\)/, "Le Kit root saisi dans le panneau doit être transmis au démarrage.");
assert.match(source, /onLoadedData=\{markVideoFrameReady\}/, "Le viewport doit confirmer les données vidéo décodées.");
assert.match(source, /!hasVideoFrame && \(/, "L’état hors ligne ne doit rester visible qu'avant la première frame vidéo.");
assert.match(source, /startRuntimeWatchdog/, "Le panneau doit détecter l'arrêt externe du runtime Kit.");
assert.match(source, /Le runtime Kit a été arrêté hors de ce panneau/, "L'arrêt externe doit être rendu visible au lieu de laisser une connexion bloquée.");
assert.match(source, /current\.processAlive && current\.controlBridgeConnected/, "Les commandes de simulation doivent attendre le bridge authentifié.");
assert.match(source, /aria-live="polite"/, "Les mises à jour d'état doivent être annoncées.");
assert.match(source, /aria-describedby="viewport-instructions"/, "Le viewport doit décrire son interaction clavier.");
assert.match(source, /discover_omniverse_local_assets/, "Le panneau doit découvrir les racines d’assets locales sans requête distante.");
assert.match(source, /Sources d’assets locales/, "Le panneau doit présenter les racines d’assets locales détectées.");
assert.match(source, /await confirm\(\{ title: "Enregistrer la caméra"/, "La persistance caméra doit rester explicite.");
assert.match(css, /button:focus-visible/, "Tous les boutons doivent avoir un focus visible.");
assert.match(css, /\.remote-video:focus-visible[\s\S]*!important/, "Le focus visible doit surpasser l'outline inline du SDK.");
assert.match(css, /\.remote-video[\s\S]*object-fit: contain/, "Le viewport conserve son ratio sans recadrage.");
assert.match(css, /\.viewport-frame[\s\S]*aspect-ratio: 16 \/ 9/, "Le catalogue d'assets ne doit pas étirer verticalement le viewport.");
assert.match(css, /\.remote-video[\s\S]*position: absolute[\s\S]*inset: 0/, "La vidéo doit remplir le cadre 16:9 stable.");
assert.match(css, /\.asset-source-list/, "La liste des bibliothèques détectées doit recevoir un style lisible.");

matchBundle(/setViewportInputActive/, "Le bundle servi doit contenir le garde d'entrée viewport.");
matchBundle(/attach_omniverse_stream/, "Le bundle servi doit pouvoir reattach le runtime Kit déjà géré.");
matchBundle(/toolResponseMetadata/, "Le bundle servi doit lire les métadonnées widget canoniques.");
matchBundle(/data-viewport-focus-guard/, "Le bundle servi doit contenir la surface focusable du viewport.");
matchBundle(/"Tab"/, "Le bundle servi doit contenir le garde Tab scoped.");
matchBundle(/tabIndex/, "Le bundle servi doit restaurer la tabulation du viewport.");
matchBundle(/Le runtime Kit a été arrêté hors de ce panneau/, "Le bundle servi doit rendre visible l'arrêt externe du runtime.");
matchBundle(/La connexion WebRTC locale a dépassé le délai du panneau/, "Le bundle servi doit rendre le timeout de connexion actionnable.");
matchBundle(/La négociation WebRTC précédente se ferme encore dans le SDK/, "Le bundle servi doit empêcher une seconde connexion pendant le nettoyage SDK.");
matchBundle(/Sources d’assets locales/, "Le bundle servi doit présenter les assets locaux détectés.");
rejectBundle(/OV_WEB_RTC_DEV/, "Le bundle servi ne doit pas embarquer le raccourci de développement Ctrl+Shift+A.");
rejectBundle(/shiftKey&&[^;]{0,80}ctrlKey&&[^;]{0,120}toLowerCase\(\)/, "Le bundle servi ne doit pas contenir le gestionnaire Ctrl+Shift+A du SDK.");

process.stdout.write(sourceOnly ? "Panel source contracts passed. Production bundle was NOT checked in --source-only mode.\n" : "Contrat source et bundle du panneau Omniverse vérifié.\n");
