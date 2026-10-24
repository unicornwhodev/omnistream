"""Create an isolated 4x4 qualification overlay; never write the full case."""
from pathlib import Path
import argparse, copy, hashlib, json, math, os
import numpy as np


def source_manifest(root):
    rows=[]
    for path in sorted(root.rglob('*')):
        if path.is_symlink():raise ValueError('Canonical source contains a symlink')
        if path.is_file():
            with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            rows.append({'path':path.relative_to(root).as_posix(),'bytes':path.stat().st_size,'sha256':digest})
    if not rows:raise ValueError('Canonical source is empty')
    raw=json.dumps(rows,sort_keys=True,separators=(',',':')).encode()
    return {'files':rows,'content_sha256':hashlib.sha256(raw).hexdigest()}


def prepare(source, output):
    from pxr import Usd,UsdGeom
    from fireviewer_capture.config import validate_config
    from fireviewer_capture.usd_cameras import create_configured_cameras,read_camera
    from fireviewer_capture.models import aware_time
    source=Path(source).resolve(strict=True);output=Path(output).resolve()
    if output==source or output.is_relative_to(source):raise ValueError('Pilot outputs must stay outside the canonical case')
    if output.exists():raise ValueError('A pilot revision must use a new directory')
    original=json.loads((source/'omnistream-geographic.json').read_text())
    if original['tile_counts']!=[40,40] or original['tile_size_m']!=500:raise ValueError('Expected the prepared 20 km case')
    selected=[f'tile_{x:02d}_{y:02d}' for x in range(18,22) for y in range(18,22)]
    baseline=source_manifest(source);output.mkdir(parents=True)
    (output/'full-case-before.json').write_text(json.dumps(baseline,indent=2)+'\n')
    config=copy.deepcopy(json.loads((source/'capture/event-v1/configuration.json').read_text()))
    config['scenario_id']=config['scenario_id']+'-pilot16'
    config['scene_revision']='pilot16-'+baseline['content_sha256'][:16]
    config['qualification_scope']={'id':'pilot-l4-16tiles','canonical_full_case_sha256':baseline['content_sha256'],
                                  'tile_ids':selected,'area_km2':4,'production_case':False,
                                  'checkpoints_compatible_with_full_case':False}
    cache={};mesh_hashes={};checks=[]
    def ground(xy):
        values=[];size=original['tile_size_m'];ox,oy=original['origin_local_m']
        for x,y in xy:
            ident=f'tile_{math.floor((x-ox)/size):02d}_{math.floor((y-oy)/size):02d}'
            if ident not in selected:raise ValueError('Pilot camera or ray leaves its explicit scope')
            if ident not in cache:
                path=source/'terrain'/ident/'lod1.usdc'
                stage=Usd.Stage.Open(str(path),load=Usd.Stage.LoadNone)
                points=np.asarray(UsdGeom.Mesh.Get(stage,'/Tile/Terrain').GetPointsAttr().Get(),dtype=np.float64)
                n=math.isqrt(len(points))
                if n*n!=len(points) or n!=501 or not np.isfinite(points).all():raise ValueError('Expected the verified 1 m render mesh')
                grid=points.reshape(n,n,3);cache[ident]=(grid[0,0,0],grid[0,0,1],grid[:,:,2].copy())
                with path.open('rb') as stream:mesh_hashes[ident]=hashlib.file_digest(stream,'sha256').hexdigest()
            west,north,z=cache[ident];u=float(np.clip(x-west,0,500));v=float(np.clip(north-y,0,500))
            i=min(499,int(u));j=min(499,int(v));a=u-i;b=v-j
            values.append((1-a)*(1-b)*z[j,i]+a*(1-b)*z[j,i+1]+(1-a)*b*z[j+1,i]+a*b*z[j+1,i+1])
        return np.asarray(values,dtype=float)
    for zone in config['zones']:
        for ring in zone['geometry']['coordinates']:
            for point in ring:point[0]*=.1;point[1]*=.1
    for camera in config['cameras']:
        camera['id']='pilot_'+camera['id'];camera['usd_path']='/World/Cameras/'+camera['id']
        eye=np.asarray(camera['position_m'],dtype=float);target=np.asarray(camera['look_at_m'],dtype=float)
        eye[:2]*=.1;target[:2]*=.1;target[2]=ground([target[:2]])[0]+4
        eye[2]=ground([eye[:2]])[0]+(4 if camera['id'].endswith('_05') else 180)
        length=np.linalg.norm(eye[:2]-target[:2]);n=max(3,math.ceil(length/2)+1);alpha=np.linspace(0,1,n)
        xy=(1-alpha[:,None])*eye[:2]+alpha[:,None]*target[:2];z=ground(xy)
        eye[2]=max(eye[2],float(np.max((z[:-1]+2-alpha[:-1]*target[2])/(1-alpha[:-1])))+.01)
        clearance=(1-alpha)*eye[2]+alpha*target[2]-z
        if clearance.min()<1.999:raise ValueError('Pilot camera terrain clearance failed')
        camera.update(position_m=eye.tolist(),look_at_m=target.tolist(),
                      pose_provenance='pilot-only virtual design; heights from verified 1 m render terrain, not a field survey or native 0.5 m DEM')
        checks.append({'camera_id':camera['id'],'minimum_render_terrain_clearance_m':float(clearance.min()),
                       'vegetation_building_occlusion_checked':False,'native_dem_camera_validation':False})
    for zone in config['zones']:zone['camera_ids']=['pilot_'+key for key in zone['camera_ids']]
    config['camera_design_validation']={'field_surveyed':False,'source_grid_m':1,'source_kind':'verified_render_terrain',
                                       'native_source_grid_m':.5,'full_zone_image_coverage_validated':False}
    config=validate_config(config)
    stage=Usd.Stage.CreateNew(str(output/'pilot-cameras.usda'));world=UsdGeom.Xform.Define(stage,'/World');stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageMetersPerUnit(stage,1);UsdGeom.SetStageUpAxis(stage,'Z');stage.SetTimeCodesPerSecond(1)
    canonical=Usd.Stage.Open(str(source/'capture_ready_v2.usda'),load=Usd.Stage.LoadNone)
    for prim in Usd.PrimRange(canonical.GetPrimAtPath('/World/Cameras')):
        if prim.IsA(UsdGeom.Camera):stage.OverridePrim(prim.GetPath()).SetActive(False)
    create_configured_cameras(stage,config);stage.GetRootLayer().Save()
    # Strong pilot cameras override the read-only referenced full scene.
    camera_rel=os.path.relpath(output/'pilot-cameras.usda',output)
    scene_rel=os.path.relpath(source/'capture_ready_v2.usda',output).replace('\\','/')
    pilot=Usd.Stage.CreateNew(str(output/'pilot.usda'))
    pilot.GetRootLayer().subLayerPaths=['./'+camera_rel,scene_rel]
    pilot.SetDefaultPrim(pilot.GetPrimAtPath('/World'))
    UsdGeom.SetStageMetersPerUnit(pilot,1);UsdGeom.SetStageUpAxis(pilot,'Z');pilot.SetTimeCodesPerSecond(1)
    pilot.SetStartTimeCode(0);pilot.SetEndTimeCode((aware_time(config['period']['end_exclusive'])-aware_time(config['period']['start'])).total_seconds())
    pilot.GetRootLayer().customLayerData={'qualification:scope':'pilot-l4-16tiles','qualification:productionCase':False,
                                         'source:fullCaseContentSHA256':baseline['content_sha256'],'science:acceptance':'pending'}
    pilot.GetRootLayer().Save()
    manifest=copy.deepcopy(original);manifest.update(active_tiles=selected,qualification_scope='pilot-l4-16tiles',overview_camera=config['cameras'][0]['usd_path'])
    (output/'omnistream-geographic.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (output/'configuration.json').write_text(json.dumps(config,indent=2)+'\n')
    (output/'camera-checks.json').write_text(json.dumps(checks,indent=2)+'\n')
    actual=Usd.Stage.Open(str(output/'pilot.usda'),load=Usd.Stage.LoadNone)
    metadata=[read_camera(actual,c,config) for c in config['cameras']]
    (output/'camera-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    after=source_manifest(source)
    if after!=baseline:raise ValueError('Canonical source changed while preparing the pilot')
    receipt={'schema':'fireviewer.pilot-scope.v1','scope':'pilot-l4-16tiles','tile_ids':selected,
             'territory_m':[2000,2000],'canonical_territory_m':[20000,20000],
             'canonical_before_sha256':baseline['content_sha256'],'canonical_after_sha256':after['content_sha256'],
             'canonical_files':len(baseline['files']),'canonical_unchanged':True,'cameras':len(metadata),
             'camera_mesh_sha256':mesh_hashes,'pilot_entrypoint':'pilot.usda','actual_kit_tested':False,
             'scientific_acceptance':False,'exports_held':True}
    (output/'preparation-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(prepare(args.source,args.output)))
