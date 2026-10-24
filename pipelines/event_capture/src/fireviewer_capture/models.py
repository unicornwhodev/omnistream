"""Serializable contracts. Intervals use integer simulated microseconds only."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
import hashlib
import json
import re

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")


class ContractError(ValueError):
    pass


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ContractError("Identifiers must be bounded ASCII names")
    return value


def simulated_us(seconds):
    if isinstance(seconds, bool):
        raise ContractError("A Boolean is not a simulated interval")
    n = Decimal(str(seconds)) * 1_000_000
    if not n.is_finite() or n < 0 or n != n.to_integral_value():
        raise ContractError("Simulated intervals must be finite non-negative microseconds")
    return int(n)


def aware_time(value):
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None or d.utcoffset() is None:
        raise ContractError("Simulated calendar times need an explicit UTC offset")
    return d.astimezone(timezone.utc)


def utc_at(epoch, elapsed_us):
    return (aware_time(epoch) + timedelta(microseconds=elapsed_us)).isoformat().replace("+00:00", "Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Activity(StrEnum):
    INACTIVE = "inactive"
    EARLY_SMOKE = "early_smoke"
    ACTIVE_RAPID = "active_rapid"
    ACTIVE_STABLE = "active_stable"
    DECLINING = "declining"
    POST_EXTINCTION = "post_extinction"
    UNKNOWN = "unknown"


RANK = {Activity.UNKNOWN: -1, Activity.INACTIVE: 0, Activity.POST_EXTINCTION: 1,
        Activity.DECLINING: 2, Activity.EARLY_SMOKE: 3, Activity.ACTIVE_STABLE: 4,
        Activity.ACTIVE_RAPID: 5}


@dataclass(frozen=True)
class Provenance:
    kind: str
    source: str
    source_revision: str | None = None

    def __post_init__(self):
        if self.kind not in {"simulator_exact", "observed", "estimated", "unknown", "test_fixture"}:
            raise ContractError("Annotation provenance must be explicit")
        if not self.source:
            raise ContractError("Annotation provenance needs a source")


@dataclass(frozen=True)
class FrontObservation:
    front_id: str
    footprint: dict
    activity: Activity
    provenance: Provenance
    smoke_footprint: dict | None = None
    smoke_present: bool | None = None
    # Visibility is camera-specific and never inferred from activity/overlap.
    camera_annotations: dict = field(default_factory=dict)

    def __post_init__(self):
        identifier(self.front_id)
        object.__setattr__(self, "activity", Activity(self.activity))
        canonical(asdict(self))


@dataclass(frozen=True)
class SimulationState:
    sim_time_us: int
    engine_revision: str
    fronts: tuple[FrontObservation, ...] | None
    environment: dict
    engine_state: dict

    def __post_init__(self):
        if type(self.sim_time_us) is not int or self.sim_time_us < 0:
            raise ContractError("Simulation time must be integer microseconds")
        if not self.engine_revision:
            raise ContractError("An engine state revision is required")
        if self.fronts is not None and len({f.front_id for f in self.fronts}) != len(self.fronts):
            raise ContractError("Duplicate front identifiers")
        canonical(self.to_dict())

    def to_dict(self):
        return asdict(self)

    @property
    def fingerprint(self):
        return digest(self.to_dict())

    @classmethod
    def from_dict(cls, value):
        value = json.loads(canonical(value))
        fronts = value["fronts"]
        if fronts is not None:
            fronts = tuple(FrontObservation(**{**f, "provenance": Provenance(**f["provenance"])}) for f in fronts)
        return cls(value["sim_time_us"], value["engine_revision"], fronts,
                   value["environment"], value["engine_state"])


@dataclass(frozen=True)
class ZoneReport:
    zone_id: str
    sim_time_us: int
    activity: Activity
    raw_activity: Activity
    front_ids: tuple[str, ...]
    smoke_front_ids: tuple[str, ...]
    transition_reasons: tuple[str, ...]
    post_window_end_us: int | None
    related_front_ids: tuple[str,...] = ()


@dataclass(frozen=True)
class CaptureRequest:
    zone_id: str
    sim_time_us: int
    state_fingerprint: str
    reasons: tuple[str, ...]
    activity: Activity
    front_ids: tuple[str, ...]
    priority: int
    scheduled_sim_time_us: int

    @property
    def key(self):
        return digest([self.zone_id, self.sim_time_us, self.state_fingerprint])
