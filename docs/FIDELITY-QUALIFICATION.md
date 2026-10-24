# Fidélité du pilote géographique

La qualification distingue les pixels reçus par WebRTC, le rendu RTX avant
encodage et les détails réellement présents dans les assets. Une connexion prête
ou un réglage demandé ne valide aucun de ces facteurs.

## Flux observé le 24 octobre 2026

Le candidat recevait 1280 × 720 malgré une demande de 1920 × 1080. Kit refusait
les demandes de redimensionnement. Après correction des dimensions de fenêtre et
de négociation, le navigateur a réellement décodé 1920 × 1080. La vue et ses
intrinsèques ont été conservées pour cette comparaison.

Le profil partagé demande 30 images/s, un plafond de 60 Mb/s et la désactivation
de la réduction dynamique de résolution. Ce sont des demandes, pas une garantie
de débit. Le trajet privé observé utilisait un relais, avec environ 240 ms de RTT.
Une cadence de vidéo reçue ne mesure pas le nombre de nouvelles images rendues.

La fenêtre Kit et le viewport ont été configurés séparément à 1920 × 1080 dans
Isaac Sim 5.1. Les réglages réellement utilisés sont
`/app/livestream/allowResize=true`, `allowDynamicResize=true` et
`disableSdkScaling=true` sous le même préfixe, dès le démarrage de Kit.
Vérifier leur prise en charge lors d'un changement de version.

## LOD à 100 m

Le LOD0 doit être disponible à **100 m des objets**. Cette distance ne désigne
pas le pas du maillage du terrain. Le pilote expose les vraies variantes des
arbres aux racines instanciées via des wrappers dérivés. Les assets de la factory
et les couches du cas complet restent inchangés.

La sélection utilise prudemment la distance 3D aux limites réelles des canopées.
Elle peut conserver un détail élevé plus loin que nécessaire, mais évite de
sous-détailler un objet proche situé au bord d'une tuile. Le LOD0 est anticipé à
120 m et conservé jusqu'à 140 m. Le niveau intermédiaire est anticipé à 420 m et
conservé jusqu'à 440 m. Les commandes de caméra forcent une mise à jour. Le suivi
des mouvements natifs est contrôlé à 4 Hz et réévalue le détail après 10 m de
déplacement. Cette politique ne garantit pas une mise à jour instantanée lors
d'une téléportation entre deux contrôles.

L'audit des modèles de référence a mesuré :

| Modèle | Triangles LOD0 | Triangles LOD2 |
| --- | ---: | ---: |
| 0 | 296 547 | 177 928 |
| 1 | 232 887 | 186 309 |
| 2 | 296 132 | 177 679 |
| 3 | 20 093 | 20 093 |
| 4 | 7 847 | 7 847 |
| 5 | 6 545 | 6 545 |

Les trois derniers modèles ont le même nombre de triangles aux trois niveaux.
Certaines textures de feuillage du modèle 1 ne font que 256 × 256, y compris en
LOD0. Augmenter le niveau géométrique ne crée pas ces détails manquants.

## Comparaison dans Kit

`pipelines/event_capture/tools/prepare_pilot_view_lods.py` prépare les wrappers
du seul pilote et une caméra située à 100 m du milieu d'une instance d'arbre
réellement présente. `compare_pilot_fidelity.py` compare à cette caméra le réglage
courant, le DLAA natif, puis les arbres en LOD0. Le test ne modifie pas la
résolution du terrain.

La timeline reste en pause et les producteurs Flow doivent être explicitement
gelés. Le test rejette un changement de caméra ou d'heure, vérifie les variantes
effectivement composées et contrôle la réserve mémoire. Le writer natif du
notebook écrit les PNG, vérifie leur lecture et leur SHA-256. Les paramètres,
les payloads et la caméra d'origine sont restaurés puis vérifiés.

Le temps par phase inclut stabilisation et écriture ; ce n'est pas un temps GPU.
L'exécution GPU reste inconnue sans profilage distinct. Les images natives et
leurs reçus restent dans Colab/Drive. Les captures du navigateur prouvent
l'interface, sans remplacer les PNG de production.

