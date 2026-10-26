# Local qualification status — 2026-10-26

**Classic RTX now renders real factory Flow flames and smoke in Full HD inside
the local memory budgets.** A ten-second laboratory run with a closed PhysX
ground mesh completes normally. The source factory USD is unchanged. Two frozen
exports have identical smoke and temperature voxel contents and no measured
support below the ground. The public launcher reproduces this result.

**This is a short native laboratory qualification, not the Die terrain or a
calibrated wildfire simulation. The 47-day production run has not started.**
The authorized RTX Real-Time 2.0 trial failed the preventive memory guard; the
successful runs use classic `RaytracedLighting`, with PT and RT2 disabled.
See the [native evidence receipt](evidence/native-flow-collision-20261026.json).

## Memory fault and preventive controls

The earlier Direct3D attempt failed with LLVM out-of-memory errors and graphics
device error `0x887a0005`. Its hard Job limit alone was insufficient to prevent
that failure. The current launcher adds a preventive committed-memory stop,
resident-memory and host-reserve checks, bounded fatal-log scanning and a 100 ms
sampling interval. It terminates only its own process tree.

The earlier Minimal configuration used one warm Slang compiler session, four
Carbonite/TBB workers, two PhysX workers, Vulkan's matching shader cache, no
unused automatic viewport, an explicitly attached RTX Hydra engine and an
explicit RGB consumer before the first Replicator step. The working classic
diagnostic uses the existing Kit 110.2 SDK, Direct3D, two CPU workers, one warm
shader session, native-resolution DLAA and only the necessary Flow/viewport/
PhysX extensions. It does not load the Replicator or Warp stack while rendering.
The separate Warp measurement pass runs after Kit exits. These changes were
tested together; neither Kit version alone nor any individual switch is claimed
sufficient to fix the earlier initialization failures.

The requested ceilings remain **12 GB process-tree RAM and 15 GB VRAM**, decimal
bytes. The OS Job committed-memory limit is 11,499,999,232 bytes, rounded down
from 11.5 GB. Native trials use a 10.5 GB preventive commit threshold and a
10.5 GB resident-memory threshold. Admission requires the Job budget plus 4 GB
available host RAM. The whole-GPU watchdog stops at 14 GB. VRAM and resident RAM
checks are sampled watchdogs, not hard allocation caps; fast growth can overshoot
between samples. These short trials do not certify long-run stability.

| Native trial | Outcome | Peak resident RAM | Peak Job commit | Peak whole-GPU VRAM |
| --- | --- | ---: | ---: | ---: |
| v13, 2 s timeline | Two Full HD PNGs; no visible VFX | 6.799 GB | 9.603 GB | 3.782 GB |
| v14, 30 s timeline | Two Full HD PNGs; no visible VFX | 7.178 GB | 9.972 GB | 3.761 GB |
| v18, Flow diagnostics | No smoke/temperature export | 5.716 GB | 8.265 GB | 3.531 GB |
| v19, ordinary Kit updates | No smoke/temperature export | 5.701 GB | 8.288 GB | 3.505 GB |
| v21, Flow inclusion diagnostic | No smoke/temperature export | 5.862 GB | 8.408 GB | 3.510 GB |
| v22, direct Flow binding counters | No smoke/temperature export | 6.042 GB | 8.510 GB | 3.512 GB |
| v23, native Kit viewport | No smoke/temperature export | 5.850 GB | 8.382 GB | 3.515 GB |
| v26, Fabric disabled with Replicator dependency loaded | No native Flow advancement | 5.958 GB | 8.486 GB | 3.513 GB |
| v27, Direct3D comparison | No native Flow advancement | 7.295 GB | 9.552 GB | 3.199 GB |

In the earlier Minimal trials, the direct Flow binding reported zero active/max
blocks. The original execution-graph time nodes also returned zeros, but those
time readings were invalid because their execution input had no trigger; this
was corrected in the later classic tests below. Timeline motion is not accepted
as solver advancement. The expressly
authorized v21 diagnostic enabled Flow's `pathTracingEnabled` inclusion flag
while retaining MinimalRendering and disabling PT/RT/RT2 modes. It did not fix
the issue. The diagnostic option remains off by default. A general Flow/Minimal
incompatibility has **not** been established by these tests.

