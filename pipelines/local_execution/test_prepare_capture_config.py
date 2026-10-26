import copy
import json
from pathlib import Path
import tempfile
import unittest

from prepare_capture_config import derive_config, prepare
from fireviewer_capture.models import Activity, SimulationState, ZoneReport
from fireviewer_capture.scheduler import CaptureScheduler


class CapturePreparationTests(unittest.TestCase):
    def setUp(self):
        path=Path(__file__).resolve().parents[1]/'event_capture/examples/reference_50_cameras.json'
        self.source=json.loads(path.read_text())

    def test_periodic_reduction_keeps_events_negatives_and_original_inputs(self):
        original=copy.deepcopy(self.source)
        c=derive_config(self.source)
        self.assertEqual(self.source,original)
        self.assertEqual(c['cameras'],original['cameras'])
        self.assertEqual(c['zones'],original['zones'])
        self.assertEqual(c['activity'],original['activity'])
        self.assertEqual(c['adapter'],original['adapter'])
        scheduler=CaptureScheduler(['fixture-zone'],c['capture_policy'])
        def observe(t, transitions=()):
            state=SimulationState(t*1_000_000,'fixture',(),{}, {})
            report=ZoneReport('fixture-zone',state.sim_time_us,Activity.INACTIVE,Activity.INACTIVE,
                              (),(),transitions,None)
            scheduler.observe(state,[report])
            return scheduler.requests_at(state.sim_time_us)
        first=observe(0)
        self.assertIn('initial_negative_or_state_sample',first[0].reasons)
        scheduler.commit(first[0])
        self.assertEqual(observe(21600),[])
        event=observe(21601,('fixture_state_change',))
        self.assertEqual(len(event),1)
        self.assertIn('fixture_state_change',event[0].reasons)
        self.assertEqual(scheduler.intervals[Activity.INACTIVE],28800*1_000_000)
        self.assertEqual(scheduler.intervals[Activity.ACTIVE_RAPID],120*1_000_000)

    def test_double_application_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'twice'):
            derive_config(derive_config(self.source))

    def test_repeated_preparation_is_idempotent_and_preserves_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.json';target=root/'local.json'
            source.write_text(json.dumps(self.source))
            before=source.read_bytes()
            self.assertEqual(prepare(source,target),prepare(source,target))
            target.write_text('{"user_edit":true}')
            with self.assertRaisesRegex(ValueError,'differs'):
                prepare(source,target)
            self.assertEqual(source.read_bytes(),before)
            self.assertEqual(json.loads(target.read_text()),{'user_edit':True})

    def test_fractional_intervals_are_rounded_up_at_microsecond_precision(self):
        self.source['capture_policy']['active_rapid']['interval_sim_s']=1
        c=derive_config(self.source)
        self.assertEqual(c['capture_policy']['active_rapid']['interval_sim_s'],1.333334)


if __name__=='__main__':unittest.main()
