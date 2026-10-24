import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest

from helpers import config,front,state,pipeline,FakeDriver,ROOT
from fireviewer_capture.activity import ZoneActivityTracker
from fireviewer_capture.scheduler import CaptureScheduler
from fireviewer_capture.config import validate_config
from fireviewer_capture.models import Activity,ContractError,simulated_us
from fireviewer_capture.simulation import RecordedStateAdapter,AdapterCapabilities,MissingSimulationAdapter,SynchronizationError
from fireviewer_capture.storage import CaptureStore


class ActivityTests(unittest.TestCase):
    def test_short_smoke_pulse_preserves_both_transitions_despite_hysteresis(self):
        c=config(1);c['activity'].update(enter_hold_sim_s=30,exit_hold_sim_s=90)
        t=ZoneActivityTracker(c['zones'],c['activity']);s=CaptureScheduler(['zone_01'],c['capture_policy'])
        observed=[]
        for snapshot in [state(),state(10,[front(phase=Activity.INACTIVE,smoke=True)]),state(11,[])]:
            reports=t.update(snapshot);s.observe(snapshot,reports);requests=s.requests_at(snapshot.sim_time_us)
            observed.extend(requests)
            for request in requests:s.commit(request)
        self.assertEqual([r.sim_time_us for r in observed],[0,10_000_000,11_000_000])
        self.assertIn('smoke_appeared_or_entered',observed[1].reasons)
        self.assertIn('smoke_disappeared_or_exited',observed[2].reasons)
        self.assertEqual(observed[1].activity,Activity.EARLY_SMOKE)

    def test_front_passes_between_two_zones_with_exit_margin(self):
        c=config(2);c['activity'].update(enter_margin_m=0,exit_margin_m=10)
        c['zones'][0]['geometry']={'type':'Polygon','coordinates':[[[0,0],[100,0],[100,100],[0,100],[0,0]]]}
        c['zones'][1]['geometry']={'type':'Polygon','coordinates':[[[100,0],[200,0],[200,100],[100,100],[100,0]]]}
        t=ZoneActivityTracker(c['zones'],c['activity'])
        a=t.update(state(0,[front(point=[99,50])]))
        b=t.update(state(1,[front(point=[101,50])]))
        d=t.update(state(2,[front(point=[111,50])]))
        self.assertTrue(a[0].front_ids);self.assertFalse(a[1].front_ids)
        self.assertTrue(b[0].front_ids and b[1].front_ids)
        self.assertIn('front_disappeared_or_exited',d[0].transition_reasons)
        self.assertTrue(d[1].front_ids)

    def test_multiple_fronts_and_smoke_do_not_imply_visible_flame(self):
        c=config(1);t=ZoneActivityTracker(c['zones'],c['activity'])
        r=t.update(state(0,[front(ident='a'),front(ident='b',phase=Activity.DECLINING,smoke=True)]))[0]
        self.assertEqual(r.front_ids,('a','b'));self.assertEqual(r.activity,Activity.ACTIVE_RAPID)

    def test_unknown_or_absent_activity_is_not_a_negative(self):
        c=config(1);t=ZoneActivityTracker(c['zones'],c['activity'])
        with self.assertRaises(ContractError):t.update(type(state())(0,'missing',None,{},{}))
        with self.assertRaises(ContractError):t.update(state(0,[front(phase=Activity.UNKNOWN)]))

    def test_post_extinction_window_ends_and_negative_sampling_survives(self):
        c=config(1);c['activity']['post_extinction_window_sim_s']=60
        t=ZoneActivityTracker(c['zones'],c['activity'])
        t.update(state(0,[front()]));r=t.update(state(10,[]))[0]
        self.assertEqual(r.activity,Activity.POST_EXTINCTION)
        self.assertEqual(r.related_front_ids,('front_01',))
        self.assertEqual(t.update(state(70,[]))[0].activity,Activity.INACTIVE)

    def test_reversed_simulated_time_is_rejected(self):
        c=config(1);t=ZoneActivityTracker(c['zones'],c['activity']);t.update(state(10))
        with self.assertRaises(ContractError):t.update(state(9))


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_two_five_and_ten_active_groups_share_one_clock(self):
        for groups in [1,2,5,10]:
            with self.subTest(groups=groups),tempfile.TemporaryDirectory() as d:
                c=config(groups,duration_s=1);p,driver,store,m=pipeline(d,c,[state(0,[front(i,ident=f'f{i}') for i in range(groups)])])
                result=await p.run()
                self.assertEqual(result['committed_groups'],groups)
                self.assertEqual(m.counts['images_written_new'],groups*5)
                self.assertLessEqual(driver.peak,5);self.assertEqual(driver.initializations,1)
                self.assertEqual(driver.created,driver.destroyed);self.assertFalse(driver.handles)
                records=[json.loads(f.read_text()) for f in Path(d).glob('groups/*.json')]
                self.assertEqual({r['sim_time_us'] for r in records},{0})
                self.assertEqual(len({r['state_fingerprint'] for r in records}),1)

    async def test_inactive_period_has_sparse_negatives_and_no_extra_render(self):
        with tempfile.TemporaryDirectory() as d:
            c=config(2,duration_s=20000);p,driver,store,m=pipeline(d,c,[state()]);await p.run()
            self.assertEqual(m.counts['images_written_new'],10)
            self.assertEqual(len(driver.calls),2)

    async def test_cap_smaller_than_five_keeps_same_state_across_batches(self):
        with tempfile.TemporaryDirectory() as d:
            c=config(1,duration_s=1,cap=2);p,driver,store,m=pipeline(d,c,[state(0,[front()])]);await p.run()
            self.assertEqual([len(x['cameras']) for x in driver.calls],[2,2,1])
            contexts=[ctx for call in driver.calls for ctx in call['contexts'].values()]
            self.assertEqual(len({x['state_fingerprint'] for x in contexts}),1)
            self.assertTrue(all(x['annotations']['fronts'][0]['flame_visible'] is None for x in contexts))

    async def test_rapid_activity_events_are_not_skipped_by_hourly_advance_bound(self):
        with tempfile.TemporaryDirectory() as d:
            c=config(1,duration_s=20);c['activity']['enter_hold_sim_s']=30
            states=[state(),state(10,[front(phase=Activity.INACTIVE,smoke=True)],'smoke_on'),state(11,[],'smoke_off')]
            p,driver,store,m=pipeline(d,c,states);await p.run()
            times=sorted(json.loads(f.read_text())['sim_time_us'] for f in Path(d).glob('groups/*.json'))
            self.assertEqual(times,[0,10_000_000,11_000_000])

    async def test_resume_mid_group_reuses_verified_images_without_rerender(self):
        with tempfile.TemporaryDirectory() as d:
            c=config(1,duration_s=1,cap=2);states=[state(0,[front()])]
            p,driver,store,m=pipeline(d,c,states,FakeDriver(fail_on_call=2))
            with self.assertRaises(RuntimeError):await p.run()
            self.assertEqual(len(list(Path(d).glob('frames/*/*.png'))),2)
            self.assertFalse(list(Path(d).glob('groups/*.json')));self.assertFalse(driver.handles)
            resumed,second,store,metrics=pipeline(d,c,states);await resumed.run()
            self.assertEqual(metrics.counts['images_reused_verified'],2)
            self.assertEqual(metrics.counts['images_written_new'],3)
            self.assertEqual(sum(len(x['cameras']) for x in second.calls),3)
            self.assertEqual(len(list(Path(d).glob('frames/*/*.png'))),5)
            self.assertEqual(len(list(Path(d).glob('groups/*.json'))),1)

    async def test_incomplete_or_corrupt_image_is_quarantined_and_repaired(self):
        with tempfile.TemporaryDirectory() as d:
            c=config(1,duration_s=1,cap=2);states=[state()]
            p,driver,store,m=pipeline(d,c,states,FakeDriver(fail_on_call=2))
            with self.assertRaises(RuntimeError):await p.run()
            victim=next(Path(d).glob('frames/*/*.png'));victim.write_bytes(b'incomplete')
            resumed,driver,store,m=pipeline(d,c,states);await resumed.run()
            self.assertTrue(list(Path(d).glob('quarantine/*')))
            self.assertEqual(m.counts['images_written_new'],4)
            self.assertEqual(m.counts['images_reused_verified'],1)

    async def test_complete_resume_performs_no_gpu_work(self):
        with tempfile.TemporaryDirectory() as d:
            c=config(1,duration_s=1);p,driver,store,m=pipeline(d,c,[state()]);await p.run()
            second,driver,store,m=pipeline(d,c,[state()]);result=await second.run()
            self.assertTrue(result['already_complete']);self.assertEqual(driver.created,0)

    async def test_changed_seed_or_scene_refuses_resume(self):
        with tempfile.TemporaryDirectory() as d:
            c=config(1,duration_s=1);p,_,_,_=pipeline(d,c,[state()]);await p.run()
            changed=copy.deepcopy(c);changed['seed']+=1;changed['render']['seed']=changed['seed']
            second,driver,_,_=pipeline(d,changed,[state()])
            with self.assertRaises(ContractError):await second.run()
            self.assertEqual(driver.created,0)

    async def test_timeline_only_freeze_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            c=config(1,duration_s=1);p,driver,store,m=pipeline(d,c,[state()])
            p.adapter.capabilities=AdapterCapabilities(True,True,False,True,('timeline','external_smoke'),'timeline-only is insufficient')
            with self.assertRaises(MissingSimulationAdapter):await p.run()
            self.assertFalse(driver.calls)

    async def test_drifting_external_state_prevents_group_commit(self):
        with tempfile.TemporaryDirectory() as d:
            c=config(1,duration_s=1);p,driver,store,m=pipeline(d,c,[state()])
            def drift():p.adapter._events[0]['engine_state']['drift']=True
            driver.on_render=drift
            with self.assertRaises(SynchronizationError):await p.run()
            self.assertFalse(list(Path(d).glob('groups/*.json')));self.assertFalse(driver.handles)

    async def test_images_conform_to_capture_json_schema(self):
        import jsonschema
        with tempfile.TemporaryDirectory() as d:
            c=config(1,duration_s=1);p,_,_,_=pipeline(d,c,[state(0,[front()])]);await p.run()
            schema=json.loads((ROOT/'schemas/capture-image.schema.json').read_text())
            for f in Path(d).glob('frames/*/*.json'):jsonschema.Draft202012Validator(schema,format_checker=jsonschema.FormatChecker()).validate(json.loads(f.read_text()))

    async def test_bounded_products_over_repeated_camera_sets(self):
        with tempfile.TemporaryDirectory() as d:
            c=config(10,duration_s=200);c['capture_policy']['inactive']['interval_sim_s']=60
            p,driver,store,m=pipeline(d,c,[state()]);await p.run()
            self.assertLessEqual(m.counts['peak_cached_products'],5)
            self.assertEqual(driver.created,driver.destroyed)
            self.assertEqual(m.counts['images_written_new'],200)

    async def test_missing_gpu_timing_is_null_not_fabricated_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p,_,_,metrics=pipeline(d,config(1,duration_s=1),[state()]);await p.run()
            self.assertIsNone(metrics.summary()['gpu_render_execution_s'])


class ConfigTests(unittest.TestCase):
    def test_reference_has_fifty_cameras_and_exactly_forty_seven_days(self):
        from datetime import timedelta
        from fireviewer_capture.models import aware_time
        c=json.loads((ROOT/'examples/reference_50_cameras.json').read_text());validate_config(c)
        self.assertEqual(len(c['cameras']),50);self.assertEqual(len(c['zones']),10)
        self.assertEqual(aware_time(c['period']['end_exclusive'])-aware_time(c['period']['start']),timedelta(days=47))
        self.assertEqual(c['render']['resolution_px'],[1280,720])
    def test_duplicate_cameras_nonfinite_and_wall_interval_types_rejected(self):
        for key,value in [('acceleration',True),('acceleration',float('nan'))]:
            c=config();c[key]=value
            with self.assertRaises((ContractError,ValueError)):validate_config(c)
        c=config();c['zones'][0]['camera_ids'][0]=c['zones'][0]['camera_ids'][1]
        with self.assertRaises(ContractError):validate_config(c)
        for value in [True,float('inf'),-.1]:
            with self.assertRaises(ContractError):simulated_us(value)


if __name__=='__main__':unittest.main(verbosity=2)
