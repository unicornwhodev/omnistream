# Real engine contract

No production propagation/front API was available when this package was built.
The reference configuration therefore says `adapter.kind=missing`. Do not
replace that marker with guessed methods or reinterpret daily fire perimeters
as instantaneous visible flames.

Implement the abstract methods in `simulation.py` against documented engine
hooks. Supply current fronts (including explicit activity and smoke presence),
their scene-local planar footprints, source revision and annotation provenance.
`fronts=None` means the feed is unavailable. An empty tuple is an explicitly
known absence of fronts. Relevant unknown activity or smoke state prevents a
negative label. Front activity and camera flame visibility are separate fields.

`advance_to(target_sim_time_us, acceleration)` returns at the target or earlier
at the next activity event. It must never overshoot a capture deadline. Preserve
short appearance/disappearance events even when they occur between polling
boundaries. Engine time advances once for all 50 cameras. Acceleration changes
wall execution policy, not the simulated capture calendar. Recorded playback
can jump to supplied events; it is not a real-time performance benchmark.

`freeze(expected_state)` acquires an async lease over **all** state producers:
timeline, propagation solver, smoke/volume solver, asynchronous input consumers
and procedural asset state. Enumerate those producers in capabilities and
provide actual freeze evidence. Pausing only the Kit timeline is insufficient.
`assert_frozen` must detect source revision/content changes throughout every
batch and write, including a capped 2 + 2 + 1 camera group. It must not merely
return the earlier snapshot again.

Checkpoint and restore must reproduce engine state, seeds, source log offsets,
external solver checkpoints and input hashes. A failure after two images must
resume at exactly the same state. Keep adapter checkpoints serializable and
avoid credentials, personal paths or account identifiers in capture metadata.

Use `simulator_exact` only for values actually supplied as exact engine truth.
Observed station weather remains `observed`; interpolation and model weather
remain estimated. Visibility estimated from an image is not exact simulator
truth. Front perimeter overlap is a trigger, not a visibility annotation.

`RecordedStateAdapter` reads an explicit state log and is suitable for replay
and scheduling tests. `KitFixtureAdapter` additionally binds the real Kit
timeline, only in a marked qualification fixture without external solvers.
Neither adapter simulates physical fire or smoke.
