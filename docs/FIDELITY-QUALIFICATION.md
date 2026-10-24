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
