# Scène ouverte, simulation et debug — RC3

## Ce que ce module contrôle

La scène est celle **déjà ouverte dans le Kit géré par cette session MCP**. Aucun rechargement n’est nécessaire pour inspecter ses objets, préparer une animation, modifier des paramètres physiques autorisés ou relancer la timeline. Une application Omniverse lancée indépendamment n’est pas automatiquement adoptée : le bridge doit appartenir au runtime géré, avec son authentification et son workspace.

La vidéo reste le rendu NVIDIA/RTX transmis par WebRTC ; aucun moteur 3D de remplacement n’a été ajouté au navigateur. Le lancement utilise le mode sans fenêtre native. Kit reste actif en arrière-plan tant que sa session MCP est active. Fermer le panneau n’arrête pas une exécution ; arrêter/quitter le serveur MCP déclenche son arrêt sécurisé. Il ne s’agit pas d’un service Windows persistant indépendant de Codex.

## Deux parcours distincts

**Nouvelle session :** installer → ouvrir le studio → configurer le workspace et le USD → préflight → lancer. Cela ouvre un fichier et démarre/réutilise Kit.

**Scène déjà ouverte :** rattacher le flux si nécessaire → inspecter la scène → choisir un objet → prévisualiser → appliquer → exécuter → observer → pause/stop → corriger → relancer. Ne pas rappeler `launch_omniverse_simulation` pour une simple correction : cette ancienne commande charge le stage configuré.

## Actions réellement exposées

| Besoin | Outil | Particularités |
|---|---|---|
| Parcourir la scène | `inspect_omniverse_scene` | Enfants directs paginés, `stageId`, révision, axe vertical, unités, plage de temps, disponibilité de PhysX. |
| Inspecter un objet | `inspect_omniverse_prim` | Attributs scalaires/vecteurs bornés, schémas, matrice locale, nombre de clés. Les grands tableaux sont omis. |
| Préparer une correction | `preview_omniverse_scene_patch` | Validation et construction d’une couche USD isolée, sans modification de la scène vivante. |
| Appliquer | `apply_omniverse_scene_patch` | Requiert l’identifiant de scène, la révision attendue et un aperçu non expiré. |
| Annuler | `undo_omniverse_scene_patch` | Dernière correction OmniStream, pas l’historique de tous les outils Kit. Jusqu’à 12 états. |
| Exporter | `export_omniverse_scene_patch` | Nouveau fichier `.usda` dans le workspace, confirmation obligatoire, jamais d’écrasement. |
| Abandonner | `discard_omniverse_scene_edits` | Supprime les corrections privées et leur historique, après confirmation ; pas les sources. |
| Configurer la surveillance | `configure_omniverse_scene_watch` | Jusqu’à 16 attributs USD existants, avec pause locale optionnelle sur NaN/Inf. |
| Diagnostiquer | `diagnose_omniverse_scene` | Inspection structurelle bornée : capacités, corps, colliders, animation/dynamique incompatible, masses invalides, scènes physiques absentes/multiples. |
| Exécuter sans recharger | `run_omniverse_scene` | Animation/timeline ou physique ; limite de durée réelle, retour au début optionnel, boucle désactivée. |
| Lire l’observation en continu | `read_omniverse_live_telemetry` | Dernier échantillon et événements depuis un curseur, sans attendre un nouveau RPC Kit. |

Les contrôles transport/caméra, le diagnostic runtime et la lecture des fichiers stdout/stderr de la RC1 restent disponibles.

### Paramètres de scène pris en charge

`transform` : position, rotation locale XYZ en degrés, échelle. Cette opération remplace l’ordre local des opérations de transformation dans la couche de correction. Elle n’est donc pas un petit delta ajouté à une pile arbitraire : inspecter la matrice et vérifier la cible avant validation.

`animate_transform` : 2 à 120 clés complètes, temps en secondes strictement croissants, translation/rotation/échelle. Les secondes sont converties en time codes USD avec la cadence du stage. Pas d’interpolation quaternion, de courbes Bézier, d’animation squelettique ou de retargeting dans cette RC. Un corps animé doit être cinématique, pas dynamique.

