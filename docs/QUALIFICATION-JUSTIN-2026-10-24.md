# Croix de Justin — reconstruction IGN de 20 × 20 km

Ce chantier construit un nouveau territoire de 400 km² dans la session Colab
CPU existante, avec la factory d’assets déjà montée sur Drive. Les anciennes
cartes R5, 128 km² et pédagogique ne fournissent aucun relief à cette version.
La qualification technique et l’acceptation scientifique restent distinctes.

## Emprise et référentiels

Le centre est le POI public « La Croix de Justin » attribué au PNR du Vercors :
longitude `5.3500219`, latitude `44.744051`. Il s’agit d’une position publiée,
sans précision de levé géodésique certifiée.

Le centre Lambert-93 vaut `(885998.8505483664, 6407758.915467745)` m.
Le carré exact utilise les bornes
`(875998.8505483664, 6397758.915467745, 895998.8505483664, 6417758.915467745)`.
Les altitudes sources sont données en NGF-IGN69. Le rendu utilise un repère
local métrique Z-up, ancré au centre Lambert-93, sans modifier les altitudes.

| Source officielle | Données conservées | Époque des données |
|---|---|---|
| MNT LiDAR HD IGN | 441 GeoTIFF numériques, grille de 0,5 m | Missions 2021/2022 |
| MNS LiDAR HD IGN | 441 GeoTIFF numériques, grille de 0,5 m | Missions 2021/2022 |
| Orthophotos HR IGN | 1 600 GeoTIFF de 500 m, grille demandée de 0,2 m | Mosaïque 2023/2024 |
| BD TOPO | Bâtiments, végétation, routes, haies, cours et plans d’eau | Métadonnées de récupération conservées |
| BD Forêt V2 | 2 572 polygones de peuplements | Époque propre au référentiel |

Les résolutions des grilles téléchargées ne certifient ni la précision du levé,
ni une acquisition synchrone, ni la résolution native de chaque photographie
composant la mosaïque. Les millésimes sont conservés par source.

L’acquisition passe par les URL de GeoTIFF numériques fournies par les
métadonnées LiDAR officielles. Elle ne remplace pas le MNT par un ombrage.
Le service écrit parfois un WKT nommé Lambert-93 avec un datum non nommé : les
paramètres de projection, le CRS demandé, les dimensions, résolutions et bornes
sont vérifiés et le WKT original est conservé. Les VRT dérivés reçoivent
l’identification EPSG:2154 ; cela ne constitue pas une validation géodésique
indépendante.

## Construction et traçabilité

Chaque fichier brut est sauvegardé sur Drive et relu pour vérifier son SHA-256.
L’emprise est découpée exactement en 40 × 40 tuiles de 500 m. Chaque tuile
dispose de quatre maillages : pas de 1, 2 et 4 m, puis environ 7,94 m pour le
LOD nominal 8 m. Les MNT/MNS natifs à 0,5 m restent séparés des dérivés de rendu.
Les textures de proximité conservent la grille de 0,2 m ; les LOD de vue
d’ensemble emploient des textures dérivées de 1 ou 2 m.

Quelques pixels blancs valides sont marqués NoData par la valeur GeoTIFF 255.
Chaque tuile concernée doit être confirmée par le PNG officiel de la même
requête : égalité exacte de tous les RGB et alpha entièrement opaque. Le PNG,
son URL publique et son empreinte sont conservés. Toute différence ou vraie
transparence arrête le build ; aucun remplissage silencieux n’est autorisé.

Le notebook conserve le contrat, les sources du pipeline et leurs empreintes,
les versions des dépendances, les reprises sans duplication de workers et les
sorties de qualification. Le paquet portable dispose d’un manifeste par fichier
et d’archives avec SHA-256 et relecture de leur sauvegarde Drive. Les fichiers
bruts, données de la factory, identifiants privés et journaux restent hors du
dépôt public.

## Végétation et bâtiments

Le détecteur travaille sur le MNS moins le MNT natifs : sommets locaux,
segmentation watershed, hauteur minimale de 2 m et aire minimale de couronne
de 0,75 m². Il exclut les emprises de bâtiments, d’eau et de routes. Une largeur
de route manquante utilise explicitement l’hypothèse de 3 m. Les détections
conservent leurs coordonnées Lambert-93, altitude de sol et hauteur source.

