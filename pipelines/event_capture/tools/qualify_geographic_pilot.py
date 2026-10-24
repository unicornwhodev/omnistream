"""Native renderer qualification of a loaded, isolated geographic pilot.

This is a static rendering test. It supplies no fire observations, propagation,
weather, smoke or physical validation. Call ``run`` in the owning Kit process;
never start a second Kit beside the viewer. Native media stay in the output.
"""
from datetime import timedelta
from pathlib import Path
import gc
import json


async def run(stage, geographic, pilot_root, output):
    import omni.kit.app
    import omni.timeline
    import omni.usd
    import carb.settings
    from fireviewer_capture.benchmark import subset_config
    from fireviewer_capture.cli import verify_output
    from fireviewer_capture.config import validate_config
    from fireviewer_capture.metrics import ResourceSampler, RunMetrics
    from fireviewer_capture.models import SimulationState, aware_time
    from fireviewer_capture.omniverse_driver import OmniverseRenderDriver
    from fireviewer_capture.orchestrator import CapturePipeline
    from fireviewer_capture.qualification import compare_repeated_view, resource_stability
    from fireviewer_capture.replicator import ReplicatorCaptureManager
    from fireviewer_capture.simulation import RecordedStateAdapter, AdapterCapabilities, SynchronizationError
    from fireviewer_capture.storage import CaptureStore, atomic_json

    root=Path(pilot_root).resolve(strict=True);out=Path(output).resolve()
    if out==root or not out.is_relative_to(root):raise ValueError('Qualification output must stay inside the isolated pilot')
    if out.exists():raise ValueError('Use a fresh qualification directory')
    if Path(stage.GetRootLayer().realPath).resolve()!=root/'pilot.usda':raise ValueError('Open the isolated pilot first')
    preparation=json.loads((root/'preparation-receipt.json').read_text())
    if preparation['scope']!='pilot-l4-16tiles' or not preparation['canonical_unchanged']:raise ValueError('Pilot preparation is not verified')
    # The launcher owns this process and explicitly declares no external fire
    # or smoke producer for this baseline. Refuse Flow/dynamic scene content.
    for prim in stage.Traverse():
        if 'flow' in prim.GetTypeName().lower():raise ValueError('Static baseline cannot freeze a Flow simulation')
        if any(a.GetNumTimeSamples() for a in prim.GetAttributes() if a.GetName().startswith('xformOp:')):
            raise ValueError('Static baseline cannot qualify animated assets')
    config=json.loads((root/'configuration.json').read_text())
    # A pilot-only override; the source production configuration stays intact.
    config['render']['rt_subframes']=32
    config['render']['dlss_quality_mode']=2
    settings=carb.settings.get_settings();previous_dlss=settings.get('/rtx/post/dlss/execMode')
    timeline=omni.timeline.get_timeline_interface();saved_time=timeline.get_current_time();saved_auto=timeline.is_auto_updating()
    if timeline.is_playing():raise ValueError('Pause the pilot before static qualification')
    timeline.set_auto_update(False);timeline.set_current_time(0);timeline.commit_silently()
    out.mkdir(parents=True)
    report={'schema':'fireviewer.geographic-pilot-render-qualification.v1','qualification_scope':'pilot-l4-16tiles',
            'production_case':False,'real_justin_scene':True,'fixture_only':False,'static_renderer_test_only':True,
            'production_fire_adapter':'missing','fire_and_smoke_qualified':False,'scientific_acceptance':False,
            'final_operational_acceptance':False,'canonical_content_sha256':preparation['canonical_before_sha256'],
            'render_override':{'rt_subframes':32,'dlss_quality_mode':2},'results':{},'exports_held':True}

    def status(phase,**values):
        atomic_json(out/'progress.json',{'phase':phase,'qualification_scope':'pilot-l4-16tiles',**values})

    class StaticTimelineAdapter(RecordedStateAdapter):
        capabilities=AdapterCapabilities(True,True,True,True,('declared_static_test_input','kit_timeline'),
                                         'Static geographic renderer test; no fire or smoke engine integration')
        def __init__(self):
            super().__init__([SimulationState(0,'static-pilot-renderer-test',(),
                {'weather':'not used in static renderer qualification'},
                {'static_renderer_test_only':True,'fire_adapter_missing':True,'external_producers':'none in this owned static baseline'})],
                'pilot16-static-renderer-test')
            timeline.pause();timeline.set_current_time(0);timeline.commit_silently()
        async def read_state(self):
            if timeline.is_playing() or abs(timeline.get_current_time()-self.now/1e6)>1e-9:
                raise SynchronizationError('Static pilot timeline changed outside the capture owner')
            return await super().read_state()
        async def advance_to(self,target_sim_time_us,acceleration):
            # This test has exactly one capture instant at zero. No accelerated
            # propagation or simulated performance claim is made.
            timeline.set_current_time(target_sim_time_us/1e6);timeline.commit_silently()
            return await super().advance_to(target_sim_time_us,acceleration)
        async def restore(self,checkpoint):
            timeline.set_current_time(checkpoint['sim_time_us']/1e6);timeline.commit_silently()
            await super().restore(checkpoint)

    class CompletePilotResidency:
        async def prepare(self,current_stage,contexts,current_config):
            s=geographic.status
            if current_stage!=stage or s.get('qualificationScope')!='pilot-l4-16tiles' or not s.get('completeAssetResidency'):
                raise ValueError('Pilot asset residency is incomplete')
            for ident in geographic.tiles:
                if not stage.GetPrimAtPath('/World/Terrain/'+ident).IsLoaded():raise ValueError('Pilot terrain is not loaded')
            for path in geographic.asset_tiles | geographic.prototype_paths:
                if not stage.GetPrimAtPath(path).IsLoaded():raise ValueError('Pilot asset payload is not loaded')
            return {'visible_assets_complete':True,'qualification_scope':'pilot-l4-16tiles',
                    'coverage_is_limited_to_pilot':True,'complete_declared_pilot_assets':True}

    async def case(groups,name,cap=5):
        c=subset_config(config,groups)
        c['scenario_id']+='-static-render-test'
        c['period']['end_exclusive']=(aware_time(c['period']['start'])+timedelta(seconds=1)).isoformat()
        c['render'].update(max_active_products=cap,max_cached_products=5)
        c=validate_config(c);path=out/name;store=CaptureStore(path);metrics=RunMetrics()
        driver=OmniverseRenderDriver(residency_provider=CompletePilotResidency())
        manager=ReplicatorCaptureManager(c,driver,store,metrics)
        pipeline=CapturePipeline(c,StaticTimelineAdapter(),manager,store,metrics)
        with ResourceSampler(metrics):result=await pipeline.run()
        verification=verify_output(path)
        if verification['images_verified']!=groups*5:raise AssertionError('Unexpected static image count')
        if driver.products or driver.unsolicited_callbacks:raise AssertionError('Unused product or unsolicited writer callback')
        row={'groups':groups,'result':result,'images_verified':verification['images_verified'],
             'metrics':metrics.summary(),'remaining_products':len(driver.products),'unsolicited_writer_callbacks':driver.unsolicited_callbacks}
        atomic_json(path/'native-metrics.json',row);return row

    try:
        settings.set('/rtx/post/dlss/execMode',2)
        if settings.get('/rtx/post/dlss/execMode')!=2:raise ValueError('DLSS quality setting was not applied')
        for groups in (1,2,5,10):
            status('static_capture_matrix',groups=groups)
            report['results'][f'{groups}_groups']=await case(groups,f'{groups:02d}-groups')
        samples=[]
        for cycle in range(9):
            status('camera_cycles',cycle=cycle)
            await case(1,f'cycles/{cycle:02d}')
            gc.collect()
            for _ in range(4):await omni.kit.app.get_app().next_update_async()
            metrics=RunMetrics();sampler=ResourceSampler(metrics);sampler.sample()
            samples.append({'cycle':cycle,**metrics.samples[-1]})
        report['results']['resource_stability']=resource_stability(samples,3,32*1024**2,8*1024**2)
        report['results']['resource_samples']=samples
        def metadata(cycle):
            return next(p for p in (out/f'cycles/{cycle:02d}').glob('frames/*/*.json')
                        if json.loads(p.read_text())['camera']['id']==c['id'])
        c=config['cameras'][0]
        report['results']['static_ghosting_numeric']=compare_repeated_view(metadata(0),metadata(1),2,12)
        report['results']['main_viewport_camera_modified']=False
        report['renderer_gates_passed']=report['results']['resource_stability']['passed'] and report['results']['static_ghosting_numeric']['passed']
        atomic_json(out/'report.json',report);status('static_renderer_tests_complete',fire_adapter='missing')
        return report
    except Exception as error:
        status('failed',error_type=type(error).__name__,error=str(error)[:1000]);raise
    finally:
        timeline.pause();timeline.set_current_time(saved_time);timeline.set_auto_update(saved_auto);timeline.commit_silently()
        if previous_dlss is not None:settings.set('/rtx/post/dlss/execMode',previous_dlss)
