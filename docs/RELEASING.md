# Versions, tags et distribution

## Identité de version

La version courante est `1.0.0-rc3`. Elle doit rester cohérente entre `package.json`, `web/package.json`, `.codex-plugin/plugin.json`, l’extension OmniStream Bridge et `release-manifest.json`. Le suffixe `-rc3` désigne une candidate, pas une certification stable.

Les tags Git suivent la forme `v<version>`, par exemple `v1.0.0-rc3`. Un tag doit pointer sur le commit examiné et qualifié pour cette version. La [checklist de release](RELEASE-CHECKLIST.md) fixe les contrôles avant un tag de candidate ou la promotion vers `1.0.0`.

État au 29 septembre 2026 : le dépôt n’a pas encore de tag GitHub, de GitHub Release ni de package publié dans un registre. Une archive candidate peut être construite localement ; le présent document ne présente pas cet artefact local comme un téléchargement public.

## Artefact à télécharger

OmniStream fournit une archive Windows source-only, pas un runtime NVIDIA précompilé. Pour la construire depuis la racine du dépôt :

```powershell
.\installer\Build-Release.ps1
```

Le résultat est placé dans `release/` sous la forme `omnistream-for-codex-<version>.zip` et `omnistream-for-codex-<version>.zip.sha256`. Le ZIP contient le source OmniStream, l’installateur, les tests et la documentation. Kit, le SDK WebRTC NVIDIA, leurs caches et le bundle du panneau sont obtenus ou construits sur le poste cible.

Après extraction, vérifier le manifeste strict :

```powershell
npm run verify:release -- --strict
```

Le SHA-256 et le manifeste attestent l’intégrité des fichiers par rapport aux valeurs fournies ; ils ne constituent pas une signature numérique ni une certification de provenance.

## Packages de registre et licence

`package.json` décrit le dépôt, ses mots-clés, son support et son périmètre. Il garde `private: true` et `license: UNLICENSED`; aucun package npm n’est publié. Ne pas retirer cette protection ni attribuer une licence sans la décision du titulaire des droits. La visibilité publique du dépôt ne concède pas de droits de réutilisation ou de redistribution.

Une GitHub Release de candidate doit être marquée **Pre-release**, utiliser un tag correspondant à la version et joindre le ZIP ainsi que son fichier `.sha256`. Ne pas annoncer de release stable tant que les gates de [validation](VALIDATION.md) et de [licence](PUBLIC-DEPLOYMENT.md) ne sont pas franchies.

## CI

Le dépôt ne contient actuellement aucun workflow GitHub Actions versionné. Les commandes de source et d’installation doivent donc être décrites comme des contrôles locaux jusqu’à ce qu’un workflow soit ajouté et qu’une exécution soit observée.
