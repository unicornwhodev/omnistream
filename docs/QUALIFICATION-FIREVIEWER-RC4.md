# Cas réel FireViewer Die–Pontaix R5 dans OmniStream RC4

État actualisé le 17 octobre 2026 : **carte réellement rendue en vidéo dans le
harness Chrome local avec négociation MCP ; candidate correspondante à qualifier
dans Codex**. Le chargement USD, la vidéo dans un navigateur de développement et
la qualification du véritable panneau restent des critères distincts.

## Scène et conservation

Le cas utilise le package local `fireviewer-die-pontaix-map-r5`, déjà présent
dans le workspace opérateur : terrain, orthophoto, bâtiments, routes,
végétation et éclairage. Il ne contient pas de scénario d'incendie ou de
simulation physique ; aucun de ces résultats n'est revendiqué ici.

Les 296 fichiers du package, soit 714 593 910 octets, sont copiés et vérifiés
par SHA-256 dans un workspace isolé. Le stage d'entrée d'origine `map.usda`
a pour SHA-256 `fa6f2a43bc06b9aab8d8abafc181b6f4deed2b1957a6ce277bfe1d06f4a66f6c`.

Le stage `fireviewer-qualification.usda` référence cette copie par sublayer.
Il ajoute exclusivement deux caméras et une plage de lecture de 60 secondes
à 24 images/s. La carte source et ses assets ne sont pas édités.
L'ouverture avec OpenUSD réel compose 450 prims Mesh, 2 PointInstancer,
14 Material, 60 Shader, une lumière distante, une lumière d'environnement
et les deux caméras de qualification. Ces comptes ne mesurent pas le FPS.

## Reproduction sur le poste de qualification

Les chemins sont relatifs à la racine du dépôt :

- Workspace : `release/qualification-rc4-r0-20261011/real-scene-20261012/workspace`.
- Stage : `fireviewer-qualification.usda` dans ce workspace.
- Runtime : Kit Existing sous `release/qualification-20261001/external/kit-app-template`.
- Caméra initiale : `/World/QualificationCameras/Overview`.
- Caméra rapprochée : `/World/QualificationCameras/Detail`.
- Démarrage en pause, temps initial 0, cadence cible 1, sans boucle ni auto-play.

Dans le véritable panneau Codex : saisir ces paramètres, valider, obtenir un
preflight réussi pour le même `configurationId`, puis lancer. Vérifier le
stage réellement chargé et la caméra sélectionnée dans la supervision.
Le rendu reste celui de Kit/RTX transmis par WebRTC.

## Critères d'acceptation

1. Le bridge inspecte réellement `/World/FireViewerSite` et ses catégories.
2. La vidéo possède des dimensions non nulles et son temps média progresse.
   Une capture doit montrer le terrain réellement rendu dans Codex.
3. Passer de Overview à Detail change le cadrage visible, puis revenir à
   Overview. Aucun appel de sauvegarde de pose n'est utilisé.
4. L'opérateur vérifie clavier/pointeur dans le viewport, saisie des champs,
   Tab/Shift+Tab et retour du focus après les dialogues.
5. Réouvrir le panneau rattache la même session sans relancer Kit.
6. L'arrêt sûr ferme uniquement le processus géré. Répéter trois cycles
   complets avant de fermer A01.
7. Les hashes du package opérateur et de sa copie sont vérifiés après essai.

## Preuves

Les preuves locales, exclues de l'archive source, sont conservées sous
`release/qualification-rc4-r0-20261011/real-scene-20261012/` :
`source-copy-manifest.json`, `scene-preparation.json`, observations du panneau,
supervision, captures et logs expurgés. Leurs dates et hashes relient le cas
à la candidate et au runtime réellement utilisés.

## Connexion locale et première vidéo le 17 octobre 2026

La distribution Codex 26.1013.3656.0 refuse encore la connexion directe locale
pendant les essais WSS. Le certificat localhost et les vérifications TLS ne
suffisent donc pas à établir une vidéo dans le panneau.