`rigid_body` : masse, cinématique/dynamique et collider optionnel. `collider` : activation/désactivation sur une géométrie. Les meshes utilisent une approximation convex hull, pas une reconstruction exacte de maillage concave. Les corps imbriqués et instances sont refusés.

`physics_scene` : création/configuration d’un prim PhysicsScene, direction et intensité de gravité. Les distances/accélérations sont exprimées en unités de la scène ; 9,81 convient à des mètres, 981 à des centimètres. Lire `metersPerUnit` et `upAxis` avant de proposer une configuration. Le paramètre `mass` suit les unités de masse USD, usuellement le kilogramme.

`attribute` : modification typée d’une petite liste blanche d’attributs physiques existants (masse, densité, vitesses, activation, gravité, friction, restitution). Pas de code Python, shader, référence externe ou chaîne USD arbitraire. L’interface propose les formulaires principaux ; l’édition d’attributs détaillés est exposée à Codex par MCP.

`playback_range` : début, fin et images par seconde. Les métadonnées sont appliquées à la couche de session, pas sauvegardées dans la source. Des changements externes concurrents de ces métadonnées sont détectés et peuvent bloquer l’annulation plutôt que d’être écrasés.

## Exécution physique et ses limites

La présence de `UsdPhysics` permet l’édition du USD mais **ne prouve pas la disponibilité du solveur**. Le mode physique requiert la détection effective de l’extension `omni.physx`, au moins une scène physique et un corps actif ; les erreurs structurelles détectées bloquent le lancement.

Le canal NVIDIA et le template sélectionnés doivent fournir cette extension. Lorsqu’elle est absente, le panneau l’indique et désactive le choix physique. Ajouter `"omni.physx" = {}` dans les dépendances de l’application Kit compatible, puis reconstruire avec les outils NVIDIA, est une opération d’administration du projet Kit, pas une installation silencieuse faite par un outil de simulation. Vérifier les disponibilités et conditions NVIDIA de ce projet. Aucune dépendance NVIDIA n’est redistribuée par cette archive.

Les deux modes utilisent **la même timeline globale Kit**. Le mode animation ne désactive pas une physique déjà présente. Stop peut réinitialiser les états du moteur ; une annulation de patch n’est pas un retour arrière déterministe du solveur. `seek` et frame arrière ne sont pas une intégration physique inverse.

L’ancien `rateMultiplier` règle la cadence cible d’updates, **pas une dilatation temporelle physique garantie**. Le panneau le nomme désormais « Cadence cible ». Le solveur, les réglages d’application et la politique de frames déterminent l’exécution réelle.

## Sens exact du « temps réel »

Trois boucles sont séparées :

- **Vidéo** : flux WebRTC natif, cadence dépendante de Kit/RTX et du décodage. Aucun FPS vidéo n’est inventé à partir de l’horloge du bridge.
- **Observation locale** : échantillonnage visé toutes les 250 ms sur le thread principal Kit, événements envoyés par le socket authentifié, cache MCP indépendant. Le panneau lit ce cache toutes les secondes lorsqu’il est visible. `kitUpdateMs` mesure la boucle d’update Kit, pas la durée GPU ou les FPS vidéo.
- **Décisions Codex** : le modèle appelle les outils pour observer, diagnostiquer puis agir. Les événements ne réveillent pas automatiquement le modèle et ne lui donnent pas une boucle de raisonnement à chaque frame.

Le watchdog local met en pause au-delà de la durée réelle autorisée (1 à 3 600 secondes) ou lors d’une valeur surveillée non finie. Il fonctionne aussi panneau fermé, **tant que Kit et sa boucle principale restent réactifs**. Ce n’est pas un watchdog matériel : si le thread principal est bloqué, il ne peut pas s’exécuter. Une télémétrie vieille de plus de 2,5 secondes ou une déconnexion est explicitement marquée périmée.

La surveillance lit le USD. Des états exclusivement conservés dans Fabric, CUDA ou une extension métier ne sont pas automatiquement observables. Le contrôle des robots, articulations, fluides, incendies, capteurs, graphes OmniGraph ou solveurs personnalisés exige encore un adaptateur métier ; la RC3 n’en prétend pas disposer.

## Corrections et persistance

Un aperçu porte sur une scène et une révision précises et expire après 120 secondes. Au maximum 4 aperçus, 32 opérations par patch, 120 clés par animation, 2 Mio de couche gérée et 12 états d’annulation sont conservés.

