# Diffusion publique — RC3

## Cible de cette livraison

Une application **locale installable sur un poste Windows RTX**, intégrée à Codex. Ce n’est pas une offre SaaS, un serveur multi-utilisateur ni un rendu disponible sur une URL publique. Le bridge de contrôle reste authentifié et borné au loopback. Ne pas l’exposer par redirection de ports ou tunnel public.

La distribution est composée du source OmniStream, de son bridge, de l’installateur, des tests et de la documentation. Les composants NVIDIA et les dépendances Web sont obtenus sur le poste cible. Le bundle contenant le SDK WebRTC est construit localement, jamais livré dans ce ZIP.

## Aucun parcours de démonstration implicite

L’installation crée les répertoires nécessaires mais n’injecte aucune scène, animation, configuration fictive ou télémétrie. Il faut choisir un USD réel. Les fichiers sous `tests/fixtures` et `mcp/fixtures` servent aux tests explicites, dans des copies temporaires. Les doubles de test du protocole ne sont pas importés par l’interface de production et ne servent jamais ses réponses.

Les nombres initiaux visibles dans la configuration, comme le temps initial ou le multiplicateur de cadence, sont des paramètres à appliquer, pas des mesures. Les mesures absentes restent inconnues. Un diagnostic tronqué ou ancien ne permet pas de conclure que toute la scène est valide. Un port prêt n’allume pas l’état vidéo : une image doit avoir été décodée.

## Parcours public

Installer les prérequis via l’assistant, laisser les vérifications se terminer et charger le plugin local. Choisir le workspace et le USD. Valider la configuration, lire le préflight, puis lancer. L’inspection et l’édition sont disponibles seulement après connexion effective du bridge. La navigation reste disponible pour consulter l’installation, les états et les erreurs.

Le studio distingue la configuration d’une session, son runtime, le contenu USD, le transport de lecture, la supervision et le diagnostic. Les formulaires ne sont pas rafraîchis depuis une ancienne configuration pendant la saisie. Les clés d’animation sont saisies par l’opérateur ou capturées depuis une pile TRS réelle reconnue ; aucune rotation de démonstration n’est préchargée.

## Contrôles avant publication

| Vérification | État de cette livraison |
|---|---|
| Source, TypeScript, protocole et contrats UI | Exécutés localement : PASS |
| Intégrité, absence de dépendances/binaires redistribués | Vérifiés sur extraction propre |
| Front réel, navigation et erreurs du vrai MCP sans Kit | Exécutés via Chromium et adaptateur de transport de test |
| Build Vite de production / installation propre | Non validés ici : dépendance native Linux manquante, réseau d’installation indisponible |
| Windows + RTX + Kit + PhysX | À qualifier sur le poste cible |
| Décodage vidéo et interactions dans le vrai Codex | À vérifier sur le poste cible |
| Installation/reprise/réparation/désinstallation Windows | Scripts revus, pas exécutés ici |
| Licence publique et éventuelle soumission catalogue | Décision et démarche du titulaire des droits ; non effectuées |

Le code demeure `1.0.0-rc3` et `UNLICENSED`. Ne pas présenter cette archive comme une version stable certifiée, ni comme une publication open source ou un plugin déjà accepté dans un catalogue.

## Dossier de validation à conserver

Après une installation propre, conserver `validation-report.json` et les versions exactes de Windows, GPU/driver, Kit, extensions, SDK WebRTC, Node et Codex. Ajouter une observation réelle de la vidéo et des actions dans le viewport. Exécuter `npm run test:physics` : le succès exige un déplacement physique observable, pas une simple réponse au lancement. Essayer aussi arrêt externe, reconnexion, erreur de chemin, perte du bridge, export sans écrasement, reprise d’installation et désinstallation préservant NVIDIA et les données utilisateur.

Le test local de cette livraison n’a pas ouvert une application Kit réelle. Il a montré que son absence reste une absence, avec de vraies erreurs MCP, et non un état de démonstration.

## Références de maintenance

- API d’intégration UI officielle : https://developers.openai.com/plugins/reference
- SDK NVIDIA et documentation correspondant au paquet installé : https://docs.omniverse.nvidia.com/ov-web-sdk/latest/web-streaming-library/overview.html
- Limites de `Compress-Archive` pour les fichiers cachés : https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.archive/compress-archive

Le source conserve la version épinglée du SDK. Une mise à jour de celui-ci doit repasser la qualification, pas seulement modifier un numéro dans le lockfile.
