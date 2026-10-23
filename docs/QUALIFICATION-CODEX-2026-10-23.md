# Correctifs d’ouverture et de hauteur Codex — 23 octobre 2026

## État de la qualification

Les corrections source, le protocole MCP et le bundle construit sont vérifiés.
Le nouveau panneau termine son initialisation MCP Apps dans le vrai hôte Codex :
configuration, scan, préflight et lancement de Kit ont été effectués depuis
son interface. Le bridge, la scène et la télémétrie répondent. La vidéo échoue
pendant cet essai et aucune capture du rendu Kit dans Codex n’est validée.
La qualification complète reste donc **partielle**.

La régression de hauteur est reproduite avant correction et ne se reproduit
plus après correction aux trois largeurs mesurées dans la reproduction locale.
Un second défaut d’initialisation MCP Apps est corrigé avec le SDK officiel.

Ce rapport complète la [qualification locale du 21 octobre](QUALIFICATION-LOCAL-2026-10-21.md).
Les résultats Chrome/Kit antérieurs restent attachés à leur environnement.
La version produit reste `1.0.0-rc4`.

Le [reçu expurgé](evidence/codex-2026-10-23/receipt.json) contient les cinq
séries de mesures, les hashes du bundle et des journaux, et les indicateurs de
qualification de l’hôte. Syntaxe/TypeScript, 102 tests Node (un skip de privilège
symlink Windows), construction et contrats du panneau passent. Le protocole de
la copie installée passe aussi. Les tests OpenUSD/PhysX du 21 octobre ne sont
pas réattribués à ce correctif de schéma et de mise en page.

## Défauts et corrections

### Catalogue MCP refusé

Le journal de l’hôte refuse le schéma de `navigate_omniverse_camera` : la racine
ne déclare pas `type: "object"`. Ses deux branches `oneOf` le déclarent, mais
cela ne satisfait pas le validateur du catalogue Codex. Un seul outil invalide
peut empêcher l’admission de l’application.

La racine déclare désormais son type. Le test de protocole impose cette
déclaration à chaque outil, plutôt que d’accepter la seule présence de `oneOf`.
Le test échoue sur l’ancien schéma, puis passe après correction, également
depuis la copie installée du plugin.

### Hauteur qui augmente sans fin

Le bandeau de choix local/distant précède un studio dont la hauteur minimale
était `100dvh`. Sur grand écran, sa hauteur était aussi fixée à `100dvh`.
Dans un hôte qui adapte l’iframe à la hauteur intrinsèque du contenu, cela donne
la relation `hauteur suivante = hauteur actuelle + hauteur du bandeau`.
La barre d’outils intermédiaire utilisait également la hauteur du viewport.

Le document et le studio ont maintenant une hauteur intrinsèque déterminée
par leur contenu. Ces dépendances au viewport sont supprimées ; le mode plein
écran de la vidéo conserve ses dimensions de fenêtre. Un garde source refuse
le retour d’unités de hauteur de viewport hors de ce plein écran.

Le même bundle est chargé dans une iframe locale sans contrôleur et sans
vidéo. Huit passes adaptent sa hauteur à celle du contenu, à largeur constante :

| Largeur | Avant | Après |
|---|---|---|
| 1 440 px | 656 → 1 053 px, croissance à chaque passe | 1 358 px, stable |
| 900 px | 2 153 → 2 550 px, croissance à chaque passe | 2 153 px, stable |
| 390 px | Non mesuré avant | 2 152 puis 2 113 px, stable à partir de la troisième mesure |

Ces valeurs décrivent une reproduction locale de la boucle de mise en page,
pas la hauteur mesurée dans Codex. Le studio reste une interface longue aux
petites largeurs ; il n’est pas réduit à une carte de résumé.

### Ressource et accès au panneau