## Portes encore ouvertes

Le pilote contient 16 tuiles, 106 335 instances de végétation et 18 prototypes.
Il ne démontre ni la résidence GPU du cas de 400 km² ni sa tenue sur 47 jours.
Les essais statiques Replicator ont vérifié 135 images par exécution pour 1, 2,
5 et 10 groupes, mais la répétabilité visuelle reste en échec aux seuils fixés.

Les recettes Flow réelles sont chargées comme essai visuel. Le moteur physique
d'incendie, le gel exact des grilles, les annotations scientifiques, la fumée et
les flammes visibles restent des validations distinctes. La politique de LOD du
viewport ne qualifie pas à elle seule la sélection de détail pour les cinq
caméras simultanées d'un groupe Replicator.

Le candidat navigateur ne remplace pas l'acceptation dans le véritable panneau
Codex. Le passage G4 et l'export complet restent suspendus à ces validations.

## Résultats natifs conservés

Les deux séries ont réellement terminé dans Kit : caméra à 100 m d'un arbre et
vue lointaine conservée. Six PNG 1920 × 1080 à l'instant simulé 12 s ont été
vérifiés. À 100 m, le profil automatique composait 18 prototypes de tuiles en
LOD0 et 270 en LOD2. Dans la vue lointaine, les 288 étaient en LOD2. L'essai
forcé composait effectivement les 288 en LOD0. Ces slots proviennent de
18 modèles partagés ; ils ne désignent pas 288 arbres uniques.

Les réglages d'origine et les wrappers sources ont été vérifiés après chaque
série. Les relevés de VRAM par phase allaient approximativement de 11,22 à
12,17 Go décimaux sur une L4 de 24,15 Go. Il ne s'agit pas d'une mesure continue
du pic mémoire ni du benchmark de la scène complète.

Un essai ultérieur a réellement décodé AV1 en 1920 × 1080 dans le candidat, sur
le même Kit et la même vue. Cela valide la compatibilité de cette paire d'hôtes,
sans certifier encore la lisibilité des petits détails lointains. H.264 reste
le choix initial de compatibilité ; le codec se choisit sous **Connexion**.

## Essai de débit en 4K

`pipelines/event_capture/tools/benchmark_pilot_rendering.py` s'exécute dans le
Kit existant du pilote de seize tuiles. Il exige la timeline en pause, les
producteurs Flow explicitement désactivés et les assets déclarés du pilote
chargés. Il ne crée aucun adaptateur physique d'incendie et ne qualifie pas
le gel exact des grilles Flow.

Le diagnostic réutilise un unique Render Product 3840 × 2160 pour les cinq
caméras fixes d'une zone. La relation USD de caméra est relue après chaque
changement. Les writers sont armés explicitement ; `step_async(delta_time=0.0)`
rend sans avancer la timeline. Le produit ne se met pas à jour entre les
captures. Les essais utilisent 1, 4 puis 16 sous-images, avec une seconde passe
à 16 pour mesurer la répétabilité aux seuils inchangés de moyenne 2 et P99 12.

L'aperçu principal est temporairement réduit à 640 × 360 puis son rafraîchissement
est désactivé. Ce choix réserve la mémoire aux captures natives 4K ; les images
de cet aperçu temporaire ne constituent aucune preuve de qualité. La caméra
principale ne tourne pas. La définition, le rafraîchissement et les paramètres
de timeline sont restaurés et relus après deux mises à jour Kit.

Le rapport distingue les durées de liaison du produit, de préparation, de
rendu et lecture des pixels, puis d'encodage, écriture et vérification PNG.
Les mesures VRAM concernent tout le GPU ; la RAM est le RSS du processus.
Le temps d'exécution GPU et le coût du moteur physique restent inconnus sans
leur instrumentation. Les PNG et rapports bruts restent sur Colab/Drive.

Invocation depuis le notebook du Kit qui possède déjà le pilote :

```python
report = await benchmark_pilot_rendering.run(stage, geographic, pilot_root)
```

