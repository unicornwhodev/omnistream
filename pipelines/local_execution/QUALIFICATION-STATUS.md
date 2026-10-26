# Local qualification status — 2026-10-26

Native RTX Minimal now produces and verifies 1920 × 1080 PNGs within the sampled
resource budgets. **The images contain the laboratory floor but no visible fire
or smoke. Wildfire simulation is not qualified, and the 47-day production run
has not started.** A normal renderer exit is not a fire-physics pass.

## Memory fault and preventive controls

The earlier Direct3D attempt failed with LLVM out-of-memory errors and graphics
device error `0x887a0005`. Its hard Job limit alone was insufficient to prevent
that failure. The current launcher adds a preventive committed-memory stop,
resident-memory and host-reserve checks, bounded fatal-log scanning and a 100 ms
sampling interval. It terminates only its own process tree.

The tested native configuration uses one warm Slang compiler session, four
Carbonite/TBB workers, two PhysX workers, Vulkan's matching shader cache, no
unused automatic viewport, an explicitly attached RTX Hydra engine and an
explicit RGB consumer before the first Replicator step. These changes were
tested together; no single one is claimed sufficient on its own.

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

The shipped Flow telemetry nodes report zero active/max blocks and zero flushed
simulation time. The direct Flow binding independently reports zero active/max
blocks. Timeline motion is not accepted as solver advancement. The expressly
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
| v33 | Direct3D, TAA instead of DLSS, two CPU workers | 8.858 GB | 10.524 GB | 2.678 GB |

The recipe, 512-block allocation cap and 0.6 m voxel size were retained. These
are initialization diagnostics with changing cache conditions, not a controlled
performance benchmark. Enabling another mode has not established a working
local fire simulator. Source factory USD, the full map and cloud originals remain
unchanged.

All comparison processes have exited. No memory ceiling was raised, driver
changed, or full production run started. The reduced classic preset is available
for diagnosis, but is **not validated for use** under the current memory budget.
The [sanitized measurement receipt](evidence/rtx-classic-comparison-20261026.json)
contains the measured resource values and hashes of the private run receipts.

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

The local recovery/offload/configuration/incident-input suite has 55 passing
tests. Event capture has 41 passing tests and three OpenUSD-dependent skips
outside Kit. Windows atomic writes and asyncio's loopback socket need a host
test process; sandbox failures before test execution are not native pipeline
failures. A small Windows allocation test verified preventive stopping before
the Job hard limit.

The actual capture orchestration now has an optional verified-offload hook.
CPU tests cover ten groups with one active product, transfer failure before
clock advancement, restart without rerendering, interruption after pruning,
remote corruption on resume and destination-policy changes. A real sleeping
child process is killed by the readback deadline. These checks do not certify
native fire capture or an authenticated image upload. Retained metadata can
still fill the bounded spool during a long run; production compaction is pending.

Recovery of the full 36-archive scene is separate from renderer qualification.
Only matching per-archive receipts and the final `scene-restored.json` establish
complete restoration. The last full recovery audit found 16 verified archives;
subsequent archives passed independent restoration and progress must be read
from fresh receipts. A Drive API request-quota failure was recovered using the
new bounded backoff, without changing accounts or permissions. Cloud originals remain
unchanged and the full map is retained locally.

The production fire adapter remains explicitly missing. Required gates include
actual propagation/Flow coupling, verified freeze of every producer, visible
native flames and smoke, physical response and mesh/time-step sensitivity,
weather-gap handling, complete visible terrain/assets and bounded Drive offload
during a long run. The acceleration target is 1000; no measured 1000× fire-solver
throughput is claimed. Periodic capture frequency is 75% of the baseline, with
negatives and transition triggers retained.

Private contexts, credentials, account/storage identifiers, raw logs and crash
dumps stay outside Git. Diagnostic native images are labelled as failures when
they do not show the requested scene or VFX. No placeholder, generated
illustration or CPU test image is accepted as production proof.
