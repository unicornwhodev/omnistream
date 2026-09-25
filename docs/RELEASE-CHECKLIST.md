# Release checklist

## Required for every candidate

- [ ] `npm --prefix .\web ci` succeeds on Windows using the configured NVIDIA registry.
- [ ] `npm run check` passes.
- [ ] `npm test` passes.
- [ ] `npm run test:python` passes with a real USD installation, zero skipped USD tests.
- [ ] `npm run test:web` passes.
- [ ] `npm run audit:public` passes from the clean candidate tree.
- [ ] `installer\Build-Release.ps1` creates a source-only archive and SHA-256 file.
- [ ] Freshly extracted archive passes `npm run verify:release -- --strict`, including plugin metadata and no unmanifested files.
- [ ] Archive contains no `node_modules`, `web-dist`, `_build`, Kit binaries/caches, credentials, logs or machine-specific paths.
- [ ] Documentation version, plugin manifest, bridge extension version and package versions agree.

## Required to promote an RC to stable

- [ ] Install from the release ZIP on a clean or representative Windows RTX machine.
- [ ] Use the intended **Production** NVIDIA runtime channel, or document the exact approved Existing project.
- [ ] `installer\test.cmd` passes without skip flags.
- [ ] `validation-report.json` has `ok: true`, `runtimeSmokeSkipped: false`, `kitTestsSkipped: false`.
- [ ] Real Codex panel shows a decoded RTX/WebRTC frame.
- [ ] Viewport pointer/keyboard input is verified.
- [ ] Configure → Preflight → Launch → Supervise → Control works on an operator-supplied real USD.
- [ ] `npm run test:physics` observes an actual displacement on the intended PhysX configuration.
- [ ] Current-scene edit / preview / apply / watch / undo / export is verified on a real USD.
- [ ] Safe runtime stop leaves no managed process/listener behind.
- [ ] Repair/resume is exercised once.
- [ ] Uninstall preserves the external NVIDIA project and removes only selected OmniStream-owned paths.

## Public/open-source release administration

The repository currently declares the web package **UNLICENSED** and does not ship a project licence file. Before a public open-source/competition submission, the project owner must deliberately choose and add the intended licence. Do not infer or add an open-source licence automatically because that decision changes redistribution rights.

## Vérification publique RC3

- [ ] Aucun USD d’exemple installé automatiquement ; workspace vide.
- [ ] Aucun résultat de test ni transport de remplacement importé par le front de production.
- [ ] Aucun état connecté/chargé/vidéo active déduit d’un simple champ ou port.
- [ ] Capture TRS fondée sur le prim réel ; aucune animation préremplie.
- [ ] Source manquante et bridge absent produisent des erreurs utiles et des commandes désactivées.
- [ ] Les formulaires ne changent pas pendant une actualisation de supervision.
- [ ] Confirmer et annuler les dialogues dans le véritable hôte Codex.
- [ ] Ne pas publier la RC comme stable ni open source avant les gates techniques et la licence.
