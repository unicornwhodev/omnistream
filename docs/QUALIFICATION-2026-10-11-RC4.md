# Qualification RC4 — premier lot A01 à A04

Travaux commencés le 11 octobre 2026 ; rapport actualisé le 17 octobre 2026.
Les résultats du 12 octobre sont conservés comme historique.

## Verdict du lot

Version locale : **1.0.0-rc4**, issue du commit de référence
`02d9fac248d85b76fdbd93bd18bac2bf33be7732` avec les modifications du lot.
Ce rapport décrit une candidate locale. Aucune publication, promotion stable,
création de tag ou modification du canal NVIDIA n'est effectuée.

| Point | Statut | Preuve et portée |
|---|---|---|
| A02 — dépendance de build | Corrigé et validé | `source-map-js` 1.2.2 ; installation propre, audit npm à zéro vulnérabilité, build et contrat du bundle réussis. |
| A03 — instantané cohérent | Corrigé et validé | Résumé complet issu du brouillon ou de l'instantané normalisé ; réponses obsolètes rejetées ; tests de comportement et vérifications des dix champs dans le harness local. |
| A04 — préparation et lancement | Corrigé et validé | Toute édition invalide la préparation ; lancement protégé par l'identité de configuration et un verrou synchrone ; tests de remplacement concurrent côté serveur. |
| A01 — véritable panneau Codex | **En qualification — vidéo locale obtenue** | Le refus de connexion directe est documenté dans Codex. Le 17 octobre, le transport de négociation MCP débloque une vraie vidéo RTX FireViewer de 1280 × 720 dans le harness Chrome local. Installation de cette candidate, vidéo dans Codex, trois cycles et entrée native restent à vérifier. |

A02–A04 sont clôturés pour ce lot. A01 demeure ouvert jusqu'à la qualification
de la candidate corrigée dans le véritable hôte. La qualification native de Kit et les
vérifications du harness ont chacune leur propre portée. Elles ne ferment
pas A01 et n'autorisent aucune promotion stable.

## Référence et conservation

Poste Windows 11 Home, build 26200 ; RTX 5070 Ti, 16 303 MiB ; pilote 616.56.
Node 24.14.0 et npm 11.9.0. Python autonome 3.11.9 avec OpenUSD 26.8 dans le
venv de qualification existant.

Runtime **Existing**, template NVIDIA au commit
`483e364a4176f102f2d3c3aaf9f301a103d61d69`, Kit
`110.2.0+feature.windows-x86_64.release`, application
`omnistream.runtime_streaming.kit`. Le SHA-256 de `kit.exe` reste
`5fe8ad14c77328dbe4a11361d1fdb45f8581d2595e7607afab0221379d4650ef`.