The first Fabric-disabled test could not initialize Replicator because its
`usdrt.population` import was missing. Loading the installed dependency fixed
that initialization error in v26, but did not activate Flow. The current probe
now rejects zero native solver progress before attempting final image capture.
The subsequent, explicitly requested classic RTX comparison is described below.

The factory source USD still matches its recorded SHA-256. The derived lab is
separate from the terrain and is not a geographic fire reconstruction. Flow's
model fields are not calibrated temperature, density or heat-release rate.

## Classic RTX comparison

The selected diagnostic mode is `RaytracedLighting` (classic RTX), with PT and
RT2 disabled and a 320 x 180 preparation/capture target. Its first attempt used
the incorrect capitalization `RayTracedLighting`; native policy read-back
rejected that attempt before simulation. The installed SDK spelling was then
corrected. This initialization failure is not evidence against classic RTX.

The following trials reached RGB graph initialization, but the 10.5 GB
preventive committed-memory stop terminated them before the first image. No
Flow advancement, fire image or smoke image was obtained. The process-tree RAM
and whole-device VRAM measurements stayed below the requested 12/15 GB ceilings.
The monitoring interval is 100 ms; the observed value may exceed the preventive
threshold before termination. Neither a zero-overshoot guarantee nor long-run
stability is inferred.

| Trial | Native configuration | Peak resident RAM | Peak Job commit | Peak whole-GPU VRAM |
| --- | --- | ---: | ---: | ---: |
| v29 | Classic RTX, Vulkan | 8.741 GB | 10.553 GB | 2.550 GB |
| v30 | Classic RTX with reduced lighting effects, Vulkan | 8.295 GB | 10.514 GB | 2.857 GB |
| v31 | Same, serialized pipeline compilation and one shader worker | 8.272 GB | 10.501 GB | 2.881 GB |
| v32 | Same, Direct3D | 9.059 GB | 10.741 GB | 2.571 GB |
| v33 | Direct3D, legacy AA op=2 requested, two CPU workers | 8.858 GB | 10.524 GB | 2.678 GB |

The recipe, 512-block allocation cap and 0.6 m voxel size were retained. These
are initialization diagnostics with changing cache conditions, not a controlled
performance benchmark. Enabling another mode has not established a working
local fire simulator. Source factory USD, the full map and cloud originals remain
unchanged.

All comparison processes have exited. No memory ceiling was raised, driver
changed, or full production run started. These initial classic trials did not
qualify that configuration. The later successful reduced native SDK test is
described below; full production remains unqualified.
The [sanitized measurement receipt](evidence/rtx-classic-comparison-20261026.json)
contains the measured resource values and hashes of the private run receipts.

## Follow-up initialization diagnosis

The next bounded attempts isolate initialization rather than change the source
recipe. A heartbeat records completed Kit updates and their longest wall time.
In the sampled run, 56 updates completed before progress stopped inside the
first native render; no further completed-update heartbeat was obtained before
the memory guard terminated the process.

| Trial | Single diagnostic change or purpose | Peak resident RAM | Peak Job commit | Peak whole-GPU VRAM |
| --- | --- | ---: | ---: | ---: |
| v34 | No preallocated warm Slang sessions | 8.832 GB | 10.505 GB | 2.644 GB |
| v35 | Native thread sample, previous bounded configuration | 8.762 GB | 10.505 GB | 2.641 GB |
| v36 | MDL library compilation disabled | 8.827 GB | 10.534 GB | 2.653 GB |
| v37 | Native viewport capture before any Replicator capture graph | 8.826 GB | 10.516 GB | 2.668 GB |
| v38 | Authorized RTX Real-Time 2.0, one bounce, same factory recipe | 8.833 GB | 10.535 GB | 2.643 GB |
| v39 | Kit 110.3, no Flow prims, Flow disabled, Replicator negative control | 6.969 GB | 8.471 GB | 2.565 GB |
| v40 | Kit 110.2 native viewport, no Flow/PhysX/Warp/Replicator extensions | 5.761 GB | 7.069 GB | 2.525 GB |

The private normal minidump is 1,449,330 bytes, contains thread stacks/module
metadata, and is not a full-memory dump. Its highest cumulative CPU-time thread
was executing in `nvwgf2umx.dll` at the sampled instant; renderer/material
initialization also appears among the candidate stack addresses. This localizes
work in the driver/rendering path but does **not** establish a driver defect or
attribute individual memory allocations. Raw stack data stays private.

