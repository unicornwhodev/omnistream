"""Conservative zone activity and transition tracking, never flame visibility."""
from dataclasses import asdict
from shapely.geometry import shape

from .models import Activity, RANK, ZoneReport, ContractError, simulated_us


class ZoneActivityTracker:
    def __init__(self, zones, policy):
        self.zones = {z["id"]: shape(z["geometry"]) for z in zones}
        if any(g.is_empty or not g.is_valid for g in self.zones.values()):
            raise ContractError("Zone geometries must be valid non-empty GeoJSON")
        self.enter_margin = float(policy["enter_margin_m"])
        self.exit_margin = float(policy["exit_margin_m"])
        if not 0 <= self.enter_margin <= self.exit_margin:
            raise ContractError("Exit spatial margin must cover the enter margin")
        self.enter_hold = simulated_us(policy["enter_hold_sim_s"])
        self.exit_hold = simulated_us(policy["exit_hold_sim_s"])
        self.post_window = simulated_us(policy["post_extinction_window_sim_s"])
        self.state = {key: {"phase": "inactive", "raw": "inactive", "candidate": "inactive",
                            "candidate_since": 0, "fronts": [], "smoke": [], "related": [], "post_until": None,
                            "ever_active": False, "last_time": -1} for key in self.zones}

    def update(self, snapshot):
        if snapshot.fronts is None:
            raise ContractError("Activity feed is missing; do not label this as negative/inactive")
        reports = []
        for key, zone in self.zones.items():
            memory = self.state[key]; now = snapshot.sim_time_us
            if now < memory["last_time"]:
                raise ContractError("Zone tracker cannot move backwards without restoring a checkpoint")
            fronts, smoke, phases = set(), set(), []
            for f in snapshot.fronts:
                # Hysteresis uses an expanded zone for an already-tracked front.
                margin = self.exit_margin if f.front_id in memory["fronts"] else self.enter_margin
                g = shape(f.footprint)
                if not g.is_valid:
                    raise ContractError("Invalid supplied front geometry")
                if not g.is_empty and zone.buffer(margin).intersects(g):
                    if f.activity==Activity.UNKNOWN:
                        raise ContractError("A relevant front has unknown activity; another front cannot hide that uncertainty")
                    if f.smoke_present is None:
                        raise ContractError("A relevant front has no explicit smoke-presence observation")
                    if f.activity==Activity.POST_EXTINCTION and not memory['ever_active']:
                        raise ContractError('Post-extinction timing needs prior activity or its restored checkpoint; it cannot be treated as an inactive negative')
                    if f.activity not in {Activity.INACTIVE, Activity.POST_EXTINCTION}:
                        fronts.add(f.front_id); phases.append(f.activity)
                if f.smoke_present is True:
                    sg = shape(f.smoke_footprint or f.footprint)
                    sm = self.exit_margin if f.front_id in memory["smoke"] else self.enter_margin
                    if not sg.is_valid:
                        raise ContractError("Invalid supplied smoke geometry")
                    if not sg.is_empty and zone.buffer(sm).intersects(sg):
                        smoke.add(f.front_id); phases.append(Activity.EARLY_SMOKE)
            raw = max(phases, key=lambda x: RANK[x]) if phases else Activity.INACTIVE
            if raw == Activity.UNKNOWN:
                raise ContractError("Supplied front activity is unknown; no negative label is justified")
            transitions = []
            previous_fronts, previous_smoke = set(memory["fronts"]), set(memory["smoke"])
            for name, old, new in [("front", previous_fronts, fronts), ("smoke", previous_smoke, smoke)]:
                if new - old: transitions.append(name + "_appeared_or_entered")
                if old - new: transitions.append(name + "_disappeared_or_exited")
            if raw.value != memory["raw"]:
                transitions.append("raw_activity_changed")
            # Short pulses are captured at BOTH transitions, even if the stable
            # phase has not passed its temporal enter/exit hold.
            if raw.value != memory["candidate"]:
                memory["candidate"] = raw.value; memory["candidate_since"] = now
            if phases:
                if not memory['fronts'] and not memory['smoke'] and memory['post_until'] is None:memory['related']=[]
                memory['related']=sorted(set(memory['related'])|fronts|smoke)
                memory["ever_active"] = True; memory["post_until"] = None
            elif (previous_fronts or previous_smoke) and memory["ever_active"]:
                memory["post_until"] = now + self.post_window
            desired = raw
            if raw == Activity.INACTIVE and memory["post_until"] is not None and now < memory["post_until"]:
                desired = Activity.POST_EXTINCTION
            hold = self.exit_hold if RANK[desired] < RANK[Activity(memory["phase"])] else self.enter_hold
            if desired == Activity.POST_EXTINCTION or now - memory["candidate_since"] >= hold:
                if desired.value != memory["phase"]: transitions.append("stable_activity_changed")
                memory["phase"] = desired.value
            if memory["post_until"] is not None and now >= memory["post_until"] and raw == Activity.INACTIVE:
                if memory["phase"] != "inactive": transitions.append("post_window_ended")
                memory["phase"] = "inactive"; memory["post_until"] = None
                memory['related']=[]
            memory.update(raw=raw.value, fronts=sorted(fronts), smoke=sorted(smoke), last_time=now)
            reports.append(ZoneReport(key, now, Activity(memory["phase"]), raw, tuple(sorted(fronts)),
                                      tuple(sorted(smoke)), tuple(sorted(set(transitions))), memory["post_until"],
                                      tuple(memory['related']) if memory['phase']=='post_extinction' else ()))
        return reports

    def next_boundary_us(self):
        result = []
        for s in self.state.values():
            if s["candidate"] != s["phase"]:
                hold = self.exit_hold if RANK[Activity(s["candidate"])] < RANK[Activity(s["phase"])] else self.enter_hold
                t = s["candidate_since"] + hold
                if t > s["last_time"]: result.append(t)
            if s["post_until"] is not None and s["post_until"] > s["last_time"]:
                result.append(s["post_until"])
        return min(result) if result else None

    def checkpoint(self):
        return {"schema": "zone-tracker-v2", "zones": self.state}

    def restore(self, value):
        from .models import canonical
        import json
        if value.get("schema") != "zone-tracker-v2" or set(value["zones"]) != set(self.zones):
            raise ContractError("Zone checkpoint does not match the configuration")
        self.state = json.loads(canonical(value["zones"]))