Vite 6.4.3, React 18.3.1 et le SDK NVIDIA `@nvidia/ov-web-rtc` 6.6.0 sont
conservés. Le diff des dépendances du lockfile porte uniquement sur
`source-map-js` 1.2.1 → 1.2.2, en plus des deux métadonnées de version RC4.
L'avis traité est [GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q),
avec le [correctif officiel 1.2.2](https://github.com/7rulnik/source-map-js/releases/tag/v1.2.2).

La fixture est copiée dans un workspace de qualification distinct. Son SHA-256
initial est `3a88ff0221052cf68710bce40ff200df5e8238a433a2c40479792afb24fc8615`.
Les neuf archives RC3, les sauvegardes de l'installation et du bridge RC3 et
les preuves antérieures sont conservées. Les racines opérateur restent celles
de la configuration existante. Les données et runtime NVIDIA sont exclus du ZIP.

## Contrats de préparation

Le panneau distingue brouillon, instantané validé, preflight associé et runtime
actif. Chaque édition invalide immédiatement le preflight et le succès affiché.
Navigation et supervision n'écrasent pas les champs saisis. La réponse normalisée
du contrôleur n'est acceptée que pour la révision ayant déclenché sa validation.

`configurationId` est opaque et renouvelé lors de la validation ou d'une
modification effective des réglages stockés. Le preflight copie la configuration
avant ses opérations asynchrones. Le panneau transmet systématiquement
`expectedConfigurationId` au lancement et refuse un contrôleur ancien sans cette
identité. Le serveur conserve la compatibilité des anciens appels `{}`.

Le lancement refuse un identifiant divergent avec
`error.data.code = simulation_configuration_changed`. Le contrôle est répété
après les attentes d'admission/réconciliation et avant le chargement du stage.
Le panneau ne reconfigure plus implicitement depuis ses champs et ne lance pas
une deuxième demande concurrente.

## Vérifications complémentaires du 17 octobre 2026

Après le correctif d'hydratation du formulaire et l'ajout du transport de
signalisation MCP local, `npm run check`, `npm test`, `npm run test:web` et
`npm run build:web` passent. Le runner Node compte **86 réussites et un skip
Windows existant** sur les privilèges de symlink. Les tests de préparation,
sonde et adaptateur compilés par TypeScript comptent 38 réussites ; les sept
tests du relais MCP sont inclus dans le total Node. Ils couvrent notamment
les limites de messages, l'ordre et les acquittements, l'expiration, le changement
de session et la fermeture asynchrone attendue par le SDK.

Les **34 tests OpenUSD passent sans skip**, avec `OMNISTREAM_REQUIRE_USD=1`.
L'audit npm complet indique zéro vulnérabilité. Les reçus datés et logs expurgés
sont conservés dans le répertoire local de qualification, ainsi que la première
capture vidéo FireViewer du harness. Ce résultat vidéo ne ferme pas A01 : voir
le [cas FireViewer](QUALIFICATION-FIREVIEWER-RC4.md) pour sa portée exacte.

## Tests exécutés le 12 octobre 2026

| Vérification | Résultat |
|---|---|
| Installation propre `npm --prefix web ci` | PASS, également dans l'installation locale. |
| `npm run check` | PASS, syntaxe Node et TypeScript. |
| `npm test` | PASS : protocole MCP, contrats source et **57 tests Node réussis**, plus **un skip Windows** sur le privilège de création de symlink. |
| Logique de préparation extraite | **22 tests Node réussis**, compilés avec le TypeScript déjà installé, sans nouveau framework. |
| Courses serveur | PASS : identifiant périmé, remplacement pendant l'admission du lancement et conservation de l'instantané pendant le preflight ; aucun processus Kit démarré lors des refus. |
| OpenUSD réel | **34 tests réussis, zéro skip USD** avec le venv existant. |
| Audit npm, arbre complet | PASS : **zéro vulnérabilité**. |
| `npm run test:web` et reconstruction finale | PASS, bundle distribué et contrats MCP/panneau. |
| NVIDIA `repo.bat build` et `repo.bat test` | PASS sur le projet Existing ; quatre tests du bridge réel, plus le test de démarrage. Les entrées d'application `.kit` ne contenant aucun test d'extension ne constituent pas des tests fonctionnels supplémentaires. |
| Validation installée finale | PASS, smoke runtime exécuté ; `SkipKitTests` utilisé uniquement pour ne pas répéter les tests Kit déjà réussis avec le même bridge. |
| Ancien lancement MCP `{}` | PASS sur le runtime réel dans le smoke test installé. |
| Arrêt sûr du smoke test | PASS : processus géré, signaling et bridge absents après arrêt. |
| Formulaire React dans le harness | PASS : état initial verrouillé ; normalisation et résumé ; édition/revalidation des dix champs ; brouillon conservé à travers les six vues et la supervision. Aucun lancement Kit demandé par ce parcours UI. |
| Panneau RC4 dans Codex | PARTIEL : validation, preflight, résumé « Prêt à lancer », lancement de la fixture et bridge observés. **Vidéo en échec** : aucun média reçu, y compris après rattachement au même processus. |
| Dialogue d'arrêt dans Codex | PARTIEL : ouverture observée ; focus sur « Annuler », fermeture par annulation et retour du focus sur « Arrêter Kit » vérifiés dans le DOM. La saisie et les parcours Tab/Shift+Tab natifs restent non qualifiés. |
| Fin de l'essai hôte | PASS pour l'état final observé : les trois PID Kit vus pendant l'essai sont absents ; supervision sans processus, signaling, bridge ni opération en cours. Le dernier arrêt passe par le safe-stop MCP du processus exact après expiration de l'automatisation UI ; le parcours complet de confirmation dans le dialogue reste non qualifié. |

La première validation installée a échoué sur une supervision sans simulation
pendant un démarrage RTX lent. Le test tentait alors de lire `.state` sur `null`.
Le helper de qualification reconnaît désormais `simulationError`, qui est
renvoyé comme donnée par la supervision, et applique le retry existant, limité
à 60 secondes et aux erreurs de lecture transitoires. Les mutations ne sont
pas répétées. La nouvelle exécution passe ; l'échec initial reste archivé.

Les tests de préparation couvrent absence de configuration, normalisation,
édition des dix champs, validation/preflight en échec, réponses tardives,
polling périmé, incompatibilité de version, double clic et erreur de lancement.
Les résultats synthétiques de transport restent explicitement des tests de logique.

## Preuves locales et reste à qualifier

Les reçus JSON, logs expurgés, observations DOM, hashes et captures du harness
sont conservés sous `release/qualification-rc4-r0-20261011/`, hors archive source.
Le manifeste du ZIP final et son fichier SHA-256 identifient la livraison ;
la vérification stricte après extraction contrôle les tailles, hashes, versions
et l'absence de fichiers supplémentaires. L'intégrité n'est pas une signature.

Le blocage d'ouverture est résolu le 12 octobre après le développement du
panneau par l'opérateur. L'onglet MCP Apps est accessible et annonce RC4.
La qualification utilise la copie USD isolée et la candidate `candidate-03`,
SHA-256 `96e273e40bc68956564c7d20155881364adde92771360a19fe14c65b5409aaa4`.
Les 95 fichiers manifestés concordent entre sources, installation et cache
aux contrôles effectués. Les 297 fichiers opérateur, les deux fixtures source
et cette archive restent identiques. La copie USD isolée utilisée dans le
panneau présente une écriture en fin d'essai, décrite ci-dessous. La mise à
jour ultérieure du livrable porte uniquement sur ce rapport et son manifeste ;
le code et le bundle testés restent inchangés.

Le premier lancement charge le stage et connecte le bridge. La négociation
WebRTC signale des échecs de reconnexion puis affiche « Flux vidéo non connecté ».
Un rattachement sur le même PID ne rétablit pas l'image. Le DOM vidéo reste à
`readyState = 0`, dimensions `0 × 0` et temps média `0`. Une capture du véritable
panneau montre simultanément runtime/bridge/scène prêts et vidéo hors ligne.
L'opérateur confirme directement avoir vu uniquement ce message. Deux autres
démarrages sont observés pendant l'essai ; ils restent également sans image
aux points de mesure, avec des échecs de reconnexion. Le troisième fournit le
message précis `Session start failed with error: "Sign in request timed out."`
après cinq tentatives. L'étape de connexion initiale du client SDK échoue ;
la durée de timeline n'explique pas ce diagnostic. Un GET HTTP local anonyme
de diagnostic vers `/sign_in` reçoit 501 ; il ne reproduit pas la requête SDK
et ne permet pas d'établir la cause de son timeout. Aucun des trois cycles
complets requis n'est déclaré réussi.

Les preuves de cette reprise sont conservées sous
`release/qualification-rc4-r0-20261011/codex-host-20261012/` : observations DOM
horodatées, capture `cycle-1-no-video.jpg`, états de supervision, logs expurgés,
confirmation de l'opérateur et hashes de conservation avant/après.
Le premier processus a été observé avec un handle de fenêtre native nul.
Les trois processus et leurs services sont absents en fin d'essai.

Le contrôle final de la copie de travail USD détecte un changement de 518 à
4 011 octets. Son SHA-256 passe de
`3a88ff0221052cf68710bce40ff200df5e8238a433a2c40479792afb24fc8615` à
`0527452db62847e95b604a0bb9ff717f4acef359a518399823879500327466ea`.
Le fichier final contient notamment une matrice de caméra et des réglages de
rendu Kit. L'opérateur ne sait plus s'il a confirmé la sauvegarde explicite de
pose ; l'automatisation n'a demandé aucune sauvegarde. L'origine de l'écriture
reste donc non confirmée. Les deux fixtures source conservent leur hash initial,
ainsi que les 297 fichiers opérateur. La copie modifiée est conservée, avec les
versions `fixture-before-host.usda` et `fixture-after-host.usda` dans les preuves.
Ce résultat ne permet pas de certifier l'absence de persistance de caméra dans
la copie de qualification.

Le bouton d'agrandissement signale « Le plein écran est refusé par l'hôte » ;
un appel d'automatisation expire après 30 secondes, puis la lecture DOM et la
capture normale du panneau fonctionnent à nouveau. Ces limites de capture et
de plein écran sont distinctes de l'échec vidéo. Le parcours automatisé de
confirmation de l'arrêt expire également ; le safe-stop MCP ferme ensuite le
dernier processus de qualification et vérifie son extinction. Les API MCP Apps
ne fournissent pas de clavier/pointeur natifs ; ces tests restent à réaliser
après rétablissement du média. La cause précise de l'échec WebRTC n'est pas
établie par ces preuves.

La timeline de cette fixture sans durée d'animation explicite va ici de `0` à
`1/24 s`. La position affichée `0,042 s` correspond à une image à 24 images/s.
Cette valeur ne constitue pas une preuve de réception vidéo.

La prochaine investigation doit recueillir les erreurs de signaling/ICE du
client SDK dans le véritable hôte et les corréler aux événements de Kit, puis
rétablir la vidéo avant de reprendre les trois cycles complets.

Pour fermer A01, réaliser trois cycles dans le véritable panneau RC4 : validation,
lancement, progression de frames décodées, interaction native visible et arrêt
sûr. Vérifier aussi saisie des formulaires, Tab/Shift+Tab, annulation/confirmation
des dialogues, retour du focus et réouverture sans relancer Kit. Conserver les
observations horodatées et captures liées aux hashes de la candidate exacte.

La [qualification RC3](QUALIFICATION-2026-10-01.md) reste un rapport historique.
Elle ne qualifie pas les changements RC4 ni un autre runtime NVIDIA.

## Reprise avec une carte réelle et diagnostic de transport

La reprise du 12 octobre utilise une copie vérifiée des 296 fichiers de la
carte FireViewer Die–Pontaix R5 et deux caméras dans une couche de qualification
séparée. Voir le [cas documenté](QUALIFICATION-FIREVIEWER-RC4.md) pour les
paramètres, identités, résultats et critères d'acceptation.

Après la première clôture documentaire, le panneau est modifié : métadonnées
privées de la réponse MCP Apps prises en priorité sur l'ancien slot global,
rattachement manuel réessayable et sérialisé, probe WebSocket bornée et
observation des violations CSP sans conserver les URL bloquées. Ces changements
ne modifient ni Kit, ni le bridge Python, ni le SDK NVIDIA, ni les dépendances.
Les comptes de tests historiques ci-dessus décrivent la première candidate.
La reprise ajoute deux tests publics et cinq tests de probe, soit **64 tests
Node réussis et un skip Windows existant**. `npm run check` et les **34 tests
OpenUSD sans skip** repassent le 12 octobre, avec logs horodatés.

Le bundle JS de cette reprise a pour SHA-256
`3cbcecf1fab8d12153f021523e7fc1065484480e84387008567d5343e2a5efd1`
dans les sources, l'installation et le cache. Le contrôleur reste
`ef6bb3f1895005f7887d23750f8283997253a8fbaf94b4f006d1e11caef46d15`.
Les anciennes archives et captures sont conservées ; elles ne sont pas
réattribuées à ce nouveau bundle.

Le nouveau panneau observe `connect-src, enforce` avant la connexion SDK.
Le code du Codex installé filtre les origines HTTP/WS et conserve HTTPS/WSS,
avec son exception HTTP localhost désactivée. Le changement de scène ne
corrige pas ce blocage de transport. La vraie carte est inspectée, le contrôle
de caméra et la lecture bornée sont vérifiés, mais aucun rendu reçu dans
Codex n'est déclaré à ce point de mesure. Le relais WSS était alors préparé et
compilé, sans activation ni installation de confiance.

L'opérateur autorise ensuite explicitement le certificat localhost et le relais.
La confiance Windows est vérifiée après sa confirmation du dialogue natif.
Le relais est intégré au contrôleur et au panneau, avec un preflight bloquant
sur certificat/port et un arrêt lié à la session détenue. Le vrai helper démarre
depuis Node et passe le test TLS 1.3, le rejet d'un nom incorrect ou d'une
confiance absente, la transmission et l'extinction de son listener. Le magasin
de certificats est lu par X509Store, ce qui corrige le lancement sous un chemin
de modules PowerShell hérité. Ces preuves de transport ne remplacent pas la
vidéo dans Codex. La reprise compte désormais 70 succès Node, un skip Windows
existant et 34 tests OpenUSD sans skip. Les hashes et observations historiques
ci-dessus restent rattachés à la candidate antérieure ; le cas FireViewer et
les reçus WSS identifient la nouvelle candidate à installer/recharger.

Les preuves de la carte réelle sont sous
`release/qualification-rc4-r0-20261011/real-scene-20261012/`. Les 296 fichiers
opérateur, leurs 296 copies et la couche de qualification restent inchangés
au contrôle après essai. A01 reste ouvert.
