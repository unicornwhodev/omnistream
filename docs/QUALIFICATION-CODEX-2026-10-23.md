# Correctifs d’ouverture et de hauteur Codex — 23 octobre 2026

## État de la qualification

Les corrections source, le protocole MCP et le bundle construit sont vérifiés.
La régression de hauteur est reproduite avant correction et ne se reproduit
plus après correction aux trois largeurs mesurées. La qualification visuelle
complète dans le vrai panneau Codex reste ouverte tant que la vidéo et les
commandes n’y ont pas été observées. Un second essai a identifié un défaut
d’initialisation MCP Apps, corrigé et testé avec le SDK officiel.

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

### État visuel

L’interface réelle a été ouverte dans le panneau latéral et lue par
l’automatisation : navigation, contrôleur local et paramètres de session sont
présents. Elle est ensuite devenue inaccessible à l’outil de capture.
L’opérateur confirme qu’elle s’est fermée seule et l’a rouverte. L’erreur
d’initialisation ci-dessus établit un défaut distinct de la boucle CSS ; le
retest visuel du bundle avec handshake doit confirmer la disparition du vide.

La nouvelle ressource et l’accès latéral nécessitent un rechargement du
catalogue MCP. L’outil de capture ne voit que les applications développées dans
un panneau latéral ; les cartes restées dans la conversation ne sont pas
accessibles. Le succès textuel de l’outil d’ouverture n’est pas une preuve
visuelle. Aucune vidéo Codex, aucun clavier/souris natif Codex ni stabilité
prolongée ne sont certifiés par les tests de mise en page.

Les journaux complets, sauvegardes des fichiers installés, chemins locaux et
captures brutes restent dans `release/`, ignoré par Git. Seuls les reçus
expurgés et captures inspectées peuvent être ajoutés au dépôt après audit de
l’index et vérification de l’identité publique du commit.