The native viewport attempt also failed before its first image. Therefore the
failure is reproducible without Replicator's capture graph, and changing only
the event capture scheduler cannot establish a fix. No fire/smoke capture or
solver advancement was obtained in these attempts.
The two negative controls v39 and v40 stopped at their 300-second wall
deadlines rather than a memory threshold. The Kit 110.2 log explicitly reports
waiting for asynchronous ray-tracing pipeline compilation. It initializes the
engine and viewport but does not deliver the first image within that deadline.
This does not establish a driver defect or justify a claim that the timeout is
caused by Flow. The two controls also use different capture backends and
extension sets, so their memory difference cannot be assigned to Kit version
alone.
The [sanitized follow-up receipt](evidence/rtx-initialization-diagnosis-20261026.json)
records resource peaks and the digest of the retained private thread sample.

A separate RTX Real-Time 2.0 diagnostic was explicitly authorized and run for
the requested two-second, 320 x 180 trial. Native settings confirmed
`RealTimePathTracing`, RT2 enabled, Interactive PT disabled and Flow inclusion
enabled. It also reached the preventive memory stop before producing its first
image or advancing the simulator. NVIDIA describes RT2 as real-time path tracing.
Its policy therefore requires
`allow_realtime_path_tracing: true` in addition to `renderer_mode: realtime2`;
truthy strings or integers are rejected. This isolated trial does not authorize
production. Interactive PT stays disabled, but that does not make RT2 a
non-path-traced renderer. RT2 is not qualified locally by this failed trial.

## Working native Flow and collision diagnostic

| Trial | Result | Peak resident RAM | Peak Job commit | Peak whole-GPU VRAM |
| --- | --- | ---: | ---: | ---: |
| v41 | Native viewport negative control: actual floor PNG, normal exit | 6.265 GB | 8.290 GB | 3.310 GB |
| v45 | Two-second actual Flow evolution, native blocks and RGB | 5.578 GB | 7.696 GB | 3.489 GB |
| v47 | Five seconds, verified 1920 × 1080 PNG | 5.945 GB | 9.047 GB | 4.623 GB |
| v49 | Ten seconds without collision; fields obtained but export spool guard stops the test | 6.417 GB | 9.583 GB | 4.630 GB |
| v51 | Ten seconds with PhysX floor, Full HD, bounded field export, normal exit | 6.291 GB | 9.494 GB | 4.802 GB |
| v52 | Public launcher reproduces the native collision test, normal exit | 6.258 GB | 9.463 GB | 4.800 GB |

Intermediate failures remain recorded as failures. Kit resets the legacy AA
operation 2 (FXAA, previously mislabeled TAA) to operation 3. Tests v42/v43
correctly rejected the resulting policy mismatch. The tested policy now uses
operation 3 with `dlss/execMode=4` (DLAA, native resolution), with frame generation
disabled. No forced repeated override or silent policy relaxation is used.

The Flow execution graph now explicitly triggers `FlowSimTime` and `FlowBlocks`
with `OnImpulseEvent`, including while the timeline is paused. The reported
absolute flushed-work timestamp is not scenario elapsed time; its bootstrap
offset can differ between runs. V44's zero-time rejection came from the missing
trigger, even though direct block counts and real flames were already present.
Native timeline time, flushed-work time and block counts remain separate fields.

V46 exposed a file-write race: Kit's capture completion callback returned before
the PNG was complete. `native_capture.py` waits for the actual file and validates
its signature, dimensions, encoding, chunk CRCs, bounded decompression, scanline
lengths and IEND before hashing. V47 and subsequent captures pass this check.
Visual inspection remains separate from file integrity.

Native NanoVDB readback has several updates of latency and needs positive
carrier-clock ticks with both Flow core evolution and emitters explicitly
disabled. V48 did not obtain files while paused; v49 overproduced them; v50
disabled readback before the first results arrived. The corrected diagnostic
waits for two observed exports of each field, disables readback, drains the
pipeline and restores the scenario clock. It checks the 128 MiB spool budget
during export and after draining. This is a sampled stop, not a filesystem quota.

