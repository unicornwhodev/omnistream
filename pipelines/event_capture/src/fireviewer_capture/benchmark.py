"""Comparable policies with identical input states, cameras, seed and renderer."""
from dataclasses import replace
import copy
from .activity import ZoneActivityTracker
from .scheduler import CaptureScheduler
from .simulation import RecordedStateAdapter
from .models import simulated_us,aware_time
from .metrics import RunMetrics,ResourceSampler
from .storage import CaptureStore,atomic_json
from .replicator import ReplicatorCaptureManager
from .orchestrator import CapturePipeline


class UniformScheduler(CaptureScheduler):
    def observe(self,state,reports):
        # Baseline intentionally samples every zone at a fixed simulated cadence.
        return super().observe(state,[replace(r,transition_reasons=()) for r in reports])


def subset_config(config,groups):
    c=copy.deepcopy(config);c['zones']=c['zones'][:groups]
    ids={i for z in c['zones'] for i in z['camera_ids']};c['cameras']=[x for x in c['cameras'] if x['id'] in ids]
    return c


async def policy_plan(config,states,uniform_interval_s=None):
    """Counts only. No GPU, timings, VRAM, images or quality are claimed."""
    c=copy.deepcopy(config)
    if uniform_interval_s is not None:
        for p in c['capture_policy'].values():p['interval_sim_s']=uniform_interval_s
    tracker=ZoneActivityTracker(c['zones'],c['activity'])
    scheduler=(UniformScheduler if uniform_interval_s else CaptureScheduler)([z['id'] for z in c['zones']],c['capture_policy'])
    adapter=RecordedStateAdapter(states);end=simulated_us((aware_time(c['period']['end_exclusive'])-aware_time(c['period']['start'])).total_seconds())
    state=await adapter.read_state();groups=0;instants=0;counts={z['id']:0 for z in c['zones']}
    while state.sim_time_us<end:
        reports=tracker.update(state);scheduler.observe(state,reports);requests=scheduler.requests_at(state.sim_time_us)
        if requests:instants+=1
        for request in requests:groups+=1;counts[request.zone_id]+=1;scheduler.commit(request)
        targets=[end,state.sim_time_us+simulated_us(c['activity']['poll_interval_sim_s'])]
        targets.extend(x for x in [scheduler.next_due_us(state.sim_time_us),tracker.next_boundary_us()] if x is not None and x>state.sim_time_us)
        state=await adapter.advance_to(min(targets),c['acceleration'])
    return {'groups':groups,'images':groups*5,'instants':instants,'per_zone_groups':counts,
            'measurement_kind':'schedule_count_only','GPU_render_measured':False}


async def benchmark_in_kit(config,states,output,adapter_factory,driver_factory,uniform_interval_s=60,groups=(1,2,5,10)):
    """Factory adapters restore the same input; each policy is a separate trial.

    This restarts BETWEEN benchmark trials, never between cameras. Production
    and fixture runs require their own real adapters and labelled evidence.
    """
    from pathlib import Path
    from .models import ContractError
    root=Path(output);report=[]
    if root.exists() and any(root.iterdir()):
        raise ContractError('Use a fresh benchmark output directory so resume cannot be mistaken for new performance measurements')
    for number in groups:
        if number>len(config['zones']):continue
        for policy in ['uniform','event']:
            c=subset_config(config,number)
            if policy=='uniform':
                for p in c['capture_policy'].values():p['interval_sim_s']=uniform_interval_s
            store=CaptureStore(root/f'{number:02d}-groups-{policy}');metrics=RunMetrics()
            adapter=adapter_factory(states);driver=driver_factory();manager=ReplicatorCaptureManager(c,driver,store,metrics)
            pipeline=CapturePipeline(c,adapter,manager,store,metrics)
            if policy=='uniform':pipeline.scheduler=UniformScheduler([z['id'] for z in c['zones']],c['capture_policy'])
            with ResourceSampler(metrics):result=await pipeline.run()
            row={'groups_configured':number,'policy':policy,'result':result,'metrics':metrics.summary()}
            atomic_json(store.root/'benchmark-result.json',row);report.append(row)
    atomic_json(root/'benchmark-comparison.json',{'trials':report,'native_visual_acceptance_complete':False})
    return report