Un transport optionnel transmet désormais la négociation SDP/ICE par les outils
MCP réservés à l'application. Le contrôleur ouvre seulement le WebSocket
authentifié de son propre Kit sur 127.0.0.1. La vidéo et l'entrée native restent
du WebRTC NVIDIA. Aucun relais public, tunnel ou service distant n'est créé.
Le SDK NVIDIA 6.6.0 et le runtime Existing sont conservés.

Dans le harness Chrome local, le run `e03214d0d690feb363c3`, PID 40748, rend la
carte FireViewer avec la caméra Overview. Le DOM vidéo donne 1280 × 720,
`readyState=4`, `paused=false`. Le temps média passe de 0,735073 s à 45,783135 s
(seconde mesure à 21:45:14.889 UTC). La capture montre le terrain et l'interface
native de Kit. Un ancien avertissement de la console Kit reste visible dans
cette image ; il ne remplace pas les mesures du média.

Le déblocage vient d'une correction de l'adaptateur de signalisation : fermer
le socket ne déclenche plus son événement de fermeture dans la pile de l'appel
`close()`. Cela permet au SDK de terminer son propre nettoyage sans traiter
cette fermeture comme une déconnexion du serveur. Un test couvre cette course.

Preuves locales : `codex-wss-20261017/chrome-mcp-first-live-frame.jpg` et
`chrome-mcp-media-progress.json`. Elles prouvent cette étape technique dans
Chrome, pas trois cycles ni l'entrée native dans Codex. La candidate construite
après ces corrections reçoit son propre reçu d'installation et ses hashes.
La confirmation de l'opérateur « la scène est visible » est conservée avec
cette portée ; aucun résultat Codex non observé n'en est déduit.

## Résultats observés le 12 octobre 2026

La configuration `d79597ec-c0e1-4023-b228-88150f613680` est validée et son
preflight réussit dans le panneau Codex. Le lancement ouvre le stage dans
le processus géré PID 7664, sans fenêtre native demandée. Le run contrôleur
est `dab6512bbfafd859f381` et le stage inspecté
`1d1e8516415f4f46aeefdb9ed1a859de`.

L'inspection du bridge retrouve `/World/FireViewerSite` et ses cinq branches :
Terrain, Buildings, Routes, VegetationContext et Vegetation. Le diagnostic
structurel traite 600 prims, sans limitation de scan ni issue signalée. Cela
ne certifie ni le rendu, ni les collisions, ni une performance GPU.

Le passage de la caméra Overview à Detail est accepté par Kit, puis Overview
est restaurée. Le run de lecture borné à cinq secondes termine avec
`wall_limit_reached`, `playing=false` et une position de timeline de
`4,1667 s`. La carte ne contient pas d'animation d'objet : ce test qualifie
le contrôle et le watchdog, pas un déplacement animé ou physique.

À 17:09:54 UTC, le panneau journalise une violation `connect-src, enforce`
et refuse l'ouverture WebSocket locale, avant la négociation du média SDK.
Le DOM vidéo observé reste `readyState=0`, `0 × 0`, temps média `0`.
La capture `codex-connect-src-blocked.jpg` montre cet échec dans le véritable
panneau avec la carte chargée. Aucun cycle complet vidéo/entrée n'est réussi.

