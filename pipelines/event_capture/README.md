# FireViewer event capture pipeline

Independent Python capture package for one shared simulation and fixed groups
of five USD cameras. There are no FireViewer backend imports or service calls.
This revision provides the scheduling, storage and Replicator integration
source. A native Colab L4 geometric fixture has exercised the driver, recovery
and short resource matrix. **Actual Justin/fire rendering, GPU execution
profiling and a production fire/smoke adapter are still required.**

| Module | Responsibility |
|---|---|
| `SimulationAdapter` | Actual engine state, event boundaries, advance, verified freeze of every producer, deterministic checkpoint/restore |
| `ZoneActivityTracker` | Spatial margins, temporal hysteresis, short smoke pulses, front crossings, post-extinction windows |
| `CaptureScheduler` | Simulated intervals, same-instant coalescing, transitions, priorities and negative samples |
| `ReplicatorCaptureManager` | Fixed cameras, bounded Render Products, explicit writers, frozen capture groups, verified files and cleanup |

See [execution](docs/EXECUTION.md), [adapter contract](docs/ADAPTER.md),
[weather](docs/WEATHER.md) and [qualification](docs/QUALIFICATION.md).
The complete [50-camera example](examples/reference_50_cameras.json) is an
explicit virtual design, not a surveyed installation. Replace it with a
verified scene configuration. `tools/prepare_geographic_cameras.py` can derive
camera heights and sampled terrain visibility from the native official DEM;
that alone does not validate vegetation occlusion or full zone coverage.

The default period is 47 days, 24 June to 10 August 2026 exclusive, in
Europe/Paris. Acceleration is configurable from 250 to 1,000. RGB resolution is
1,280 × 720. All scheduling intervals are simulated seconds; monotonic wall
time is used only for performance metrics, writer timeouts and resource sampling.

| State | Default simulated interval |
|---|---:|
| Inactive | 6 hours; also initial negative sample |
| Early smoke | 5 minutes |
| Rapid active front | 90 seconds |
| Stable active front | 5 minutes |
| Declining activity | 15 minutes |
| Post-extinction | 30 minutes during a configurable 6-hour window |

Every raw entry/exit and activity transition also triggers a sample. These
defaults are data in the configuration, not constants in the scheduler.
An active front never implies a visible flame in a particular image. Camera
visibility annotations remain null unless a named source supplies them.

One frozen lease covers all requests at one instant. With a product cap of
two, a five-camera group renders as 2 + 2 + 1 while the state stays frozen.
The default active cap is five and the cache cap ten. Inactive products have
updates disabled. Writers attach with `trigger=None`, are scheduled explicitly,
and render through `step_async(delta_time=0.0)`. No main viewport rotation is
required. Source camera layers are prepared separately from rendering.

Per-image metadata follows the [JSON schema](schemas/capture-image.schema.json).
It records source state/provenance, camera matrices and intrinsics, weather,
render configuration, deterministic identifiers and SHA-256. Only a verified
five-image group manifest makes a group usable. File existence alone does not.

The current normalized weather preparation retains official observations and
ECMWF estimates separately. Live integration must select its source explicitly;
missing station values are not silently replaced by model values.