L’application transfère la couche validée dans une couche anonyme privée de la session. Les deux couches affectées sont sauvegardées en mémoire avant transfert et restaurées si l’application échoue ; `Sdf.ChangeBlock` seul ne serait pas une transaction. Si une opinion plus forte de la session masque une propriété proposée, le patch est refusé plutôt qu’annoncé efficace.

Pause est requise pour préparer/appliquer les transformations ; **Stop** pour les paramètres physiques et l’annulation. Les corrections de scène n’appellent pas `Save` sur les sources. L’ancien outil `save_omniverse_camera` reste l’exception explicite : il peut sauvegarder la pose de caméra dans un fichier existant autorisé, uniquement à la demande de l’utilisateur.

Exporter produit **une couche d’overrides**, pas une scène autonome ou aplatie. Il faut la composer avec la scène source dans un projet USD ; les assets référencés ne sont pas copiés. L’export ne vide pas la session et ne marque pas les corrections comme abandonnées. Exporter puis abandonner permet ensuite d’ouvrir un autre stage. Arrêter Kit sans export perd les corrections en mémoire.

## Logs et diagnostic

Tampons bornés : 400 événements bridge, 500 événements cache MCP, 150 événements d’interface. Le curseur, les pertes et la fraîcheur sont exposés. Les logs Carbonite utilisent le callback public lorsqu’il est disponible ; les fichiers runtime stdout/stderr restent accessibles autrement. La lecture des fichiers est limitée à leur dernière tranche de 512 Kio, puis au nombre de lignes demandé.

L’expurgation masque les deux secrets de session et les formats de credentials usuels. Elle n’est pas une garantie de détection de tous les secrets arbitraires d’extensions tierces : relire les logs avant de les publier.

En cas de `revision_conflict` ou `stage_changed`, inspecter puis recréer l’aperçu, sans boucle aveugle de réapplication. En cas de `operation_uncertain`, superviser le runtime et suivre l’arrêt sécurisé ; une erreur de transport ne prouve pas l’absence d’effet.

## Parcours sur votre scène

L’installateur ne copie aucune scène ni animation dans le workspace. Choisir un fichier USD réel et de confiance, placé dans le workspace autorisé, ou inspecter le stage déjà ouvert dans le Kit géré.

Dans **Scène**, inspecter puis sélectionner un objet. Les paramètres sans observation restent vides. Pour une animation, saisir les clés explicitement, ou utiliser la capture de la pose courante : elle n’est proposée que pour une pile TRS locale simple reconnue. Les piles complexes ne sont pas arbitrairement décomposées. Les valeurs de capture proviennent d’une nouvelle inspection du prim à l’instant choisi par le runtime. Le champ de temps indique où placer cette pose dans l’animation ; saisir ce champ ne déplace pas à lui seul la timeline.

Prévisualiser la correction puis confirmer son application avant expiration de l’aperçu. Arrêter la timeline avant les changements physiques. Une désactivation de collider existant écrit maintenant effectivement `physics:collisionEnabled = false`. Choisir une durée bornée valide, exécuter puis observer la scène et les mesures réelles. Un diagnostic ancien ou incomplet est signalé ; une inspection tronquée bloque le lancement automatique borné.

Les scènes `tests/fixtures/*.usda` et `mcp/fixtures/*.usda` sont réservées aux tests explicites. Elles ne sont importées ni par l’interface de production, ni par le serveur MCP normal. `npm run test:runtime` et `npm run test:physics` utilisent des copies temporaires dédiées : il s’agit de tests natifs, pas d’un mode de démonstration du produit.

## Références techniques

- NVIDIA Kit streaming : https://docs.omniverse.nvidia.com/kit/docs/kit-app-template/latest/docs/streaming.html
- NVIDIA Timeline : https://docs.omniverse.nvidia.com/kit/docs/omni.timeline/latest/omni.timeline/omni.timeline.Timeline.html
- OpenUSD layers : https://openusd.org/release/api/class_sdf_layer.html
- OpenUSD Xformable : https://openusd.org/dev/api/class_usd_geom_xformable.html
- OpenAI plugin/UI bridge : https://developers.openai.com/plugins/build/chatgpt-ui