Les 8 723 234 candidats initiaux sont croisés avec les polygones officiels de
végétation BD TOPO et BD Forêt. Ce filtre en conserve **8 466 623** et en écarte
**256 611**. Les candidats bruts restent archivés. Aucun amincissement aléatoire
ou quota décoratif n’est appliqué. Il s’agit de candidats de canopée, sans
certification du nombre de tiges, de la position des troncs ou des espèces
individuelles.

Six modèles de la factory servent de représentants morphologiques. Leurs
dimensions sont adaptées aux hauteurs et largeurs détectées. Les trois états
de référence, brûlure partielle et carbonisé sont dérivés par la factory ; les
pertes de feuillage et changements de couronne modifient réellement la
géométrie. Ces 18 prototypes restent des états visuels sans calibration de
combustion ou preuve de sévérité à chaque position.

Les bâtiments reprennent les emprises et Z de toiture de la BD TOPO, avec des
murs raccordés au MNT. Les sorties contiennent 12 181 parties de bâtiments
réparties dans 636 tuiles. Le manifeste conserve 402 signalements, dont des
altitudes de toiture absentes et des toitures partiellement sous le sol LiDAR.
Ces volumes simplifiés ne certifient pas les façades, intérieurs ou mesures
actuelles des bâtiments ; les incohérences ne sont pas corrigées par une
hauteur de prefab inventée.

## Contrôles et limites

Les contrôles indépendants vérifient l’union des tuiles, les empreintes des
quatre LOD, les raccords au même LOD, les coordonnées et identifiants de canopée,
des hauteurs relues dans les grilles natives, les dépendances USD et le
chargement/déchargement des prototypes. Des échantillons stratifiés mesurent
l’écart du rendu rééchantillonné avec le MNT natif ; cet écart ne mesure pas
l’exactitude du MNT sur le terrain.

Le [contrôleur géographique](TILED-GEOGRAPHIC-SCENES.md) conserve tout le terrain
en vue d’ensemble et charge le détail et les assets autour des caméras choisies
par les commandes du plugin. Le cadrage d’ensemble est contrôlé sur les huit
coins du volume du territoire. La présence d’un payload ou d’une télémétrie
répondante ne remplace pas une image réellement décodée dans Codex.

Le contrôle technique de base a confirmé 400 km², 6 400 fichiers LOD vérifiés,
3 120 raccords au même LOD avec un écart maximal mesuré de 0 m et aucune
dépendance USD manquante parmi 10 316 couches et 4 829 assets. Les altitudes
du maillage contrôlé vont de 269,67 à 2 041,07 m.

Sur 409 600 échantillons par LOD, l’écart vertical bilinéaire avec la grille
native donne au LOD 1 m un RMSE de 0,125 m et un percentile 95 absolu de
0,060 m, mais un maximum de **47,918 m**. Le LOD nominal 8 m donne un RMSE de
0,843 m, un percentile 95 de 1,097 m et un maximum de **113,703 m**.
Ces valeurs extrêmes doivent être localisées et expliquées avant acceptation
scientifique. Les faibles erreurs moyennes ne suffisent pas à les valider.

Le diagnostic complémentaire des 1 600 tuiles localise 203 échantillons du
LOD 1 m au-delà de 1 m d’écart, dont 26 au-delà de 5 m et deux au-delà de 20 m.
Au LOD 8 m, les comptes correspondants sont 24 459, 1 022 et 88. Le plus fort
écart est dans `tile_39_17`, au point Lambert-93 `(895701, 6406365)` : le MNT
natif vaut 1 796,722 m et la surface bilinéaire du LOD 8 m 1 683,018 m.
Le voisinage natif présente lui-même de très fortes variations, sans NoData.
Ce constat localise la perte lors du rééchantillonnage ; il ne prouve pas la
précision de la falaise source et ne justifie aucun lissage correctif inventé.
Les voisinages numériques et les coins du maillage sont conservés sur Drive.