The v49 no-collision reference has 15.42% of its smoke-field support weight below
the ground threshold. Adding the closed static PhysX mesh, enabling Flow mesh
collision and keeping the artificial ground eraser disabled removes the measured
below-ground support in v51 and v52. In v52 all 2,342,912 allocated voxels per
field were measured; the two final exports have identical canonical voxel/value
hashes for both smoke and temperature. The smoke support extends to 12.9 m at
ten seconds, with its weighted centroid at 3.21 m. Values use native Flow units,
not kilograms per cubic metre, kelvin or calibrated heat release.

The rendered flame front is still bright and the smoke remains near the source.
Visibility and this ground-collision response do not establish realistic rural
fire physics. There is no hot/cold/wind/convergence matrix pass, no five-camera
native frozen-state pass, no velocity-field freeze proof, no checkpoint/restart
of native Flow and no long-run memory or ghosting qualification. Separate runs
also produce different hashes; deterministic replay has not been established.
The loaded Flow extension reports a Fabric interface-version warning against
this SDK, retained in private logs; these short tests do not establish general
binary compatibility for other Flow features.

## Complete published incident inputs

The formerly found 21-day archive was incomplete. The current published input
set was fetched again and referenced file sizes and SHA-256 digests checked:

- 138 source files and 37 chronology entries;
- 59 daily products, 24 June through 21 August 2026;
- 67 cartographic snapshots: 59 daily reconstructions, six dated observations,
  two period assessments;
- 47 daily products selected for the simulation ending 10 August, exclusive;
- daily statuses: 24 reconstructed and 35 carried forward. These are not 59
  independent observed perimeters.

Calendar dates, observation dates, uncertainty, hindsight constraints and source
properties are retained. Carried extents do not carry old active/front/flame or
thermal layers. A perimeter or thermal detection is never automatically an
ignition area or a visible-flame annotation.

The 67 snapshots have also been projected from longitude/latitude to scene XY
using the delivered EPSG:2154 anchor, preserving holes and multipart structure.
One `unobserved` geometry in the 10 July observation extends outside the southern
20 km boundary. It is flagged and retained rather than silently clipped.
Terrain-height sampling and independent geodetic acceptance remain pending.

## Automated checks and remaining gates

The local recovery/offload/configuration/incident-input suite has 61 passing
tests. Event capture has 41 passing tests and three OpenUSD-dependent skips
outside Kit. Windows atomic writes and asyncio's loopback socket need a host
test process; sandbox failures before test execution are not native pipeline
failures. A small Windows allocation test verified preventive stopping before
the Job hard limit.

The actual capture orchestration now has an optional verified-offload hook.
CPU tests cover ten groups with one active product, transfer failure before
clock advancement, restart without rerendering, interruption after pruning,
remote corruption on resume and destination-policy changes. A real sleeping
child process is killed by the readback deadline. An authenticated cloud trial
also uploaded the real v52 native Full HD PNG (1,040,736 bytes) and its diagnostic
metadata, verified the complete remote byte streams by SHA-256, uploaded a
verified receipt, and pruned only the spool's media copy. The local review image
remains. This validates one real diagnostic bundle, not production five-camera
offload throughput. Retained metadata can
still fill the bounded spool during a long run; production compaction is pending.

Recovery of the full 36-archive scene is separate from renderer qualification.
Only matching per-archive receipts and the final `scene-restored.json` establish
complete restoration. There are now 25 matching numbered archive receipts out
of 36; the separate preparation archive is not included in this count. The last
bounded batch restored and verified 617 files (804,511,810 bytes) from archive
25 and consumed its local ZIP after verification. The final all-file audit has
not yet run, so these receipts do not certify complete current scene restoration.
A Drive API request-quota failure was recovered using the
new bounded backoff, without changing accounts or permissions. Cloud originals remain
unchanged and the full map is retained locally.

The production fire adapter remains explicitly missing. Required gates include
actual propagation/Flow coupling, verified freeze of every producer, visible
native flames and smoke in the geographic scene, physical response and mesh/time-step sensitivity,
weather-gap handling, complete visible terrain/assets and bounded Drive offload
during a long run. The acceleration target is 1000; no measured 1000× fire-solver
throughput is claimed. Periodic capture frequency is 75% of the baseline, with
negatives and transition triggers retained.

Private contexts, credentials, account/storage identifiers, raw logs and crash
dumps stay outside Git. Laboratory images are labelled as diagnostic evidence;
they never stand in for the requested geographic scene. No placeholder, generated
illustration or CPU test image is accepted as production proof.
