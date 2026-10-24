# Qualification gates and benchmark

The current 32 tests passed on Colab CPU on 2026-10-24, including six weather
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

The current Colab session was CPU-only when these tests were run. The native
matrix, profiler, memory stability, ghosting, real fire engine integration and
real scene panel acceptance have **not** passed. Keep final scene export held.
