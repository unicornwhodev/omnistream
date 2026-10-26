"""Project verified incident evidence into scene XY, without inventing fire state.

The output is a versioned constraint package, not GeoJSON in a non-WGS84 CRS,
not an ignition mask and not a propagation adapter. Source topology, holes,
precision and feature properties survive unchanged. Terrain Z remains unknown
until sampled against the verified native height data.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from prepare_incident_inputs import encoded, write
from restore_scene import bounded_path, sha256


def make_projector(georeferencing):
    from pyproj import Transformer
    g = georeferencing
    if (g['horizontal_crs'] != 'EPSG:2154' or g['meters_per_unit'] != 1 or
            g['up_axis'] != 'Z' or g['local_axes'] != {
                'X':'East','Y':'North','Z':'absolute NGF-IGN69 elevation'}):
        raise ValueError('Unsupported scene coordinate convention')
    anchor = g['local_origin_l93_m']
    bounds = g['bounds_l93_m']
    if (len(anchor) != 3 or len(bounds) != 4 or
            not all(math.isfinite(x) for x in (*anchor,*bounds)) or anchor[2] != 0 or
            bounds[0] >= bounds[2] or bounds[1] >= bounds[3]):
        raise ValueError('Invalid map anchor or bounds')
    expected_matrix = [[1,0,0,anchor[0]], [0,1,0,anchor[1]], [0,0,1,0], [0,0,0,1]]
    if g['local_to_l93_column_vector'] != expected_matrix:
        raise ValueError('Scene matrix is not the declared anchor translation')
    transformer = Transformer.from_crs('EPSG:4326','EPSG:2154',always_xy=True)
    inverse = Transformer.from_crs('EPSG:2154','EPSG:4326',always_xy=True)

    def point(position):
        if (len(position) != 2 or not all(type(v) in (int,float) and math.isfinite(v) for v in position)
                or not -180 <= position[0] <= 180 or not -90 <= position[1] <= 90):
            raise ValueError('Expected finite longitude/latitude without an invented altitude')
        east,north = transformer.transform(*position,errcheck=True)
        lon,lat = inverse.transform(east,north,errcheck=True)
        if max(abs(lon-position[0]),abs(lat-position[1])) > 1e-7:
            raise ValueError('Coordinate round trip exceeded 1e-7 degrees')
        return [east-anchor[0],north-anchor[1]]
    return point, [bounds[0]-anchor[0],bounds[1]-anchor[1],bounds[2]-anchor[0],bounds[3]-anchor[1]]


def project_geometry(geometry, point):
    depths = {'Point':0,'MultiPoint':1,'LineString':1,'MultiLineString':2,'Polygon':2,'MultiPolygon':3}
    kind = geometry.get('type')
    if kind not in depths:
        raise ValueError('Unsupported evidence geometry: '+str(kind))
    points = []
    def visit(coordinates, depth):
        if not isinstance(coordinates,list) or not coordinates:
            raise ValueError('Empty or malformed evidence geometry')
        if depth:
            return [visit(child,depth-1) for child in coordinates]
        projected = point(coordinates)
        points.append(projected)
        return projected
    result = {'type':kind,'coordinates':visit(geometry['coordinates'],depths[kind])}
    bounds = [min(p[0] for p in points),min(p[1] for p in points),
              max(p[0] for p in points),max(p[1] for p in points)]
    return result,bounds,len(points)


def prepare(inputs, georeferencing, output):
    inputs,output = Path(inputs).resolve(strict=True),Path(output).resolve()
    source_manifest = inputs/'sources_manifest.json'
    manifest = json.loads(source_manifest.read_text(encoding='utf-8'))
    # No network lookup is performed during coordinate preparation.
    rows = manifest['files']
    verified = {}
    for row in rows:
        path = bounded_path(inputs,row['path'])
        if path.stat().st_size != row['bytes'] or sha256(path) != row['sha256']:
            raise ValueError('Published input changed: '+row['path'])
        verified[row['path']] = row
    scenario_path = inputs/'scenario.json'
    scenario = json.loads(scenario_path.read_text(encoding='utf-8'))
    index = json.loads((inputs/'sources/cartography/die-justin/index.json').read_text(encoding='utf-8'))
    geo_path = Path(georeferencing).resolve(strict=True)
    geo = json.loads(geo_path.read_text(encoding='utf-8'))
    project,bounds = make_projector(geo)
    files,summary = [],[]
    for ref in index['snapshots']:
        relative = 'sources/cartography/die-justin/'+ref['path']
        if verified[relative]['sha256'] != ref['sha256']:
            raise ValueError('Snapshot index differs from frozen source manifest')
        snapshot = json.loads(bounded_path(inputs,relative).read_text(encoding='utf-8'))
        features,counts = [],{}
        for ordinal,feature in enumerate(snapshot['features']['features']):
            geometry,box,n = project_geometry(feature['geometry'],project)
            properties = feature['properties']
            kind = properties['kind']
            counts[kind] = counts.get(kind,0)+1
            inside = box[0]>=bounds[0] and box[1]>=bounds[1] and box[2]<=bounds[2] and box[3]<=bounds[3]
            identity = hashlib.sha256(encoded({'source':ref['sha256'],'ordinal':ordinal})).hexdigest()
            features.append({'constraint_id':identity,'source_feature_ordinal':ordinal,
                'properties':properties,'geometry_local_xy_m':geometry,'bounds_local_xy_m':box,
                'coordinate_count':n,'within_scene_xy_bounds':inside,
                'terrain_height_m':None,'exact_simulator_annotation':False})
        relative_output = 'snapshots/'+ref['sha256']+'.json'
        data = {'schema':'fireviewer.scene-incident-constraints.v1',
                'snapshot_id':ref['id'],'source_sha256':ref['sha256'],
                'source_date':snapshot['date'],'source_kind':snapshot['kind'],
                'source_status':snapshot.get('status'),'source_coverage':snapshot.get('coverage'),
                'observed_from':snapshot.get('observedFrom'),'observed_to':snapshot.get('observedTo'),
                'base_geometry':snapshot.get('baseGeometry'),'constraints':features}
        blob = encoded(data)
        write(bounded_path(output,relative_output),blob)
        files.append({'path':relative_output,'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()})
        outside = [f for f in features if not f['within_scene_xy_bounds']]
        summary.append({'id':ref['id'],'source_kind':ref['kind'],'feature_counts':counts,
                        'features_outside_scene_xy':len(outside),
                        'outside_kinds':sorted({f['properties']['kind'] for f in outside})})
    report = {'schema':'fireviewer.projected-incident-inputs.v1',
        'scenario_sha256':sha256(scenario_path),'source_manifest_sha256':sha256(source_manifest),
        'georeferencing_sha256':sha256(geo_path),'source_crs':'EPSG:4326','scene_crs':'EPSG:2154',
        'local_origin_l93_m':geo['local_origin_l93_m'],'local_xy_bounds_m':bounds,
        'scene_revision':scenario['map_binding']['scene_revision'],
        'snapshots':summary,'files':files,
        'daily_schedule':scenario['simulation_daily_frames'],
        'geometry_topology_preserved':True,'height_sampling':'pending',
        'all_geometry_within_scene_xy':all(r['features_outside_scene_xy']==0 for r in summary),
        'independent_geodetic_validation':False,'propagation_adapter_connected':False,
        'perimeter_is_not_an_ignition_mask':True,'physical_fire_calibrated':False,
        'rules':scenario['rules']}
    write(output/'projection-receipt.json',encoded(report))
    return {'snapshots':len(summary),'simulation_days':len(report['daily_schedule']),
            'all_geometry_within_scene_xy':report['all_geometry_within_scene_xy'],
            'features_outside_scene_xy':sum(x['features_outside_scene_xy'] for x in summary),
            'height_sampling':'pending','propagation_adapter_connected':False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',required=True)
    parser.add_argument('--georeferencing',required=True)
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.inputs,args.georeferencing,args.output)))