Chaque exécution écrit un dossier neuf `4k-render-throughput/<UTC>` sous le
pilote. Une image n'entre dans le rapport qu'après vérification de sa définition,
lecture du PNG et calcul de son SHA-256. Les produits sont libérés à la sortie,
y compris en cas d'erreur. Le diagnostic s'arrête au-delà de 90 % de VRAM ou
en dessous de 5 Gio de RAM disponible. Une interruption ou un rapport incomplet
ne valide aucune série de captures. L'essai est limité au rendu du pilote et
ne donne pas la durée du cas complet de 400 km².

### Résultat du 24 octobre 2026

Le [résumé vérifié](evidence/4k-throughput-2026-10-24.json) conserve les empreintes
des rapports et images, les mesures et les échecs. Dans Isaac Sim 5.1 sur L4,
avec RTX RayTracedLighting, DLAA natif et seed 20260624, une série complète de
20 PNG 3840 × 2160 a terminé à l'instant simulé 12 s. Les cinq caméras sont
restées fixes et aucun produit n'était actif entre les captures. Un seul
produit a servi aux quatre passes.

| Sous-images par capture | Groupe de cinq images | Rendu et lecture des pixels | Encodage, écriture et vérification |
| --- | ---: | ---: | ---: |
| 1 | 51,51 s | 43,97 s | 7,04 s |
| 4 | 53,72 s | 46,47 s | 6,99 s |
| 16 | 95,13 s | 87,81 s | 7,10 s |
| 16, seconde passe | 94,94 s | 87,64 s | 7,10 s |

Ces durées comprennent les étapes réellement exécutées ; la première passe
inclut l'initialisation du produit et du graphe. Ce sont des durées murales,
pas des temps d'exécution GPU profilés. Le pic échantillonné pendant les captures
est de 16,07 Gio de VRAM pour tout le GPU et 15,10 Gio de RSS pour le processus.
La caméra principale, sa définition 4K, son rafraîchissement, le temps 12 s et
le mode de timeline ont été relus après restauration. Aucun produit ni callback
de writer non demandé ne subsistait.

La répétabilité à 16 sous-images échoue pour quatre caméras : MAE 3,89 à 4,32
et P99 26 à 28, aux seuils conservés de 2 et 12. La cinquième passe : MAE 0,13,
P99 2. Les variantes 1 et 4 échouent également pour les quatre premières vues
face à la référence 16. Il s'agit d'écarts natifs avant compression vidéo ;
ils ne permettent pas encore d'attribuer la cause au bruit de rendu, à un
historique temporel ou à un producteur externe. Ni le réglage rapide ni le
réglage 16 ne sont acceptés comme profil scientifique pour le groupe.

Les essais antérieurs ont atteint la réserve de mémoire en recréant des produits
4K. La destruction des objets ne restituait pas immédiatement toute la mémoire
au GPU. Un redémarrage contrôlé du seul Kit pilote a permis la série complète
avec réutilisation d'un produit. Trois essais incomplets restent explicitement
en échec dans le résumé ; deux de leurs images et les vingt images de la série
terminée, soit 22 PNG, ont été vérifiés et copiés sur Drive avec relecture SHA.
Les PNG natifs n'ont pas été exportés sur le PC.

À titre de budget arithmétique seulement, 47 jours entièrement inactifs avec
50 caméras et une capture toutes les six heures donnent 9 400 images. Aux
coûts observés sur ce pilote, cela représente environ 26,9 à 49,6 heures de
captures, hors moteur physique et transitions. Ce n'est ni le planning réel
de l'incendie ni une prévision de la scène complète. L'accélération ×500 ou
×1000 ne réduit pas le temps passé à rendre un état gelé.

Le profil 4K actuel ne satisfait donc pas la préparation complète : le coût
de rendu et lecture des pixels ainsi que les écarts temporels natifs doivent
encore être traités. La G4 et l'export restent suspendus. La qualification
du candidat navigateur ne constitue pas celle du véritable panneau Codex.