La qualification du rendu Kit/Codex et les captures de cette nouvelle scène
doivent être consignées après leur observation.
L’acceptation scientifique reste ouverte : contrôle indépendant de précision,
incertitudes, cohérence temporelle, validation des populations et calibration
du modèle d’incendie. Un périmètre quotidien décrit une emprise touchée et ne
justifie pas des flammes, fumées ou une carbonisation uniforme sur cette zone.

## Métadonnées, météo et caméras avant export

Les sources, dates, référentiels, limites, classes et empreintes sont préparés
dans les métadonnées de scène. Une première préparation de neuf vues de contrôle
a été complétée par **10 zones et 50 caméras fixes à 1 280 × 720**, conformément
au nouveau [pipeline de captures événementielles](../pipelines/event_capture/README.md).
Les poses et optiques des 50 caméras ont été relues dans OpenUSD. Les visées
échantillonnées vers leurs cibles conservent au moins 2 m de dégagement au-dessus
du MNT. Ce sont des emplacements virtuels : ni les occultations par la végétation
et les bâtiments, ni la couverture de toute la zone dans l’image ne sont validées.

La fenêtre météo est du 24 juin 2026 à 00 h CEST au 10 août à 00 h CEST exclu,
soit 1 128 heures. Les séries continues incluent un 1 129e relevé à la borne
finale. Les archives officielles Météo-France ont été récupérées sur Colab pour
27 stations du département de la Drôme situées à moins de 60 km de la croix.
Deux séries sont préparées avec les métadonnées de scène : Die (26113003) et
Saint-Roman-Diois (26327001). Die ne fournit ici ni humidité ni vent et présente
deux valeurs de pluie manquantes. Saint-Roman fournit température, humidité,
vent et pluie sur toute la fenêtre, mais 88 humidités portent le code qualité 9.
Ces valeurs sont conservées et exclues par défaut du forçage validé.

Une série Open-Meteo ECMWF IFS au centre de l’emprise est sauvegardée séparément,
comme estimation de modèle. L’archive ZIP fournie par l’utilisateur contenait
du code de récupération, sans observations. Les sources ne sont pas fusionnées
et aucune substitution silencieuse ne comble les manques. Les codes qualité,
unités, dates UTC, CSV sources et empreintes sont conservés. Le champ de vent
en relief et l’humidité du combustible ne sont pas calibrés par ces données.
Voir le [contrat météo](../pipelines/event_capture/docs/WEATHER.md).

Les 32 tests CPU/OpenUSD du pipeline sont passés dans Colab. Ils ne constituent
pas une qualification du rendu Omniverse. Le moteur d’incendie et de fumée doit
fournir un adaptateur réel pour l’état, les événements, le gel de tous les
producteurs et la reprise ; cet adaptateur est explicitement manquant. Les
Render Products, le profilage GPU, la stabilité mémoire, le ghosting et la
présence de tous les assets visibles restent à qualifier dans Kit compatible.
Le notebook de préparation météo/caméras a également été sauvegardé puis exécuté
dans Colab : quatre cellules de code, zéro erreur. Ses sorties indiquent
explicitement l’absence de qualification GPU et le maintien de l’export suspendu.

Le point d’entrée préparé est `capture_ready.usda`. La scène, ses données et
son calcul restent dans Colab/Drive. **L’export vers le PC reste suspendu**
jusqu’à la fin de ces préparations et validations.

## Sources

- [POI Croix de Justin attribué au PNR du Vercors](https://www.cirkwi.com/fr/point-interet/2199158-la-croix-de-justin)
- [MNT LiDAR HD sur data.gouv.fr](https://www.data.gouv.fr/datasets/mnt-lidar-hd)
- [MNS LiDAR HD sur data.gouv.fr](https://www.data.gouv.fr/datasets/mns-lidar-hd)
- [Descriptif de livraison LiDAR HD IGN](https://geoservices.ign.fr/sites/default/files/2024-09/DL_LiDAR_HD_1-0.pdf)
- [Catalogue WFS officiel Géoplateforme](https://data.geopf.fr/wfs/ows?SERVICE=WFS&REQUEST=GetCapabilities&VERSION=2.0.0)
