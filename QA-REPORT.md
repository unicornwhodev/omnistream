# OmniStream 1.0.0-rc3 — rapport de vérification

## Verdict

Passe de refonte et de durcissement réalisée sur la RC2. Le parcours utilisateur ne contient plus de scène installée automatiquement, animation préremplie, état de connexion inventé ou rendu de remplacement. **Cette conclusion porte sur le code et le parcours observé sans Kit ; elle ne certifie pas une simulation native ou une vidéo RTX qui n’ont pas été exécutées ici.**

## Résultats exécutés

| Contrôle | Résultat et portée |
|---|---|
| `npm run check` | PASS : syntaxe des modules Node + TypeScript application/Vite. Dépendances de contrôle récupérées de l’archive fournie, pas d’une installation propre. |
| `npm test` | PASS : suite MCP historique ; 12 tests scène/événements ; 12 tests d’intégrité publique ; contrats source du panneau ; 7 tests de distribution. |
| `python -m unittest discover -s tests -v` | 32 tests trouvés : **17 PASS, 15 SKIPPED**, aucun échec. Les 15 skips nécessitent le véritable `pxr`/OpenUSD absent ici. |
| Syntaxe Python bridge | PASS : cinq modules compilés syntaxiquement, sans prétendre importer Kit. |
| Formatage du front | PASS : contrôle Prettier du source TSX, CSS et utilitaire MJS. |
| Contrats source du panneau | PASS : mode `--source-only` explicite, ne remplace pas le contrat du bundle. |
| `npm run test:web` | **BLOQUÉ/ÉCHEC D’ENVIRONNEMENT** : Vite ne charge pas `@rollup/rollup-linux-x64-gnu`, absent des dépendances Windows fournies. Le build et le contrat du bundle ne sont donc pas validés. |
| Installation propre des dépendances | Non validée : tentative réseau sans résolution/accès sortant utilisable. Ni le lockfile ni le SDK ne sont annoncés installés de zéro ici. |
| Audit de diffusion / manifeste | Exécutés séparément sur un arbre nettoyé puis une archive réextraite ; voir les commandes de reproduction ci-dessous. |

Les tests unitaires du protocole utilisent des clients doubles pour certaines réponses Kit et des données de test isolées. Ces tests sont présentés comme tels ; ils ne constituent pas la preuve d’une simulation physique. Le test navigateur de cette RC n’utilise pas de réponses Kit/WebRTC fictives.

## Navigateur : méthode et preuves

Plugin Browser absent ; Playwright a utilisé Chromium système en mode headless. La navigation HTTP locale est refusée par la politique du navigateur dans cet environnement. Le document a donc été chargé par `set_content`, avec le vrai source TSX transpillé pour ce contrôle et les vraies bibliothèques React/SDK NVIDIA disponibles localement. Ce chargeur CommonJS de contrôle est extérieur à la release : ce n’est pas un build Vite distribué.

Premier parcours : aucun hôte. Les six surfaces s’affichent, les actions runtime sont désactivées, le viewport explique la connexion manquante, les mesures restent inconnues. Aucun asset, objet ou animation de démonstration n’est généré.

Deuxième parcours : le vrai `mcp/server.mjs` tourne dans un processus Node. Un adaptateur IPC réservé au test relie les appels du panneau à son protocole JSONL natif. Aucun statut de runtime, contenu de scène, réponse d’outil ou frame WebRTC n’est fabriqué. **Ce n’est toutefois pas le véritable hôte Codex.**

Vérifications obtenues : workspace réellement vide retourné vide ; paramètres saisis non effacés après plusieurs polls ; chemin d’un fichier absent refusé par le contrôleur ; ce chemin n’apparaît jamais comme stage chargé ; navigation des six vues ; arrêt réel du processus MCP reconnu comme contrôleur indisponible. Pas d’erreur ou warning console sur ce parcours. Les erreurs de transport après fermeture du processus sont attendues et affichées par le panneau.

