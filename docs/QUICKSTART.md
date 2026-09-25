# Quick start

> RC3 : pour le travail dans la scène déjà ouverte, les nouveaux outils physiques/animation, la télémétrie et leurs limites, consulter [Scène ouverte et debug](LIVE-SCENE.md). Le cycle ci-dessous décrit le runtime et les outils historiques.

## 1. Extract and install

On the Windows RTX machine that will run Omniverse Kit, extract the OmniStream release to a normal local folder and run:

```bat
installer\install.cmd
```

The installer verifies the release manifest before copying source files. It then checks Node/npm, Git and the NVIDIA driver. NVIDIA Kit/WebRTC components are **not bundled**: when they are missing, OmniStream opens or invokes the official NVIDIA acquisition/setup path, waits for the operator to complete any NVIDIA terms/login/template steps, validates the resulting local project, and resumes.

For a product-oriented installation choose **Production** when prompted. Choose **Existing** only when you already have a compatible Kit project. Use **Feature** for development/prototyping rather than qualification.

## 2. Let installation qualification finish

A normal install ends by running the product validation script. A locally qualified installation must finish with:

```text
VALIDATION OMNISTREAM: PASS
```

The machine-readable report is stored at:

```text
%LOCALAPPDATA%\OmniStream\state\validation-report.json
```

If the runtime smoke was skipped, the installation is usable for diagnosis/development but is **not qualified stable** until `installer\test.cmd` succeeds without skip switches.

## 3. Load the local plugin in Codex

The default installed plugin root is:

```text
%LOCALAPPDATA%\OmniStream\plugin
```

Load/import that local plugin in Codex, then open **OmniStream for Codex**.

## 4. Ouvrir votre vraie scène

L’installateur ne crée aucun contenu d’exemple. Le workspace utilisateur reste vide. Placer un USD de confiance dans le workspace configuré. Ne pas ouvrir un fichier inconnu sans en vérifier les dépendances/extensions.

Dans **Configurer**, sélectionner le workspace puis utiliser **Scanner**, ou saisir le chemin réel de votre fichier. Valider la configuration. Dans **Lancer**, examiner le préflight puis lancer lorsque les vérifications requises sont satisfaites. Un port de signalisation disponible ne prouve pas qu’une image est reçue. Attendre l’apparition réelle de votre scène dans le viewport.

Dans **Scène**, inspecter les objets actuels avant toute modification. Les contrôles physiques sont conditionnés à la capacité réelle de l’application Kit. Dans **Contrôler**, utiliser lecture, pause, arrêt, frames et seek ; la cadence cible ne promet pas de dilatation temporelle du solveur. **Superviser** et **Diagnostic** séparent état runtime, vidéo, bridge, scène, logs et mesures.

Si aucune scène ni mesure n’est disponible, l’interface l’indique au lieu de la remplacer par une donnée de démonstration. Les corrections de scène restent en session : exporter avant d’arrêter Kit. L’enregistrement de caméra est une écriture source distincte et explicitement confirmée.

## 5. Recover if something fails

```bat
installer\diagnose.cmd
installer\repair.cmd
installer\test.cmd
```

`repair.cmd` reuses the existing external Kit project and does not delete or redownload NVIDIA software. See [Troubleshooting](TROUBLESHOOTING.md) for failure-specific guidance.
