"""Documented Kit timeline binding for qualification fixtures ONLY."""
from contextlib import asynccontextmanager
from .simulation import RecordedStateAdapter,AdapterCapabilities,SynchronizationError
from .models import SimulationState


class KitFixtureAdapter(RecordedStateAdapter):
    capabilities=AdapterCapabilities(True,True,True,True,("recorded_state_log","usd_timeline"),
                                     "Qualification fixture only; not a propagation or smoke adapter")
    def __init__(self,states,source_id="qualification-fixture"):
        import omni.usd,omni.timeline
        stage=omni.usd.get_context().get_stage()
        if not stage or stage.GetDefaultPrim().GetCustomDataByKey("qualification:fixture") is not True:
            raise SynchronizationError("Recorded Kit binding is restricted to an explicitly marked qualification fixture")
        super().__init__(states,source_id);self.timeline=omni.timeline.get_timeline_interface()
        self.timeline.pause();self.timeline.set_current_time(0);self.timeline.commit()

    async def _set_time(self):
        import omni.kit.app
        self.timeline.pause();self.timeline.set_current_time(self.now/1_000_000);self.timeline.commit()
        await omni.kit.app.get_app().next_update_async()

    async def read_state(self):
        state=await super().read_state()
        return SimulationState(state.sim_time_us,state.engine_revision,state.fronts,state.environment,
                               {**state.engine_state,"kit_timeline_seconds":float(self.timeline.get_current_time()),
                                "kit_timeline_playing":bool(self.timeline.is_playing()),"external_engines":"none in marked fixture"})

    async def advance_to(self,target_sim_time_us,acceleration):
        await super().advance_to(target_sim_time_us,acceleration);await self._set_time();return await self.read_state()

    async def restore(self,checkpoint):
        await super().restore(checkpoint);await self._set_time()

    async def assert_frozen(self,snapshot):
        await super().assert_frozen(snapshot)
        if self.timeline.is_playing() or abs(self.timeline.get_current_time()-self.now/1_000_000)>1e-6:
            raise SynchronizationError("Kit timeline changed during a frozen capture group")
