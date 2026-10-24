# Préparation de la simulation Die–Justin

Ce chantier prépare une simulation avancée et exploitable de la zone de
20 × 20 km centrée sur la Croix de Justin. Le calcul, les données et les médias
natifs restent dans Colab et Drive. L’export de la scène vers le PC reste suspendu.

## Conditions avant G4

La L4 reste utilisée pendant la préparation. La bascule vers une G4 exige une
scène complète, les contrôles OmniStream distants, un fonctionnement stable,
le raccordement du moteur d’incendie et des essais intégrés documentés.
La qualification en conditions réelles s’appuiera sur cette simulation.

La qualification L4 peut utiliser un pilote isolé de 16 tuiles de 500 m,
disposées en 4 × 4 autour du centre. Ce périmètre de 4 km² garde ses propres
couches USD, configuration, caméras, checkpoints et sorties. Le cas complet
reste référencé en lecture seule ; ses empreintes sont contrôlées avant et
après les essais. Un résultat du pilote conserve son périmètre dans les reçus
et ne constitue pas à lui seul une mesure de la charge des 400 km² sur G4.

Sur G4, l’accélération temporelle configurée doit être le double de celle du
profil L4. Avec la référence actuelle à ×500, la cible G4 est ×1000. Ce facteur
est un objectif de progression du temps simulé ; le débit effectivement atteint
doit être mesuré. Les pas numériques nécessaires au solveur, les cinq vues
synchrones et les intervalles de capture en temps simulé restent conservés.

Le profil G4 doit employer une RTX PRO 6000 Blackwell adaptée au rendu Kit.
Une A100 ne remplace pas le GPU du viewer actuel : le livestream Isaac Sim
n’y est pas pris en charge. Une migration ne vaut pas qualification du runtime,
du pilote, de Flow ou du rendu sur le nouveau GPU.

## Scène et effets

La présence des fichiers et leur chargement dans le rendu sont deux contrôles
distincts. Le contrôle des populations doit conserver tous les identifiants,
positions, hauteurs et états d’assets déclarés. La réduction du nombre d’objets
pour masquer une limite de ressources ne fait pas partie du contrat.

Les VFX existants de la factory sont la base de l’intégration : flammes de
surface, fronts de végétation, feux de cime, feux de bâtiments, fumées claires
et sombres. Le catalogue actif, ses empreintes, ses paramètres et ses reçus
de contrôle doivent être vérifiés avant composition. Les sources et recettes
existantes restent préservées. Une recette visuellement contrôlée ne certifie
pas à elle seule une propagation ou une émission physique calibrée.

Le moteur d’incendie et son adaptateur font partie de cette préparation.
Ils doivent exposer des états effectivement produits et une interface réelle
de progression, gel et reprise. Aucun appel à un solveur absent ni aucun front
inventé ne peut servir de qualification. Les périmètres quotidiens contraignent
l’évolution du scénario ; les états intermédiaires et paramètres reconstruits
conservent leur provenance et leurs incertitudes.

Les états touché, en combustion, décroissant et éteint doivent piloter les
modèles d’assets, les émetteurs et les volumes appropriés. L’activité d’un front
ne suffit pas à annoter une flamme visible. La visibilité doit tenir compte de
la caméra, des occultations, de la fumée, du rendu et du seuil de détection.

## Données exploitables par FireViewer

Les sources pertinentes comprennent les rapports officiels, périmètres,
observations satellites, météo, photos, vidéos, autres médias et témoignages
publics disponibles. Leur collecte doit produire un registre lié au scénario
avec identifiant déterministe, source, date d’acquisition, intervalle temporel,
emprise ou localisation, droits d’usage, empreinte, fiabilité et incertitude.
Les dates de publication et d’observation sont conservées séparément.

Les éléments observés, produits par le simulateur, reconstruits et estimés
restent distinguables. Les contradictions, données manquantes et limites de
résolution restent disponibles. Les témoignages et médias sans géolocalisation
ou date vérifiée ne deviennent pas automatiquement une vérité de calibration.
Les données personnelles, secrets d’accès et médias à droits restreints restent
hors du commit public.

## Qualification intégrée

La qualification couvre les commandes de scène, caméra, timeline, simulation,
corrections bornées et annulation sur le Kit distant réel. Le viewer doit
rester utilisable après une déconnexion et une reconnexion sans relancer le
scénario. La latence réseau, le coût du rendu et le délai des commandes doivent
être mesurés séparément.

Le pipeline de capture garde une horloge globale pour les 50 caméras des dix
zones. Les groupes voient exactement le même état et tous les producteurs,
y compris feu et fumée, doivent être gelés explicitement pendant les cinq
captures. Les négatifs et transitions restent présents. Les images sont
vérifiées, hachées et reliées aux paramètres, annotations et états de simulation.

Le bilan doit inclure la charge complète d’assets, les scénarios multi-fronts,
les transitions rapides de fumée, les reprises sur interruption, les fichiers
incomplets, la stabilité RAM/VRAM et les essais de ghosting. Les mesures de
simulation, rendu GPU, écriture et débit restent séparées. Les captures de
preuve montrent la vraie scène et les effets réellement rendus dans Codex.

## Références matérielles

- [Notes officielles Colab, ajout de G4](https://colab.research.google.com/notebooks/relnotes.ipynb)
- [Types de GPU Google Cloud](https://docs.cloud.google.com/compute/docs/gpus)
- [Contraintes du livestream Isaac Sim 5.1](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/manual_livestream_clients.html)