Dimensions contrôlées : **1440×1000, 820×900, 420×900 et 360×800**. Pas de débordement horizontal. À 420 px, contrôle géométrique après navigation : barre sticky terminant à 63 px, en-tête inspecteur commençant à environ 72 px, donc sans recouvrement. Les captures full-page prises après un défilement peuvent replacer une barre sticky ; la capture viewport est la preuve de sa position réelle à l’écran.

## Revue visuelle

Comparaison du front RC2 fourni et du rendu RC3, pas avec l’ancienne image de dashboard API rejetée. Points inspectés :

1. Navigation : rail dédié au lieu d’une grille de petits onglets dans l’inspecteur.
2. Composition : viewport dominant, transport immédiatement dessous, contrôles dans un inspecteur séparé.
3. Typographie : titres, labels, boutons et statuts différenciés ; labels du rail desktop agrandis après revue.
4. Couleurs : graphite et gris neutres, vert d’action/état ; pas de panneaux kaki décoratifs.
5. États : absence d’hôte/runtime visible, aucune scène ou caméra supposée, valeurs inconnues explicites.
6. Responsive : nav horizontale aux petites largeurs, champs empilés, inspecteur atteignable sans débordement.
7. Libellés : « cadence cible » conservé, sans promesse de vitesse physique ; « vidéo active » ne découle pas de la signalisation.

Les changements de texte et de navigation sont intentionnels et liés au vrai produit. Aucune maquette générée, statistique décorative ou carte d’API ne sert de référence. Les écrans avec objets/vidéo actifs restent à contrôler dans Kit.

## Corrections fonctionnelles vérifiées dans le source

Gestion explicite des erreurs/objets vides dans les réponses MCP ; détection de l’hôte et de sa perte ; protection des brouillons contre la supervision ; verrou partagé des actions de scène ; temporisation/expiration de l’aperçu ; confirmations natives au panneau ; erreur React visible plutôt qu’écran vide ; enregistrement caméra et fermeture avec risque de perte explicitement confirmés.

Les deux assets inutilisés du squelette web (favicon générique violet et sprite d’icônes de réseaux sociaux) ont également été retirés. Ils ne participaient à aucune fonction du produit.

Le bridge écrit effectivement la désactivation d’un collider existant. Une inspection tronquée ne déclare plus à tort l’absence d’une scène physique et bloque le lancement automatique borné. La capture de pose retourne uniquement une TRS simple reconnue ; les piles complexes sont refusées. Des tests OpenUSD correspondants existent mais sont dans les **15 skips natifs**, pas dans les succès locaux.

## Diffusion

L’audit teste maintenant l’arbre réel, refuse les binaires (au lieu de les ignorer), dépendances, archives, liens symboliques, octets nuls cachés dans le texte et gros sources sans revue. Le script Windows archive via .NET pour conserver les métadonnées cachées, puis contrôle leur présence. Le manifeste vérifie tailles/SHA-256 ; `--strict` refuse des fichiers supplémentaires. **Les hashes ne sont pas une signature numérique.**

Sur une extraction propre :

```powershell
npm run audit:public
npm run verify:release -- --strict
```

Après acquisition locale des dépendances sur la bonne plateforme :

```powershell
npm run check
npm test
npm run test:python
npm run test:web
installer\test.cmd
npm run test:physics
```

## Reste à qualifier

Installation/réparation/reprise/désinstallation PowerShell ; installation propre et build Vite de production ; import et édition OpenUSD réels ; Kit/PhysX ; décodage et interactions WebRTC dans le vrai Codex ; jeux de données volumineux et extensions tierces. La CI Windows fournie n’a pas été exécutée depuis cet environnement. La sécurité testée n’équivaut pas à un audit indépendant.

Ces limites justifient **RC3**, pas une promotion artificielle en stable. La licence du produit reste `UNLICENSED` ; aucune publication de catalogue ni modification des droits n’a été effectuée.
