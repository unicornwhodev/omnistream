"""One shared simulated calendar; zone priorities and same-instant coalescing."""
from dataclasses import replace

from .models import Activity, CaptureRequest, ContractError, simulated_us


class CaptureScheduler:
    def __init__(self, zone_ids, policy):
        self.intervals = {Activity(k): simulated_us(v["interval_sim_s"]) for k, v in policy.items()}
        self.priorities = {Activity(k): int(v["priority"]) for k, v in policy.items()}
        if set(self.intervals) != set(Activity) - {Activity.UNKNOWN} or any(v <= 0 for v in self.intervals.values()):
            raise ContractError("Every known activity needs a positive simulated capture interval")
        self.zones = {k: {"next_due_us": 0, "last_committed_us": None,
                          "last_activity": "inactive", "last_state_fingerprint": None} for k in zone_ids}
        self.pending = {}

    def observe(self, snapshot, reports):
        now = snapshot.sim_time_us
        for report in reports:
            if report.sim_time_us != now:
                raise ContractError("Activity and capture clocks differ")
            z = self.zones[report.zone_id]; activity = report.activity
            # Use an immediate raw transition even before a stable hysteresis
            # phase; metadata retains both rather than inventing stable activity.
            if report.transition_reasons and report.raw_activity not in {Activity.INACTIVE, Activity.UNKNOWN}:
                activity = report.raw_activity
            if activity == Activity.UNKNOWN:
                raise ContractError("Unknown activity cannot choose a capture policy")
            if activity.value != z["last_activity"] and z["last_committed_us"] is not None:
                z["next_due_us"] = min(z["next_due_us"], z["last_committed_us"] + self.intervals[activity])
            reasons = list(report.transition_reasons)
            if z["last_committed_us"] is None: reasons.append("initial_negative_or_state_sample")
            if now >= z["next_due_us"]: reasons.append("simulated_interval_due")
            if not reasons: continue
            request = CaptureRequest(report.zone_id, now, snapshot.fingerprint, tuple(sorted(set(reasons))),
                                     activity, tuple(sorted(set(report.front_ids) | set(report.smoke_front_ids) | set(report.related_front_ids))),
                                     self.priorities[activity] + (100 if report.transition_reasons else 0),
                                     now if report.transition_reasons else min(now,z["next_due_us"]))
            previous = self.pending.get(request.key)
            if previous:
                request = replace(previous, reasons=tuple(sorted(set(previous.reasons) | set(request.reasons))),
                                  priority=max(previous.priority, request.priority),
                                  front_ids=tuple(sorted(set(previous.front_ids)|set(request.front_ids))))
            self.pending[request.key] = request

    def requests_at(self, sim_time_us):
        if any(r.sim_time_us < sim_time_us for r in self.pending.values()):
            raise ContractError("An uncommitted capture instant was advanced past")
        return sorted((r for r in self.pending.values() if r.sim_time_us == sim_time_us),
                      key=lambda r: (-r.priority, r.zone_id, r.key))

    def commit(self, request):
        if request.key not in self.pending:
            raise ContractError("Unknown or already committed capture group")
        z = self.zones[request.zone_id]
        z.update(last_committed_us=request.sim_time_us,
                 next_due_us=request.sim_time_us + self.intervals[request.activity],
                 last_activity=request.activity.value, last_state_fingerprint=request.state_fingerprint)
        del self.pending[request.key]

    def next_due_us(self, after_us):
        pending = [r.sim_time_us for r in self.pending.values() if r.sim_time_us > after_us]
        due = [z["next_due_us"] for z in self.zones.values() if z["next_due_us"] > after_us]
        return min(pending + due) if pending or due else None

    def checkpoint(self):
        from dataclasses import asdict
        return {"schema": "capture-scheduler-v1", "zones": self.zones,
                "pending": [asdict(r) for r in self.pending.values()]}

    def restore(self, value):
        from .models import canonical
        import json
        if value.get("schema") != "capture-scheduler-v1" or set(value["zones"]) != set(self.zones):
            raise ContractError("Capture checkpoint does not match configured zones")
        self.zones = json.loads(canonical(value["zones"])); self.pending = {}
        for row in value["pending"]:
            row = dict(row); row["activity"] = Activity(row["activity"])
            row["reasons"] = tuple(row["reasons"]); row["front_ids"] = tuple(row["front_ids"])
            r = CaptureRequest(**row); self.pending[r.key] = r