La ressource est renouvelée en
`ui://omnistream-for-codex/panel-rc4-layout.html` pour distinguer le bundle
corrigé des anciennes cartes mises en cache. L’outil d’ouverture déclare
`"openai/ui": { "entrypoints": [{ "type": "thread" }] }` pour proposer un accès
direct dans le panneau latéral de la conversation, selon le
[contrat officiel des extensions Codex](https://developers.openai.com/plugins/build/extensions#sidebar-apps).
Le protocole teste l’identifiant et cet accès.

Après mise à jour, reconstruire le panneau, recharger le contrôleur MCP et
ouvrir une nouvelle instance du studio. Une carte déjà ouverte garde son
ancien document. Le guide [setup et utilisation](LOCAL-SETUP.md) décrit les
étapes locales et les précautions sur les scènes.

## Observation dans Codex et limites

### Initialisation MCP Apps manquante

Après rechargement, Codex détecte le panneau, mais une capture échoue puis sa
cible devient inaccessible. L’opérateur observe que son contenu devient vide.
Les journaux de l’hôte contiennent `MCP app initialization timed out` et un échec
d’initialisation de la sandbox OmniStream. Le source utilisait directement
`window.openai.callTool` sans effectuer le handshake `ui/initialize`.

Le panneau utilise désormais `@modelcontextprotocol/ext-apps` 2.0.3 pour
initialiser sa connexion puis appeler les outils avec `callServerTool`.
Les commandes attendent la fin de la négociation, même si l’alias historique
existe déjà. L’échec d’une initialisation embarquée ne déclenche pas de repli
vers cet alias. Le harness de développement autonome garde sa passerelle
locale explicite, puisqu’il n’a pas d’hôte parent. La négociation est bornée à
15 secondes ; les appels permettent un démarrage Kit à froid plus long.
Le harness se déclare explicitement : une WebView native de premier niveau
doit aussi initialiser MCP Apps, même si `window.parent === window`.

Cinq tests supplémentaires couvrent l’ordre des appels, l’initialisation unique,
les échecs, le harness autonome et une négociation avec le vrai SDK. Ce dernier
envoie `ui/initialize`, puis `ui/notifications/initialized`, avant `tools/call`.
Le test vérifie aussi que les métadonnées privées de la réponse sont conservées.
Le build servi est contrôlé pour contenir le protocole d’initialisation.
L’audit npm de cette nouvelle dépendance ne signale aucune vulnérabilité.

Cette correction suit le [contrat UI officiel OpenAI](https://developers.openai.com/plugins/build/chatgpt-ui)
et le [guide MCP Apps](https://modelcontextprotocol.io/extensions/apps/build).
Le succès du test de protocole ne remplace pas la vérification du nouveau
bundle dans l’hôte réel.

Le [reçu de cette seconde correction](evidence/codex-2026-10-23/bridge-receipt.json)
identifie le SDK, le bundle installé et les journaux retenus. La suite courante
compte **107 tests Node réussis**, un skip de privilège symlink Windows, et
aucun échec. Le reçu initial conserve les mesures de hauteur et l’identité du
bundle du premier correctif ; il n’est pas réattribué au nouveau bundle.

### Essai dans le vrai panneau après correction

Le [reçu de l’essai hôte](evidence/codex-2026-10-23/host-smoke.json) distingue
les observations du panneau et les résultats des tests automatiques. Il
identifie les six captures DOM brutes par leur hash, sans publier leur contenu
privé. Ces captures textuelles ne sont pas des captures d’écran.

Le panneau latéral expose la phase d’initialisation `mcp`. L’automatisation
remplit les champs avec une copie isolée de la fixture de qualification,
scanne le workspace, valide la configuration et le préflight, puis lance Kit.
Le scan trouve une scène USD et un asset. La vérification des processus
confirme que configurer et valider n’ont pas démarré Kit. Après lancement,
le processus géré n’a pas de fenêtre native ; la supervision indique runtime,
bridge et scène prêts, et le panneau reçoit une télémétrie fraîche.
L’onglet **Contrôler** s’ouvre et affiche la timeline et les caméras.

L’opérateur confirme que le panneau reste utilisable après l’échec de capture.
Il confirme ensuite pouvoir utiliser les commandes. Une lecture indépendante
du contrôleur indique une simulation en pause à 10 secondes. Cette confirmation
manuelle ne certifie pas l’ensemble des commandes ni leur fonctionnement vidéo.
La fermeture et le vide observés avant le handshake ne se reproduisent pas
pendant les lectures réussies de ce nouvel essai. Cela ne certifie ni une
stabilité prolongée ni la hauteur du panneau dans l’hôte réel.

### Échec vidéo et limite de capture

Le panneau annonce le démarrage du transport puis affiche **Flux vidéo non
connecté**. Aucun décodage RTX n’est attesté. Deux diagnostics sont conservés :

- Une violation `connect-src`, disposition `enforce`, est signalée dans le
  journal du panneau. L’instrumentation actuelle omet la destination bloquée
  pour ne pas conserver d’URL contenant un jeton. Son rôle causal dans
  l’échec vidéo n’est pas établi.
- Le journal Kit signale `800b1000`, `NVST_R_INVALID_STATE`, transition de
  l’état `1005` vers `1004`, pendant la création de session streaming. Le
  processus Kit et le contrôle de scène restent actifs après ce message.

L’outil de capture d’écran ne renvoie aucune image. Ensuite, une commande de
lecture et de nouvelles lectures DOM expirent, y compris un essai borné à
40 secondes. La commande de lecture n’est pas comptée comme réussie : l’état
relu via MCP reste arrêté à zéro. L’automatisation est interrompue sur cette
instance pour éviter les répétitions bloquantes. Une lecture ultérieure répond
de nouveau ; le canal présente donc aussi un défaut intermittent. Le fait que le panneau soit
utilisable par l’opérateur et que son canal d’automatisation ne réponde plus
est consigné séparément.

La vidéo Codex, le cycle lecture/pause depuis son interface, les captures
d’écran et le clavier/souris natif restent à qualifier. Les contrôles backend
et les images Chrome antérieurs ne comblent pas ces lacunes. La cause exacte
du refus CSP et de la transition streaming doit être isolée avant de modifier
les autorisations réseau ou de déclarer le produit validé dans Codex.

L’opérateur fournit trois captures de l’interface qui affichent la vidéo hors
ligne et la simulation en lecture. Elles sont conservées uniquement comme
diagnostic local : elles ne montrent pas le rendu de la scène et aucune n’est
ajoutée comme preuve visuelle de qualification. L’acceptation exige une image
réelle RTX transmise depuis Kit et affichée dans le panneau Codex.

### Instrumentation de l’échec média

Une version instrumentée classe les violations CSP (donnée embarquée, objet
local, origine loopback, réseau externe masqué) sans conserver les chemins,
requêtes ni identifiants. Elle observe les états natifs WebRTC, les pistes,
les octets vidéo reçus et le compteur d’images décodées, ainsi que les codes
d’erreur SDK reconnus. Les compteurs proviennent de `RTCPeerConnection.getStats`.
Les écoutes et relevés sont bornés et nettoyés ; aucun rendu de remplacement
n’est fourni et les autorisations CSP ne sont pas élargies.

Le [reçu des diagnostics](evidence/codex-2026-10-23/diagnostics-receipt.json)
identifie ce nouveau bundle et ses contrôles automatiques. Il ne réattribue
pas les observations de l’ancien bundle à cette nouvelle construction.
Une nouvelle instance doit charger l’instrumentation avant de rattacher la
vidéo au Kit existant. Son essai visuel reste en attente.

La nouvelle ressource et l’accès latéral nécessitent un rechargement du
catalogue MCP. L’outil de capture ne voit que les applications développées dans
un panneau latéral ; les cartes restées dans la conversation ne sont pas
accessibles. Le succès textuel de l’outil d’ouverture n’est pas une preuve
visuelle.

Les journaux complets, sauvegardes des fichiers installés, chemins locaux et
captures brutes restent dans `release/`, ignoré par Git. Seuls les reçus
expurgés et captures inspectées peuvent être ajoutés au dépôt après audit de
l’index et vérification de l’identité publique du commit.
