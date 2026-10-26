import copy
import unittest
from prepare_incident_inputs import validate_daily_source, resolved_features


class PublishedDateTests(unittest.TestCase):
    def setUp(self):
        self.ref={'id':'daily-2026-08-09','date':'2026-08-09','sha256':'a'*64}
        self.frame={'date':'2026-08-09','sourceDate':'2026-07-17',
                    'status':'carried-forward','carryActivityForward':False,
                    'snapshot':dict(self.ref)}

    def test_carried_extent_can_have_older_observation_date(self):
        validate_daily_source(self.frame,self.ref)

    def test_future_observation_and_wrong_snapshot_are_rejected(self):
        bad=copy.deepcopy(self.frame);bad['sourceDate']='2026-08-10'
        with self.assertRaises(ValueError):validate_daily_source(bad,self.ref)
        bad=copy.deepcopy(self.frame);bad['snapshot']['date']='2026-07-17'
        with self.assertRaises(ValueError):validate_daily_source(bad,self.ref)

    def test_carried_geometry_does_not_carry_activity_and_keeps_holes(self):
        extent={'properties':{'kind':'affected'},'geometry':{'type':'Polygon',
                  'coordinates':[[[0,0],[3,0],[3,3],[0,0]],[[1,1],[2,1],[1,2],[1,1]]]}}
        flame={'properties':{'kind':'flame'},'geometry':{'type':'Point','coordinates':[1,1]}}
        source={'date':self.frame['date'],'features':{'features':[extent,flame]}}
        self.assertEqual(resolved_features(self.frame,source,{}),[extent])
        observed={**self.frame,'status':'observed'}
        self.assertEqual(resolved_features(observed,source,{}),[extent,flame])
