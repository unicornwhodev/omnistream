# Qualification gates and benchmark

The current 36 tests passed on Colab CPU on 2026-10-24, including six weather
tests and a real OpenUSD check of the 50 camera poses and metric optics.
These use explicitly named CPU test doubles for rendered arrays. They are
source-level evidence, not real scene captures or NVIDIA GPU acceptance.
Later changes require a fresh test receipt before being marked checked.

The unit suite covers 1, 2, 5 and 10 groups, negative periods, multiple fronts,
short smoke pulses, spatial crossings, same-state five-camera groups, bounded
Render Products, interrupted writes, corrupt slots, idempotent resume and
missing state feeds. The real driver must repeat these cases in compatible Kit.

`tools/benchmark_plan.py` compares **planned counts only** for event capture
versus a uniform simulated interval. Supply the same explicit state log:

```bash
python tools/benchmark_plan.py --config configuration.json --state-log states.json \
  --uniform-interval-sim-s 60 --output planned-counts.json
```

For a real rendering comparison, call `benchmark_in_kit` in `benchmark.py`
with actual engine/driver factories. It runs both policies with identical
input states, camera designs, seed and render settings for 1, 2, 5 and 10 groups.
Separate trials restart at the same initial state; cameras never restart their
own simulation. Record runtime/driver/Replicator versions and warm-up policy.
Keep a negative interval and every named transition in the event policy.

Metrics distinguish simulation advance wall time, render wall time, encoding
and verified write time, process RSS, device VRAM and output images per wall
second. Device-wide VRAM includes other GPU allocations. An unavailable NVML
value is null. `gpu_render_execution_s` is null unless a real profiler timing
provider is injected. **Render wall time is never relabelled GPU execution time.**
Supply `--gpu-timing-factory module:function` for the installed renderer's
verified profiler binding; no generic CUDA timer can measure arbitrary RTX
Vulkan work correctly. Real GPU profiling is still an outstanding gate.

Native acceptance must include:

1. Real RGB files from every group in the 1/2/5/10 matrix at 1280 × 720,
   all five camera timestamps/state hashes equal, independent of product cap.
2. Writer callbacks only when explicitly scheduled; zero inactive Render
   Products updating between captures and complete detach/destroy on exit.
3. Real external producer freeze/restore, plus interrupted and incomplete
   output recovery with byte-verified reuse of completed images.
4. Repeated camera-set cycles after warm-up. Record RSS/VRAM per completed
   cycle and evaluate `resource_stability` with predeclared limits. Missing
   VRAM or fewer than five post-warm-up cycles cannot pass that gate.
5. Render a fixed view A, an opposing view B, then A again at the same frozen
   state, using explicit warm-up/subframes. Compare to an independently warmed
   A reference with `compare_repeated_view` and inspect the actual images for
   ghosting. Numerical differences alone do not prove semantic correctness.
6. Visibility-complete terrain/vegetation/building/fire/smoke residency and
   correct damage-state assets. Memory limits must not remove visible objects.
7. Actual fire/smoke labels, exact/estimated provenance, weather mapping and
   the actual Codex panel displaying decoded scene frames. Placeholder panels,
   DOM dumps, artificial unit images and offscreen fixture renders do not pass
   the real-scene panel gate.

## Native geometric fixture, 2026-10-24

A separate Colab NVIDIA L4 (23,034 MiB, driver 580.82.07) ran Isaac Sim 5.1.0.0
with actual RTX RGB output. The marked geometric fixture is not the Justin
landscape, a fire solver, or smoke rendering. Its state log tests scheduling.
The existing recorded NVIDIA agreement and matching user-space driver libraries
were reused; the Google host driver was not replaced.

The 1/2/5/10-group comparison verified 270 RGB images at 1280 × 720. Uniform
sampling used two instants per zone over 20 simulated seconds; the event policy
used one. These short, deliberately chosen fixture counts do not predict
production savings over 47 days. The active/cache cap was five. Native smoke
on/off input events and negatives added 20 images; incomplete-file recovery
reused one verified image and rendered four replacements with a cap of two.
Twelve five-view cycles added 60 images: 355 verified images in total.

After three warm-up cycles, device VRAM growth was 0 bytes/cycle and process
RSS growth about 196,403 bytes/cycle, under predeclared limits of 8/32 MiB per
cycle. This is a short-run allocator/resource check, not a long-duration soak.
The repeated static view had mean absolute RGB difference 0.232 and p99 2
(0–255 units; limits 2 and 12). Numerical comparison passed; visual smoke/fire
ghosting inspection is still required. There were no unsolicited callbacks or
remaining managed products in those cycle/recovery cases.

Native testing exposed two SDK boundary failures: the first manual event can
be lost before graph initialization; a new writer attached while orchestration
is STEPPED can start pre-triggered. The driver primes the graph without writers
armed/scheduled, and pauses capture orchestration before attaching more writers.
The simulation time is checked; no simulation restart or viewport rotation is
used. A stop/reinitialize workaround was discarded because it repeated expensive
asset-loading waits after cache evictions. Failed/partial trials were preserved
separately and do not contribute to accepted image counts.

Run the native fixture with the compatible environment's Python and an already
recorded agreement. Use a new output directory:

```bash
python tools/qualify_in_isaacsim.py --output /content/qualification-new-run
```

The script creates its own explicitly marked stage; never substitute it for
real-scene acceptance. It writes checkpointed image groups, benchmark results,
resource samples, source hashes and a report whose final operational acceptance
remains false. See the [sanitized measured receipt](../../../docs/evidence/native-2026-10-24/fixture-summary.json).

The delivered script was also run independently and completed another 355-image
matrix. A Drive backup was read back and verified: 13 representative unmodified
PNG samples and the metadata/hashes of all 710 images across both runs. The
samples include each zone and the repeated-view A/B/A comparison. Full fixture
pixels are reproducible with the script; the retained sample archive is not a
backup of every generated PNG. No fixture images were exported to the PC.

Actual GPU execution timing is still null: measured render wall time is
available separately. A real fire/smoke adapter, exact producer freeze/restore,
visibility-complete Justin assets, visual ghosting checks, scientific terrain
acceptance and actual decoded Justin frames in Codex are outstanding gates.
**Keep final scene export held.**
