# Qualification des VFX existants dans Isaac Sim

Ce banc travaille sur les recettes Flow existantes de la factory. Il conserve
leurs sources et leurs empreintes. Chaque essai écrit une révision séparée sur
Colab/Drive. Aucun chargement de carte Die–Justin, pilote géographique ou export
d'assets vers le PC n'est nécessaire.

Le protocole ci-dessous décrit le banc cloud initial. Le chantier a ensuite été
déplacé vers une exécution locale bornée ; voir le
[bilan local actuel](../local_execution/QUALIFICATION-STATUS.md). Ce déplacement
ne transforme pas les anciens essais en validation physique acquise.

Le moteur utilisé est NVIDIA Flow dans Isaac Sim : une simulation eulérienne
sur grille volumétrique creuse. Les contrôles portent sur les champs réellement
produits : apparition, flottabilité, déplacement sous vent imposé, extinction,
interaction avec un sol de référence, stabilité numérique et gel des volumes.
Les images natives confirment séparément la visibilité des flammes et fumées.

## Limites des conclusions

Une recette rendue ne constitue pas une calibration thermochimique. Les champs
Flow `temperature`, `fuel`, `burn` et `smoke` gardent leurs unités de modèle.
Ils ne sont pas renommés en kelvins, kilogrammes ou puissance thermique. La
direction de flottabilité et la gravité PhysX sont deux paramètres distincts.
Les dimensions observées, paramètres imposés, résultats du solveur et mesures
optiques restent identifiés séparément.

Le profil `flow-response-v3` produit des opinions USD dérivées : vent ambiant
sans vitesse verticale artificielle, source sans jet ascendant imposé,
flottabilité thermique, pas du solveur fixe, collisions Flow/PhysX et source
au-dessus du sol. Le test froid coupe chaleur et combustion. La suppression
sous le sol est désactivée pour ne pas confondre effacement et collision.
Ces corrections doivent passer les essais natifs avant activation dans la
factory. Les recettes d'origine restent disponibles.

## Contrôles

- Métadonnées : identifiant de recette, SHA-256 des sources et du code, seed,
  versions Isaac/Flow, mètres/Z-up, pas physique, paramètres du test.
- Grilles : données NanoVDB natives, valeurs finies, support, centroïde et
  enveloppe en mètres ; intégrale exprimée en unités du modèle × m³.
- Réponse : comparaison chaud/froid, inversion du vent, arrêt des émetteurs,
  décroissance, sensibilité au pas et au maillage ; aucun résultat fictif si
  le runtime ne permet pas de lire le champ demandé.
- Gel : pause de la timeline, arrêt explicite du solveur et des émetteurs,
  vidage de la lecture asynchrone et comparaison des empreintes de grilles.
- Rendu : simulation à faible coût de prévisualisation, captures finales
  natives 3840 × 2160 à temps gelé, lecture et SHA-256 vérifiés.
- Ressources : durées de simulation/rendu/écriture séparées, RAM, VRAM,
  refus des résultats incomplets et conservation des preuves d'échec.

Les tests Python des métriques ne qualifient pas Isaac. L'acceptation demande
des exécutions natives, des champs mesurables et des preuves visuelles.

## Installation privée

Utiliser le compte Colab autorisé, un runtime L4 et l'installation Isaac Sim
5.1 déjà approuvée. Monter le Drive de la factory. Conserver les fichiers de
contexte, autorisations et environnement hors Git. Les scripts lisent leurs
chemins à l'exécution ; aucun compte, identifiant Drive, jeton, clé API ou
paramètre de proxy n'est nécessaire dans le dépôt public.

`inspect_runtime.py --context <contexte-prive.json>` est le premier contrôle
du runtime et de la lecture NanoVDB. Il doit finir avant les séries de mesures.
Il utilise les sources existantes et écrit ses sorties dans le dossier de
qualification du contexte. Le contexte contient seulement `factory_root` et
`qualification_root` et demeure privé.

## Sources techniques

- [Flow : modèle de simulation](https://docs.omniverse.nvidia.com/extensions/latest/ext_fluid-dynamics.html)
- [Réglages Flow et export NanoVDB](https://docs.omniverse.nvidia.com/extensions/latest/ext_fluid-dynamics/settings.html)
- [Lecture NanoVDB native](https://docs.omniverse.nvidia.com/extensions/latest/ext_omnigraph/node-library/nodes/omni-flowusd/flownanovdbreadback-1.html)
- [Lecture des volumes avec Warp](https://nvidia.github.io/warp/v1.5/modules/runtime.html)
