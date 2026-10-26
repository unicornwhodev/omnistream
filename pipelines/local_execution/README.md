# Local scene recovery and capture offload

This directory prepares local execution while retaining the complete original
scene. It is not a qualified wildfire simulator or a replacement for the real
simulation adapter in `pipelines/event_capture`.

## Full scene recovery

`restore_drive.py` reads `metadata/delivery.json`, `scene-files.json` and a
private Drive file index. A dry run is the default. `--execute` copies only the
manifest-listed IDs, one archive at a time, using an independently authorized
rclone configuration. It verifies the archive and every extracted file before
consuming that one local ZIP. It never moves, deletes or changes sharing of
Drive originals. Existing differing files stop recovery.

```powershell
python pipelines/local_execution/restore_drive.py --workspace <private-work-dir> --rclone <rclone.exe> --config <private-config> --remote <authorized-remote>
# Add --execute after inspecting the generated restoration-plan.json.
```

The full map remains on disk. Plan for its full uncompressed size, the largest
single transfer archive, runtime caches, a bounded capture spool and the disk
reserve. The default reserve is 16,000,000,000 bytes. A reserve is checked again
during extraction. Every restored archive has a verification receipt; a final
audit verifies all original files again.

Recovery runs with Windows background CPU, disk and memory scheduling. The
default download cap is 8 MiB/s; hashing and extraction are paced at 32 MiB/s of
accounted logical bytes. This does not cap all system disk traffic or the
compressed-source reads performed by the ZIP library. One transfer and one
checker are allowed. A shared OS lock prevents recovery and the bounded runtime
launcher from running together when they use the same private workspace.
Other applications are not modified.

Use `--max-archives 1` for a bounded recovery step. A
`stop-restoration.request` file in that workspace stops at an archive boundary.
Recovery checks an 8,000,000,000-byte available-host-RAM floor before work and
before each archive. Resuming rehashes completed files; this audit is also paced
and can take several minutes. These checks cannot diagnose the cause of a prior
desktop freeze or prove that every source of host pressure has been eliminated.

Drive backend initialization can fail with a transient API request quota before
rclone's normal transfer retries begin. The downloader records private attempt
receipts and retries at most four times, waiting 30, 60 and 120 seconds. It does
not retry authentication, storage or daily-quota failures. A partial archive is
retained for inspection. Stop requests and host-memory/disk floors are checked
throughout backoff. Each transfer also has a 900-second wall deadline.

## Capture offload contract

`VerifiedSpool` copies explicit completed bundles, reads back their actual
remote bytes through SHA-256, writes local and cloud receipts, then removes
only the listed local capture/demo media. Failed transfers, quota errors,
missing files, corruption and changed local content preserve the local copy.
There is no cloud `sync`, `move`, `delete` or `purge` operation.

The default spool limit is 512,000,000 bytes. The producer must call `capacity`
with a conservative complete-group size before rendering. It includes retained
metadata and partial files in the budget. Metadata and checkpoints remain local;
the limit intentionally stops a long run if those accumulate. Long-duration
metadata compaction remains a production gate.

`offload_group` accepts the existing five-camera group receipt. Call it only
after the scheduler checkpoint has committed and while propagation, smoke and
all other state producers remain frozen. Merely pausing the Omniverse timeline
does not meet that contract. This hook is not yet connected to a qualified
production fire adapter. Do not start a long run using this module alone.

`spool_adapter.make_offloader` now connects the spool to `CapturePipeline` through
the optional `offload_factory` argument of `run_in_current_kit`. Add this directory
to the runtime's Python import path and use `spool_adapter:make_offloader`.
The private configuration's `local_offload` section supplies `rclone_executable`,
`rclone_config_path`, `remote`, `folder_id`, `max_spool_bytes` and `reserve_bytes`.
It contains no raw credentials. Do not publish that private configuration.

Admission happens before each five-camera group, including when ten zones are
due at one simulated instant. After a group commits, the checkpoint records its
pending cloud transfer before any local image can be pruned. Upload and full
SHA-256 readback run with Render Products disabled and all producers frozen.
Only then is the pending checkpoint cleared. A transfer failure exits the
capture loop without advancing simulated time. The real adapter must keep
external producers stopped when that loop exits; it must not automatically
restart them on release of a freeze lease.

On restart, pending transfers are checked before new render products or
simulation advancement. An interruption after local pruning rechecks the cloud
copy, without rerendering. Changing or omitting the destination policy on resume
is refused. Cancellation drains the transfer worker before releasing the lease.
An independent 150-second readback timer terminates a stalled owned rclone
process; a blocked stdout read cannot bypass the deadline.

Use a private rclone config, never a token in a command line or repository.
The OAuth scopes are `drive.readonly,drive.file`: read existing source
files and create/manage app-created output. Confirm the account before using
it, and root output operations at the designated folder ID. No broad existing
file write scope is required by these scripts.

