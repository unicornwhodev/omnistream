"""Derive explicit virtual camera heights from an official metric DEM on Colab."""
from pathlib import Path
import argparse,copy,hashlib,json,math,sys
import numpy as np


def prepare(config,dem,anchor,scene_revision):
    import rasterio
    from fireviewer_capture.config import validate_config
    result=copy.deepcopy(config);result['scene_revision']=scene_revision;checks=[]
    with rasterio.open(dem) as ds:
        if ds.crs.to_epsg()!=2154 or ds.res!=(.5,.5):raise ValueError('Expected official native metric Lambert-93 0.5 m DEM')
        def ground(xy):
            points=[(x+anchor[0],y+anchor[1]) for x,y in xy]
            z=np.ma.asarray(list(ds.sample(points,masked=True)))[:,0]
            if np.ma.getmaskarray(z).any() or not np.isfinite(z).all():raise ValueError('Missing DEM at a designed camera/target/ray')
            return np.asarray(z,dtype=float)
        for c in result['cameras']:
            eye=np.asarray(c['position_m'],dtype=float);target=np.asarray(c['look_at_m'],dtype=float)
            target[2]=ground([target[:2]])[0]+4
            height=4 if c['id'].endswith('_05') else 180
            eye[2]=ground([eye[:2]])[0]+height
            length=np.linalg.norm(eye[:2]-target[:2]);n=max(3,math.ceil(length/2)+1);alpha=np.linspace(0,1,n)
            xy=(1-alpha[:,None])*eye[:2]+alpha[:,None]*target[:2];gz=ground(xy)
            required=np.max((gz[:-1]+2-alpha[:-1]*target[2])/(1-alpha[:-1]))
            eye[2]=max(eye[2],float(required)+.01)
            clearance=(1-alpha)*eye[2]+alpha*target[2]-gz
            assert clearance.min()>=1.999
            c.update(position_m=eye.tolist(),look_at_m=target.tolist(),
                     pose_provenance='virtual design with native MNT-derived heights and sampled terrain line of sight; not a surveyed camera site')
            checks.append({'camera_id':c['id'],'terrain_ray_samples':n,'maximum_ray_sample_spacing_m':length/(n-1),
                           'minimum_terrain_clearance_m':float(clearance.min()),'camera_above_local_ground_m':float(eye[2]-gz[0]),
                           'vegetation_building_occlusion_checked':False,'surveillance_zone_coverage_optimized':False})
    result['camera_design_validation']={'terrain_line_of_sight_only':True,'field_surveyed':False,
        'full_zone_image_coverage_validated':False,'source_grid_m':.5,'source_crs':'EPSG:2154','height_datum':'NGF-IGN69'}
    return validate_config(result),checks


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--dem',required=True)
    p.add_argument('--anchor',nargs=2,type=float,required=True);p.add_argument('--scene-revision',required=True)
    p.add_argument('--output',required=True);a=p.parse_args()
    out=Path(a.output)
    if out.exists():raise ValueError('Write camera preparations to a new revision directory')
    config,checks=prepare(json.loads(Path(a.config).read_text()),a.dem,a.anchor,a.scene_revision);out.mkdir(parents=True)
    (out/'configuration.json').write_text(json.dumps(config,indent=2)+'\n')
    (out/'terrain-line-of-sight.json').write_text(json.dumps(checks,indent=2)+'\n')
    from pxr import Usd,UsdGeom
    from fireviewer_capture.usd_cameras import create_configured_cameras,read_camera
    stage=Usd.Stage.CreateNew(str(out/'cameras.usda'));world=UsdGeom.Xform.Define(stage,'/World');stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageUpAxis(stage,'Z');UsdGeom.SetStageMetersPerUnit(stage,1)
    create_configured_cameras(stage,config);stage.GetRootLayer().Save()
    actual=[read_camera(stage,c,config) for c in config['cameras']]
    (out/'composed-camera-metadata.json').write_text(json.dumps(actual,indent=2)+'\n')
    print(json.dumps({'cameras':len(actual),'terrain_rays_checked':len(checks),'actual_Kit_render_tested':False}))


if __name__=='__main__':main()
