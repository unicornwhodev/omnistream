import copy
import unittest

from project_incident_constraints import make_projector, project_geometry


class GeometryProjectionTests(unittest.TestCase):
    def test_holes_and_multipart_order_are_preserved(self):
        geometry = {'type':'MultiPolygon','coordinates':[
            [[[0,0],[3,0],[3,3],[0,0]],[[1,1],[2,1],[1,2],[1,1]]],
            [[[5,5],[6,5],[5,6],[5,5]]]]}
        before = copy.deepcopy(geometry)
        result,bounds,count = project_geometry(geometry,lambda p:[p[0]+10,p[1]+20])
        self.assertEqual(geometry,before)
        self.assertEqual(len(result['coordinates']),2)
        self.assertEqual(len(result['coordinates'][0]),2)
        self.assertEqual(result['coordinates'][0][1][0],[11,21])
        self.assertEqual(bounds,[10,20,16,26])
        self.assertEqual(count,12)

    def test_empty_and_unknown_geometry_are_not_silently_dropped(self):
        for geometry in ({'type':'LineString','coordinates':[]},
                         {'type':'GeometryCollection','geometries':[]}):
            with self.assertRaises(ValueError):
                project_geometry(geometry,lambda p:p)

    def test_projection_is_xy_metres_and_does_not_invent_z(self):
        geo = {'horizontal_crs':'EPSG:2154','meters_per_unit':1,'up_axis':'Z',
            'local_axes':{'X':'East','Y':'North','Z':'absolute NGF-IGN69 elevation'},
            'local_origin_l93_m':[700000,6600000,0],
            'local_to_l93_column_vector':[[1,0,0,700000],[0,1,0,6600000],[0,0,1,0],[0,0,0,1]],
            'bounds_l93_m':[690000,6590000,710000,6610000]}
        project,bounds = make_projector(geo)
        x,y = project([3,46.5])
        self.assertAlmostEqual(x,0,places=5)
        self.assertAlmostEqual(y,0,places=5)
        self.assertEqual(bounds,[-10000,-10000,10000,10000])
        for bad in ([3,46.5,100],[float('nan'),0],[300,0]):
            with self.assertRaises(ValueError):project(bad)
