# Validation

OmniStream separates **source qualification**, **installed-runtime qualification**, and **visible Codex proof**. No single PID, port, build or unit test is presented as evidence for all three.

## Source gate

After `web` dependencies have been obtained on Windows:

```powershell
npm run check
npm test
npm run test:web
.\installer\Build-Release.ps1
```

| Command | Evidence | Launches Kit / writes USD? |
| --- | --- | --- |
| `npm run check` | Node syntax plus real TypeScript/Vite panel type checks. | No. |
| `npm test` | MCP descriptors/protocol, simulation contracts, atomic launch guard, loopback auth, path policy, redaction, safe stop and source-only behavior. | No. |
| `npm run test:web` | Builds the real panel, validates its MCP resource/bundle contract, then removes generated test output. | No Kit / no USD. |
| `npm run audit:public` | Verifies publication scope excludes generated/dependency/runtime material, local paths and common secret patterns. | No. |

No GitHub Actions workflow is currently versioned in this repository. Until a workflow is added and a run is observed, report these commands as local source checks rather than CI evidence.

## Installed product gate

Run:

```bat
installer\test.cmd
```

`Test-OmniStream.ps1` performs, in order:

1. source + TypeScript contracts;
2. MCP/security tests;
3. panel build/resource contract;
4. final panel build;
5. strict environment/configuration doctor;
6. NVIDIA project `repo.bat test` unless explicitly skipped;
7. real `npm run test:runtime` unless explicitly skipped.

The result is written to:

```text
%LOCALAPPDATA%\OmniStream\state\validation-report.json
```

The runtime smoke exercises the product workflow against real Kit:

**Configure → Preflight → Launch → Supervise → Read bounded logs → Control → Camera navigation/save → Safe stop**.

It verifies credentials are not exposed in ordinary structured results/log diagnostics and uses a temporary USD fixture rather than modifying a user scene.

The runtime smoke command is available locally, but no self-hosted GitHub Actions workflow is currently versioned in this repository.

## RC → stable promotion gate

`1.0.0-rc3` must remain an RC until all of the following are true on the intended target machine:

- `installer\test.cmd` passes with **no skip flags**;
- a decoded RTX/WebRTC frame is visible in the Codex panel;
- focused pointer/keyboard input reaches the live Kit viewport;
- the Simulation Deck can configure, preflight, launch, supervise and control a real stage deliberately supplied by the operator;
- safe runtime stop leaves no managed Kit process or signaling listener behind;
- repair + rerun retains normalized configuration and external NVIDIA ownership boundaries.

Only after that evidence should the version be promoted to `1.0.0`.

## Manual Codex visual gate

Automated runtime tests still do not prove that a particular Codex Desktop build actually rendered the embedded video. Verify:

1. `ui://omnistream-for-codex/panel.html` loads after the local panel build.
2. Config validation does not start Kit.
3. Launch reaches ready states for managed process, signaling, authenticated bridge and selected stage.
4. Supervision updates while runtime/timeline state changes.
5. The connection overlay disappears after a decoded RTX frame is received.
6. Play/pause/reset/step/seek/rate/loop operate without terminating Kit.
7. Viewport input works after focus.
8. Runtime stop completes cleanly.

Record this separately from the machine-readable validation report.


## Gates supplémentaires RC3

`npm test` comprend les 12 tests Node des nouveaux contrats, du cache et du multiplexage d’un véritable socket local authentifié. `npm run test:python` exécute 17 tests Python indépendants de Kit et 15 tests supplémentaires nécessitant un vrai `pxr`. En l’absence de `pxr`, ces quinze tests sont **SKIPPED**, jamais considérés réussis. Aucun workflow de CI n’est actuellement versionné ici ; il n’y a donc pas de résultat CI courant à attribuer à cette candidate.

Le smoke runtime comprend désormais aperçu/application/annulation d’une animation USD et surveillance avec limite locale de durée. `npm run test:physics` ajoute un essai de chute dont le déplacement doit être observé dans le USD. Il échoue sans capacité PhysX ou sans remontée USD du mouvement. Un moteur utilisant seulement Fabric exige un autre adaptateur de mesure.

Le rapport PowerShell distingue explicitement les contrôles automatiques de `visualWebRtcVerified`, `codexHostVerified` et `productionReady`, laissés à false : les scripts ne s’attribuent pas une certification visuelle. Le succès automatique n’est pas à lui seul une promotion stable.

Voir `QA-REPORT.md` pour les résultats effectivement obtenus, les versions locales et les validations non exécutées.

## Contrôles publics RC3

`npm test` inclut aussi 12 tests d’intégrité des états/interface et 7 tests de distribution (rejets de binaires, octets nuls, dépendances, gros fichiers et liens symboliques ; contrat de packaging Windows). `npm run test:panel-source` vérifie le source sans prétendre vérifier un bundle. `npm run test:web` garde le build Vite et les contrôles du vrai bundle comme étapes obligatoires distinctes.

Le banc navigateur RC3 a utilisé le vrai source React et le vrai SDK NVIDIA local, d’abord sans hôte, puis avec le vrai processus MCP par un adaptateur IPC réservé au test. Aucun résultat de scène/Kit/WebRTC n’a été fabriqué pour ce contrôle. Cela prouve le parcours sans runtime et les erreurs effectives, pas l’édition dans Kit ni la vidéo. Voir le rapport de cette livraison.