Le code de normalisation CSP du Codex installé (package 26.1007.2314.0,
interface 26.1007.21434) lit bien `_meta.ui.csp`, mais retient HTTPS/WSS et
écarte HTTP/WS. Son exception localhost HTTP/WS est désactivée dans cette
distribution. Ajouter l'alias historique `widgetCSP` ne corrigerait donc pas
ce filtrage. La documentation des
[métadonnées UI OpenAI](https://developers.openai.com/plugins/reference)
confirme le contrat standard ; cette restriction particulière est constatée
dans le code local et dans le panneau, pas déduite de la documentation.

Lors de ce premier essai, le relais TLS était seulement préparé et compilé.
Les certificats localhost préexistants ne passaient pas le contrôle de chaîne.
Le plan initial est conservé dans `WSS-CHANGE.md` ; la suite ci-dessous décrit
les opérations réalisées après l'autorisation de l'opérateur.

Le contrôle après essai vérifie 592 hashes : les 296 fichiers opérateur et
les 296 fichiers copiés sont identiques aux valeurs initiales. Le wrapper
USD de qualification reste lui aussi inchangé. À ce point de mesure, Kit était
en pause sur Overview.

## Correctif local WSS après autorisation

L'opérateur autorise explicitement « Autoriser le certificat local et poursuivre »,
puis confirme le dialogue de confiance Windows. Le certificat serveur localhost
est valable 90 jours, CA=false, avec une clé Windows non exportable. Sa partie
publique est approuvée dans CurrentUser/Root ; la clé reste dans CurrentUser/My.
Les reçus `localhost-certificate-created.json` et `localhost-certificate.json`
distinguent l'état avant confirmation et la vérification fraîche réussie.
La première vérification dans le processus d'import avait conservé un résultat
de chaîne non fiable ; une vérification dans un nouveau processus réussit.

La configuration locale reçoit uniquement `signalingTls` avec le port 49101
et l'empreinte du certificat. Le reçu `signaling-tls-config-change.json` conserve
la sauvegarde et les hashes avant/après ; tous les champs initiaux sont préservés.
Kit garde ses ports de signaling 49100 et média 47998, le canal Existing et le
SDK NVIDIA 6.6.0. Aucun réglage de sécurité de Codex n'est modifié.

Le contrôleur démarre son propre relais TLS sur 127.0.0.1, transmet sans réécriture
les octets au signaling Kit, et ferme son entrée après l'arrêt sûr de Kit.
Le panneau déclare WSS localhost dans sa CSP et utilise `forceWSS` du SDK.
L'URI `panel-rc4-tls.html` distingue cette ressource de l'ancien document en cache.
Le preflight exige un certificat valide et fiable ainsi qu'un port de relais
disponible. Un défaut est bloquant ; aucun repli silencieux ne désactive TLS.

Le test `tls-transport-integration.json`, effectué à 19:23:25 UTC, vérifie le
vrai helper Windows démarré depuis Node : TLS 1.3 accepté pour localhost,
transmission correcte vers un serveur de test détenu, mauvais nom d'hôte et
absence de confiance refusés, puis extinction du helper et de son listener.
Ce test utilise la partie publique du certificat avec la validation TLS normale.
Il ne consomme pas le bearer Kit et ne constitue pas une preuve vidéo.
Il a également révélé et corrigé l'absence du lecteur Cert dans Windows PowerShell
lancé par Node avec le chemin de modules PowerShell 7 : le helper lit désormais
le magasin Windows par l'API X509Store, sans dépendre de ce lecteur.

Les tests source incluent 70 succès Node et le skip de symlink Windows existant ;
les 34 tests OpenUSD passent sans skip. Le build et les contrats MCP/bundle du
panneau passent. La réception de frames dans Codex, les entrées natives, les
dialogues et les trois cycles complets restent à vérifier sur la candidate
installée après rechargement du contrôleur. A01 reste ouvert à cette étape.

La candidate WSS préparée conserve la version `1.0.0-rc4`. Le SHA-256 du
contrôleur est `44635fd11207fcbe121f214bd567e81aae8e7db4069490990d7d3109f6ccf7ce`
et celui du bundle JS local est
`bf33f8f4dbe2737ab08f6ac909d7057394456036e3b57587e780dad283222f1b`.
Le manifeste source et le reçu d'installation relient ces identités à l'archive
extraite, au plugin installé et au cache Codex. Le test du protocole MCP sur la
configuration TLS réelle vérifie aussi l'origine WSS de la ressource et les
checks certificat/port ; il n'effectue aucun lancement Kit.
