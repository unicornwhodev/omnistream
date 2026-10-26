"""The only simulation-advance loop; captures freeze it rather than restarting."""
from datetime import datetime
import time

from .activity import ZoneActivityTracker
from .scheduler import CaptureScheduler
from .config import validate_config,config_identity
from .models import aware_time,simulated_us,ContractError,identifier


class CapturePipeline:
    def __init__(self,config,adapter,manager,store,metrics,offloader=None):
        self.config=validate_config(config);self.adapter=adapter;self.manager=manager;self.store=store;self.metrics=metrics
        self.identity=config_identity(config)
        self.metrics.requested_acceleration=self.config['acceleration']
        self.tracker=ZoneActivityTracker(config["zones"],config["activity"])
        self.scheduler=CaptureScheduler([z["id"] for z in config["zones"]],config["capture_policy"])
        self.end_us=simulated_us((aware_time(config["period"]["end_exclusive"])-aware_time(config["period"]["start"])).total_seconds())
        self.committed_groups=0
        self.offloader=offloader
        self.offload_policy_id=identifier(offloader.policy_id) if offloader else None
        self.pending_offloads=[]

    async def _checkpoint(self,status="running"):
        checkpoint=await self.adapter.checkpoint()
        self.store.checkpoint({"schema":"fireviewer.pipeline-checkpoint.v1","config_sha256":self.identity,
                               "status":status,"adapter":checkpoint,"tracker":self.tracker.checkpoint(),
                               "scheduler":self.scheduler.checkpoint(),"committed_groups":self.committed_groups,
                               "offload_policy_id":self.offload_policy_id,"pending_offloads":list(self.pending_offloads)})

    async def _admit_group(self,request):
        if self.offloader:
            await self.offloader.admit_group(self.config)

    async def _drain_offloads(self):
        # Called only inside the adapter's frozen lease. Each group was already
        # committed into the scheduler checkpoint, so a retry never renders it
        # again or advances while its cloud verification is outstanding.
        while self.pending_offloads:
            group_id=self.pending_offloads[0];started=time.perf_counter()
            await self.offloader.offload_group(group_id)
            self.metrics.durations['cloud_offload_and_readback_wall_s']+=time.perf_counter()-started
            self.metrics.counts['groups_offloaded_verified']+=1
            self.pending_offloads.pop(0)
            await self._checkpoint()

    async def _group_committed(self,request,group_id,receipt_sha256):
        self.scheduler.commit(request);self.committed_groups+=1
        self.store.log({"event":"group_committed","group_id":group_id,"receipt_sha256":receipt_sha256,
                        "zone_id":request.zone_id,"sim_time_us":request.sim_time_us})
        if self.offloader:self.pending_offloads.append(group_id)
        await self._checkpoint()
        if self.offloader:await self._drain_offloads()

    async def run(self,resume=True,max_groups=None):
        self.adapter.require_capture_contract()
        if not self.adapter.capabilities.deterministic_restore:
            raise ContractError("Idempotent capture requires a documented deterministic adapter checkpoint/restore")
        checkpoint=self.store.read_checkpoint() if resume else None
        if checkpoint:
            if checkpoint["config_sha256"]!=self.identity:
                raise ContractError("Resume configuration/scene/seed changed")
            if checkpoint.get('offload_policy_id')!=self.offload_policy_id:
                raise ContractError('Resume cloud destination/policy changed or offloader missing')
            pending=checkpoint.get('pending_offloads',[])
            if (not isinstance(pending,list) or len(pending)>64
                    or any(not isinstance(x,str) or len(x)!=64 or any(c not in '0123456789abcdef' for c in x) for x in pending)
                    or len(set(pending))!=len(pending)):
                raise ContractError('Invalid pending cloud groups in checkpoint')
            if pending and self.offloader is None:
                raise ContractError('Pending cloud verification requires its offloader')
            self.pending_offloads=list(pending)
            await self.adapter.restore(checkpoint["adapter"]);self.tracker.restore(checkpoint["tracker"])
            self.scheduler.restore(checkpoint["scheduler"]);self.committed_groups=checkpoint["committed_groups"]
        elif self.store.read_checkpoint() is not None:
            raise ContractError("Existing checkpoint requires resume or a new output directory")
        state=await self.adapter.read_state()
        if checkpoint is None and state.sim_time_us!=0:
            raise ContractError("A fresh run must start at simulated zero; a later state requires its checkpoint")
        if self.pending_offloads:
            async with self.adapter.freeze(state) as snapshot:
                await self._drain_offloads()
                await self.adapter.assert_frozen(snapshot)
        if checkpoint and checkpoint['status']=='complete':
            return {"already_complete":True,"committed_groups":self.committed_groups}
        await self.manager.start()
        try:
            while state.sim_time_us<self.end_us:
                reports=self.tracker.update(state);self.scheduler.observe(state,reports)
                requests=self.scheduler.requests_at(state.sim_time_us)
                # Save the exact pending instant BEFORE any write. If a process
                # dies mid-group, restore this state and verify existing images.
                await self._checkpoint()
                if requests:
                    await self.manager.capture_instant(self.adapter,state,requests,self._group_committed,self._admit_group)
                    if max_groups is not None and self.committed_groups>=max_groups:
                        await self._checkpoint("stopped_at_requested_boundary")
                        return {"stopped":True,"committed_groups":self.committed_groups}
                boundaries=[self.end_us,state.sim_time_us+simulated_us(self.config["activity"]["poll_interval_sim_s"])]
                for boundary in [self.scheduler.next_due_us(state.sim_time_us),self.tracker.next_boundary_us()]:
                    if boundary is not None and boundary>state.sim_time_us:boundaries.append(boundary)
                target=min(boundaries);before=state.sim_time_us;started=time.perf_counter()
                state=await self.adapter.advance_to(target,self.config["acceleration"])
                self.metrics.durations["simulation_advance_wall_s"]+=time.perf_counter()-started
                self.metrics.counts["simulation_advance_calls"]+=1
                if not before<state.sim_time_us<=target:
                    raise ContractError("Adapter failed to advance monotonically or overshot a capture/event boundary")
                self.metrics.counts['simulated_time_advanced_us']+=state.sim_time_us-before
            await self._checkpoint("complete")
            return {"complete":True,"committed_groups":self.committed_groups,"sim_time_us":state.sim_time_us}
        finally:
            await self.manager.close()
