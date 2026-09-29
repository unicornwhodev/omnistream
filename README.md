# OmniStream for Codex — 1.0.0-rc3

Studio local pour piloter **une vraie scène NVIDIA Omniverse Kit** depuis Codex : configurer une session, lancer le runtime sans fenêtre native, inspecter/modifier le USD, piloter animations et corps rigides, observer la télémétrie et diagnostiquer les erreurs. Le navigateur reçoit le rendu WebRTC ; il ne le remplace pas par une scène 3D locale.

**Statut : release candidate, pas version stable certifiée.** Le contrôleur et le front ont été testés localement ; la qualification Windows/RTX/Kit, le build de production et le flux vidéo réel dans Codex restent des gates de livraison. Les résultats et limites sont détaillés dans [QA-REPORT.md](QA-REPORT.md).

## Installer

Sur le poste Windows RTX cible, extraire l’archive puis lancer :

```bat
installer\install.cmd
```

L’assistant vérifie les prérequis, ouvre les sources externes nécessaires, attend les installations/acceptations de l’opérateur puis reprend. Il ne contient ni Kit, ni runtime/extension NVIDIA compilée, ni SDK WebRTC préemballé, ni bundle généré. Les dépendances sont obtenues sur le poste cible. Le plugin installé se trouve par défaut sous `%LOCALAPPDATA%\OmniStream\plugin`.

Le workspace et le dossier d’assets sont créés **vides**. Aucune scène d’exemple, animation préfabriquée, statistique ou télémétrie fictive n’est installée. Utiliser votre propre USD de confiance. Le mode de développement n’est pas lancé par l’installateur et ne remplace pas le transport de production.

[Première utilisation](docs/QUICKSTART.md) · [Installation et reprise](docs/INSTALLATION.md) · [Préparer la diffusion publique](docs/PUBLIC-DEPLOYMENT.md)

## Choisir un parcours

- **Ouvrir une nouvelle scène** : configurer le workspace et le fichier USD, lancer le préflight, puis démarrer la session Kit depuis **Lancer**.
- **Travailler sur la scène déjà ouverte** : utiliser la session Kit OmniStream active, inspecter le stage dans **Scène**, puis prévisualiser et appliquer les corrections. Ne relancez pas la simulation pour une simple correction : le lancement charge le stage configuré.

Le second parcours s’applique à une scène ouverte dans le runtime géré par la session MCP courante ; OmniStream ne rattache pas automatiquement un Kit lancé indépendamment. Voir le [guide de la scène ouverte](docs/LIVE-SCENE.md) et l’[index de la documentation](docs/README.md).

## Interface

Viewport dominant, navigation latérale et inspecteur par tâche : **Configurer / Lancer / Scène / Contrôler / Superviser / Diagnostic**. Palette graphite, accents verts, champs lisibles, navigation clavier et adaptation aux petites largeurs. Le transport de lecture reste directement sous le viewport.

Un chemin saisi reste un brouillon jusqu’à validation et ne signifie pas que la scène est chargée. Les valeurs absentes sont marquées « Non vérifié » ou « — ». L’état vidéo actif exige une image décodée, pas seulement un port ouvert. Les commandes de scène sont désactivées sans bridge authentifié. Les formulaires ne sont pas écrasés par la supervision périodique.

## Ce que Codex peut réellement demander

| Parcours | Outils principaux |
|---|---|
| Préparer le runtime | `configure_omniverse_simulation`, `preflight_omniverse_simulation` |
| Démarrer/rattacher | `launch_omniverse_simulation`, `attach_omniverse_stream` |
| Inspecter le contenu | `inspect_omniverse_scene`, `inspect_omniverse_prim` |
| Corriger sans écrire la source | `preview_omniverse_scene_patch`, `apply_omniverse_scene_patch`, `undo_omniverse_scene_patch` |
| Exécuter et contrôler | `run_omniverse_scene`, `control_omniverse_simulation` |
| Observer/debugger | `supervise_omniverse_simulation`, `read_omniverse_live_telemetry`, `diagnose_omniverse_scene`, `read_omnistream_runtime_logs` |
| Conserver/abandonner | `export_omniverse_scene_patch`, `discard_omniverse_scene_edits` |

