"""Explicit adapter interface; no fictitious front accessor or solver freeze."""
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass
import json

from .models import SimulationState, ContractError, canonical, digest


class MissingSimulationAdapter(RuntimeError):
    pass


class SynchronizationError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdapterCapabilities:
    activity_state_available: bool
    stops_on_activity_events: bool
    freezes_all_state_producers: bool
    deterministic_restore: bool
    state_producers: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class FrozenSnapshot:
    state: SimulationState
    evidence: dict


class SimulationAdapter(ABC):
    """Implemented against the real engine's documented hooks.

    advance_to may stop BEFORE its target for an activity event, never after it.
    A frozen lease must include propagation, smoke and asynchronous producers;
    pausing an Omniverse timeline alone does not satisfy this contract.
    """
    capabilities: AdapterCapabilities

    @abstractmethod
    async def read_state(self) -> SimulationState:
        raise MissingSimulationAdapter("Engine state adapter is missing")

    @abstractmethod
    async def advance_to(self, target_sim_time_us: int, acceleration: float) -> SimulationState:
        raise MissingSimulationAdapter("Engine temporal-advance adapter is missing")

    @abstractmethod
    def freeze(self, expected: SimulationState):
        raise MissingSimulationAdapter("External-producer freeze adapter is missing")

    @abstractmethod
    async def assert_frozen(self, snapshot: FrozenSnapshot):
        raise MissingSimulationAdapter("External-producer freeze verification is missing")

    @abstractmethod
    async def checkpoint(self) -> dict:
        raise MissingSimulationAdapter("Engine checkpoint adapter is missing")

    @abstractmethod
    async def restore(self, checkpoint: dict):
        raise MissingSimulationAdapter("Engine restore adapter is missing")

    def require_capture_contract(self):
        c = self.capabilities
        if not (c.activity_state_available and c.stops_on_activity_events and c.freezes_all_state_producers):
            raise MissingSimulationAdapter(
                "A live adapter must supply activity, event stops and verified freeze of every producer; timeline pause is insufficient")
        if not c.state_producers:
            raise MissingSimulationAdapter("The adapter must enumerate its state producers")


class RecordedStateAdapter(SimulationAdapter):
    """A real reader of a supplied state log, NOT a propagation/smoke solver.

    Used for deterministic replay, fixtures and renderer qualification. It must
    never be reported as an integration with a production fire engine.
    """
    capabilities = AdapterCapabilities(True, True, True, True, ("recorded_state_log",),
                                       "Recorded input only; no external physics or smoke engine")

    def __init__(self, states, source_id="recorded-state-log"):
        self._events = [s.to_dict() if isinstance(s, SimulationState) else s for s in states]
        self._events = json.loads(canonical(self._events))
        times = [s["sim_time_us"] for s in self._events]
        if not times or times[0] != 0 or times != sorted(set(times)):
            raise ContractError("Recorded states must start at zero and have unique increasing simulated timestamps")
        for s in self._events:
            if SimulationState.from_dict(s).fronts is None:
                raise ContractError("An absent front feed is not an inactive scene")
        self.source_id = source_id; self.source_digest = digest(self._events)
        self.now = 0; self.index = 0; self._frozen = False

    async def read_state(self):
        state = json.loads(canonical(self._events[self.index])); state["sim_time_us"] = self.now
        return SimulationState.from_dict(state)

    async def advance_to(self, target_sim_time_us, acceleration):
        if self._frozen:
            raise SynchronizationError("Cannot advance while the capture lease is frozen")
        if type(target_sim_time_us) is not int or target_sim_time_us < self.now:
            raise ContractError("Recorded clock cannot move backwards")
        # Return each supplied transition, including short smoke pulses.
        if self.index + 1 < len(self._events) and self._events[self.index + 1]["sim_time_us"] <= target_sim_time_us:
            self.index += 1; self.now = self._events[self.index]["sim_time_us"]
        else:
            self.now = target_sim_time_us
        return await self.read_state()

    @asynccontextmanager
    async def freeze(self, expected):
        if self._frozen:
            raise SynchronizationError("Nested frozen capture lease")
        state = await self.read_state()
        if state.fingerprint != expected.fingerprint:
            raise SynchronizationError("State changed before capture")
        self._frozen = True
        lease = FrozenSnapshot(state, {"producer": "recorded_state_log", "all_producers_frozen": True,
                                       "source_digest": self.source_digest, "production_fire_solver": False})
        try:
            yield lease
            await self.assert_frozen(lease)
        finally:
            self._frozen = False

    async def assert_frozen(self, snapshot):
        if not self._frozen or (await self.read_state()).fingerprint != snapshot.state.fingerprint:
            raise SynchronizationError("The shared capture state is no longer frozen")

    async def checkpoint(self):
        return {"adapter": "recorded-state-log-v1", "source_digest": self.source_digest,
                "source_id": self.source_id, "sim_time_us": self.now, "index": self.index}

    async def restore(self, checkpoint):
        if self._frozen or checkpoint.get("source_digest") != self.source_digest:
            raise SynchronizationError("Checkpoint does not match the recorded source")
        index = checkpoint["index"]; now = checkpoint["sim_time_us"]
        if type(index) is not int or not 0 <= index < len(self._events) or now < self._events[index]["sim_time_us"]:
            raise ContractError("Invalid recorded-state checkpoint")
        if index + 1 < len(self._events) and now >= self._events[index + 1]["sim_time_us"]:
            raise ContractError("Checkpoint skips a supplied activity transition")
        self.index = index; self.now = now
