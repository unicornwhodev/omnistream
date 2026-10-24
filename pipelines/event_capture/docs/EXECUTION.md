# Execution and recovery

Run data preparation and Kit on the authorized Colab environment. Keep raw
rasters, generated assets, observations and intermediate captures there. Export
only the completed, prepared scene when its validation gates have passed.

CPU preparation can use Python 3.11 or newer. The Kit environment must use the
Python version required by its installed NVIDIA runtime; do not upgrade that
environment to match Colab's notebook kernel.

```bash
python -m pip install -e /content/event_capture
python -m fireviewer_capture.cli validate-config examples/reference_50_cameras.json
python -m unittest discover -s tests -v
python -m fireviewer_capture.cli prepare-camera-layer configuration.json cameras.usda
```

Compose `cameras.usda` as a stronger layer over the prepared scene. All camera
positions use local scene metres, Z up. Virtual focal length and sensor size
are specified in millimetres; the USD preparation converts them into tenths
of scene units. The JSON example is not suitable for direct scientific use
until camera heights, placement, visibility and scene revision are checked.

Use the compatible Isaac Sim environment's interpreter to run:

```bash
python tools/run_in_isaacsim.py --config configuration.json \
  --scene capture_ready.usda --output /content/captures/scenario-001 \
  --adapter-factory my_engine_capture:create_adapter
```

`my_engine_capture:create_adapter` is an example **user-supplied import target**,
not a supplied API. It must return an implementation of `SimulationAdapter`.
The script does not accept a new NVIDIA agreement and does not install Kit.
Use the compatible runtime and existing recorded approval. It refuses local
PC execution for this Colab scenario. The same runner can be awaited inside an
existing Kit application, without creating another application:

```python
from fireviewer_capture.runner import run_in_current_kit
await run_in_current_kit(config_path, output_dir, adapter_factory=adapter_spec)
```

`--fixture-log log.json` is restricted to a USD stage explicitly marked
`qualification:fixture=True`. It tests recorded state playback and actual Kit
rendering; it cannot stand in for a live propagation/smoke integration. A real
terrain stage is never automatically marked as a fixture.

One writer process owns an output directory. Do not run two processes into the
same directory. Output names derive from configuration, state, zone and camera.
The checkpoint stores the exact pending instant before writes begin. A restart
restores adapter, tracker and scheduler. Verified earlier images are reused
without rendering; corrupt or partial slots are moved to `quarantine/` and
replaced. A changed seed, configuration or scene revision requires a new output
directory. A fresh run must begin at simulated zero.

```bash
python -m fireviewer_capture.cli verify-output /content/captures/scenario-001
```

Files are decoded/validated, hashed and read back before group commit. Consumers
must enumerate `groups/*.json` and verify each image/metadata checksum. An image
without a committed group remains provisional. Do not edit accepted metadata
in place. A filesystem crash/fsync guarantee still depends on the underlying
storage; retain verified checkpoints and backups on Drive.

For a tiled geographic scene, prepare visibility-complete asset residency
before a batch. The interactive near-camera 25-tile policy is not a scientific
capture policy: distant visible forest must not disappear to meet a memory
limit. A capture residency provider must either load all required assets/LODs
or refuse the batch; it must not silently drop visible assets. This provider
and its memory budget must be qualified with the actual terrain.