[Référence MCP](docs/MCP-REFERENCE.md) · [Scène ouverte, physique et animation](docs/LIVE-SCENE.md)

L’édition concerne les transformations TRS, clés, paramètres physiques autorisés, colliders, corps rigides et gravité. Ce n’est pas un éditeur complet de robots, fluides, animation squelettique ou graphes OmniGraph. La présence de schémas USD ne prouve pas que PhysX est disponible. La cadence cible n’est pas une vitesse physique garantie.

## Sécurité et données

Runtime local géré, bridge loopback authentifié, workspace borné, opérations sérialisées et limites d’observation. Aperçus liés à une scène/révision, expiration, annulation en session et export vers un nouveau fichier. Aucun Python arbitraire envoyé par le modèle. L’enregistrement explicite d’une caméra reste une exception qui écrit dans la source autorisée.

Fermer le panneau n’équivaut pas à arrêter Kit ; fermer sa session MCP provoque l’arrêt sécurisé. Les corrections non exportées sont perdues à l’arrêt du runtime. L’annulation d’un patch n’est pas un retour arrière déterministe du solveur. Le produit n’est pas un service Windows autonome ni un serveur de rendu multi-utilisateur sur Internet.

[Architecture](docs/ARCHITECTURE.md) · [Sécurité](docs/SECURITY.md) · [Dépannage](docs/TROUBLESHOOTING.md)

## Vérifier

Après obtention des dépendances sur la plateforme cible :

```powershell
npm --prefix .\web ci
npm run check
npm test
npm run test:python
npm run test:web
npm run build:web
```

Les tests natifs `npm run test:runtime` et `npm run test:physics` utilisent des USD de test en copie temporaire. Ces données restent séparées du produit et du workspace utilisateur. Aucun résultat simulé de ces tests n’est affiché comme télémétrie réelle. La qualification visible dans Codex reste séparée.

Sur une archive fraîchement extraite : `npm run verify:release -- --strict` puis `npm run audit:public`. Le manifeste vérifie l’intégrité des fichiers ; ce n’est pas une signature numérique.

[Validation](docs/VALIDATION.md) · [Checklist de release](docs/RELEASE-CHECKLIST.md) · [Changements](CHANGELOG.md) · [Tiers](THIRD_PARTY.md)

## Version, téléchargement et licence

La version source est `1.0.0-rc3` sur Windows 10/11 x64 avec GPU NVIDIA RTX. Ce dépôt est public, mais le logiciel reste `UNLICENSED` : aucune licence open source n’a été choisie. Le package npm n’est pas publié (`private: true`). Au 29 septembre 2026, aucun tag ou artefact de release n’est publié sur GitHub. La page [Releases](https://github.com/unicornwhodev/omnistream/releases) indiquera les téléchargements lorsqu’une candidate sera publiée.

L’archive Windows source-only se construit avec :

```powershell
.\installer\Build-Release.ps1
```

Le script crée un ZIP et son fichier `.sha256` sous `release/`; le ZIP exclut Kit, les binaires NVIDIA, les dépendances WebRTC et le bundle généré. L’empreinte détecte les changements de fichiers mais n’est pas une signature. Les critères de tag, release candidate et distribution sont décrits dans [Versions et distribution](docs/RELEASING.md). Aucun package npm ou release GitHub stable n’est annoncé ici.

## Diffusion publique

Cette passe prépare la distribution locale du logiciel ; elle ne publie pas le plugin dans un catalogue et n’expose aucun port Kit sur Internet. Une licence n’a pas encore été choisie : le projet reste `UNLICENSED`. Ne pas le présenter comme open source avant la décision explicite du titulaire des droits.