## Local render constraints

`render_profiles.json` selects **1920 x 1080 native captures** by default
(`full_hd`). `hd` is 1280 x 720. The optional `qhd` profile is 2560 x 1440 and is
reserved for an explicit trial after Full HD stability has been measured. No
automatic escalation is implemented. These local profiles deliberately do not
include 4K. The factory's existing cloud qualification configuration remains
unchanged.

`probe_factory_vfx.py` reads the selected profile from its private context's
`render_profile` key, or uses `full_hd` when omitted. It creates one active
capture Render Product at a time and verifies actual saved image dimensions.
This reduces image pixels by 75% compared with 3840 x 2160; it is not a promise
of a proportional speed or VRAM improvement. Flow grid resolution, physical
dimensions, simulated timing and the complete terrain are not reduced by this
pixel profile.

The OmniStream monitoring target is 1280 x 720 at up to 30 fps, independently of
the native capture target. `minimal_runtime.kit` uses this viewport resolution.
The profile documents the intended stream settings; the plugin session and
actual decoded stream still need to be configured and measured at launch.
Resolution alone does not qualify flame/smoke physics or fix loading pressure.

The native qualification app limits Carbonite and TBB to four workers and PhysX
to two. It disables the automatic default viewport; the optical probe explicitly
attaches the RTX Hydra engine before creating Render Products. Advancing the Kit
timeline without that engine is not rendering evidence. The CPU controls follow
the [Isaac Sim performance handbook](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/reference_material/sim_performance_optimization_handbook.html#cpu-thread-count-optimizations).

The current requested resource ceilings are 15,000,000,000 bytes of VRAM and
12,000,000,000 bytes of process-tree RAM. `bounded_process.py` assigns the suspended
child to a Windows Job Object with an 11,500,000,000-byte committed-memory limit
(rounded down to whole Windows memory pages),
reads that limit back, and only then resumes it. Child processes remain in the
job. Admission additionally requires the job budget plus 4,000,000,000 bytes of
available host RAM; a host RAM floor is checked while it runs. Committed memory
and sampled resident memory are recorded separately.

An additional preventive stop defaults to 9,000,000,000 bytes of peak Job
commit (or 80% of a smaller hard limit). A hard allocation refusal by itself
caused LLVM to fail and the graphics device to be lost in a previous trial.
The monitor also stops at 10,500,000,000 bytes of resident process-tree memory,
and scans bounded increments of the owned child's logs for fatal renderer
errors. These are preventive watchdogs; an interrupted run is never a pass.

VRAM is sampled for the whole GPU every 100 ms and the owned job is stopped at
14,000,000,000 bytes. This reserves headroom below the requested 15 GB, but is a
watchdog, **not a hard GPU allocation cap**; fast allocation can overshoot between
samples. Production remains conditional on native resource measurements. A
texture budget alone is not a VRAM ceiling.

The installed renderer exposes `MinimalRendering` and `/rtx/minimal/mode=3`
(diffuse, glossy and emission). This retains emissive materials; mode 2 only
uses diffuse textures. Native Flow/volume support, memory stability and flame/
smoke physics have **not** been qualified in this local configuration.

The earlier Kit 110.2 installation did not resolve the needed Replicator package.
The isolated preparation now uses the modular Isaac Sim 6.1 kernel/application
packages (Kit 110.3), without installing the complete robotics package set.
`run_kit.py` uses the environment's Python and KitApp bootstrap: the pip kernel
does not contain the standalone embedded Python layout expected by a direct
`kit.exe` launch. Extension precaching is separate from a native render test.
NVIDIA's registry can place deduplicated backing packages in its shared user
extension cache and link them into the private cache; those shared packages are
not cleanup targets. A successful extension resolution is not a Flow/RTX or
physics qualification.

Production RGB images must come from native scene Render Products. An
OmniStream screenshot or demo video proves streaming/control and is not used
as a synthetic training image or physics validation.

## Faster execution and reduced periodic capture rate

`prepare_capture_config.py` derives a separate local configuration from the
original delivered file, retaining the 50 camera poses, zones, weather, seeds,
period, activity observation rules and transition triggers. The current local
target is acceleration **1000**, previously 500, with periodic frequency scaled
by **0.75**. A frequency reduction of 25% means intervals multiplied by 4/3:

| Activity | Original simulated interval | Local simulated interval |
| --- | ---: | ---: |
| Inactive negative sample | 6 h | 8 h |
| Early smoke | 5 min | 6 min 40 s |
| Rapid active front | 1 min 30 s | 2 min |
| Stable active front | 5 min | 6 min 40 s |
| Declining activity | 15 min | 20 min |
| Post-extinction | 30 min | 40 min |

Transitions and initial samples are retained. Consequently, the total number of
images is not guaranteed to fall by exactly 25%; that factor applies to the
periodic rate. The post-extinction observation window and event boundaries are
unchanged. The helper rejects applying the reduction to an already derived
configuration and never overwrites a conflicting output.

```powershell
python pipelines/local_execution/prepare_capture_config.py --source <original-configuration.json> --output <new-local-configuration.json> --acceleration 1000 --frequency-scale 0.75 --render-profile full_hd
```

The 47-day clock divided by 1000 gives a **simulation-only target of 4060.8 wall
seconds (1 h 7 min 40.8 s)**. This is a target, not a runtime estimate: native
physics, frozen-state rendering, file verification, upload and checkpoints have
their own costs. The configuration does not enlarge the physics time step,
skip events, replay the simulation once per camera or fabricate a missing fire
adapter. A missing production adapter remains explicitly missing.

`RunMetrics` reports both measured simulated-seconds per adapter-advance wall
second and simulated-seconds per complete pipeline wall second. The latter
includes pipeline captures/checkpoints but excludes native app startup. Values
cover only progress in the current invocation, including after resume; the
requested acceleration is recorded separately. Rendering GPU time remains
unavailable unless supplied by an actual GPU timing provider.

A changed configuration has a new deterministic run identity. Use a fresh
capture output directory; an existing checkpoint cannot silently switch cadence.
Windows path checks normalize equivalent extended drive/UNC namespaces after
filesystem resolution, while still refusing paths outside the output root.
Started image-writing threads are drained before releasing the frozen state on
failure or cancellation.

## Native initialization and failure evidence

The current short native tests use Kit 110.3 through the isolated Isaac Sim 6.1
kernel/application. They use Vulkan and its matching shader-cache extension.
Download large extension archives to a bounded file stream; buffering a complete
archive during precaching can itself exhaust RAM. Verify CRC/content before
installing the cache and retain the matching version. Do not delete shared
extension-cache backing folders. See NVIDIA's
[Vulkan shader-cache overview](https://docs.omniverse.nvidia.com/kit/docs/omni.hydra.rtx.shadercache.vulkan/latest/Overview.html).

The first native Render Product has an explicit RGB annotator. It is initialized
at zero delta while both Flow simulation and emitters are disabled. A product
with no consumer previously left the first orchestrator step waiting. After
stage loading, `render_policy.py` reapplies and reads back the requested settings;
the Flow extension can re-enable volume inclusion defaults during population.
The policy is checked after every simulation step. The default keeps Flow's
path-traced inclusion flag off. The private-context `flow_volume_gate` option
exists for an explicitly approved diagnostic only; it never selects the
PathTracing renderer or enables PT/RT2 modes.

The probe records both the ordinary timeline and the installed Flow telemetry
nodes, plus direct binding block counts. Their actual contracts are read from
the installed `FlowSimTime` and `FlowBlocks` nodes. Zero solver time/blocks and
missing NanoVDB fields cannot be qualified by successful RGB output. See the
[Flow settings](https://docs.omniverse.nvidia.com/kit/docs/flow/latest/settings.html)
and [current qualification results](QUALIFICATION-STATUS.md).

## Published perimeter and chronology preparation

Install the CPU helpers' dependencies separately from the native Kit environment:

```powershell
python -m pip install -r pipelines/local_execution/requirements.txt
python -m pip install -e pipelines/event_capture
python pipelines/local_execution/prepare_incident_inputs.py --output <new-private-input-directory> --capture-config <local-capture-config.json> --scene-manifest <scene-files.json>
python pipelines/local_execution/project_incident_constraints.py --inputs <private-input-directory> --georeferencing <scene/metadata/georeferencing.json> --output <new-private-constraints-directory>
```

The first command freezes the current public incident archive and verifies every
referenced size/hash. It preserves the complete source period but selects only
the configured simulation window. The second reads those frozen files without
network access, projects their XY geometry into the delivered scene reference
system and records source hashes. It preserves polygon holes, multipart geometry,
feature properties and uncertainty; it reports features outside the scene bounds.
It neither clips evidence silently nor assigns an unmeasured terrain elevation.

The outputs are evidence constraints, not a fire-engine feed. Dated observations,
retrospective reconstructions and carried-forward perimeters remain distinct.
The source's `sourceDate` can precede the daily product's date. Old activity is
cleared on carried extents; absence of a detection is not extinction. Adapter
integration must respect this contract and cannot turn all burned/perimeter
geometry into flames. Conflicting existing outputs stop preparation; use a new
output revision instead of overwriting an audit trail.

## Tests

```powershell
python -m unittest discover -s pipelines/local_execution -p "test_*.py" -v
```

These tests cover file preservation, archive integrity, bounded admission,
transfer failure, remote corruption, idempotent retry with a test backend,
I/O pacing and exclusion between independent worker processes.
They do not demonstrate an authenticated Drive transfer or native Kit physics.
