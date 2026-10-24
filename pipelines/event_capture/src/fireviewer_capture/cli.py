"""Preparation and inspection commands; GPU execution is an explicit Kit entry."""
import argparse
import json
from pathlib import Path
from .config import load_config,config_identity
from .storage import CaptureStore,file_sha,atomic_json
from .models import ContractError


def verify_output(directory):
    store=CaptureStore(directory);groups=list(store.root.glob('groups/*.json'));images=0
    for path in groups:
        group=json.loads(path.read_text())
        if not group.get('verified') or len(group['frames'])!=5:raise ContractError('Incomplete group manifest')
        ids=set()
        for frame in group['frames']:
            image=store._path(frame['image_path']);meta=store._path(frame['metadata_path'])
            if file_sha(image)!=frame['image_sha256'] or file_sha(meta)!=frame['metadata_sha256']:
                raise ContractError('Capture changed after group commit')
            record=json.loads(meta.read_text());ids.add(record['camera']['id'])
            if (record['sim_time_us']!=group['sim_time_us'] or record['state_fingerprint']!=group['state_fingerprint'] or
                    record['image']['sha256']!=frame['image_sha256']):raise ContractError('Incoherent capture group')
            images+=1
        if ids!=set(group['camera_ids']):raise ContractError('Wrong camera group')
    return {'groups_verified':len(groups),'images_verified':images,'checkpoint':store.read_checkpoint(),
            'native_render_and_scientific_acceptance_not_implied':True}


def main(argv=None):
    p=argparse.ArgumentParser(description='Backend-independent event capture preparation and verification')
    sub=p.add_subparsers(dest='command',required=True)
    v=sub.add_parser('validate-config');v.add_argument('config')
    v=sub.add_parser('verify-output');v.add_argument('directory')
    v=sub.add_parser('prepare-camera-layer');v.add_argument('config');v.add_argument('output')
    v=sub.add_parser('prepare-entrypoint');v.add_argument('config');v.add_argument('output')
    v.add_argument('--camera-layer',required=True);v.add_argument('--base-scene',required=True)
    a=p.parse_args(argv)
    if a.command=='verify-output':result=verify_output(a.directory)
    else:
        c=load_config(a.config);result={'config_sha256':config_identity(c),'cameras':len(c['cameras']),'zones':len(c['zones'])}
        if a.command=='prepare-entrypoint':
            from .usd_cameras import create_capture_entrypoint
            result.update(create_capture_entrypoint(a.output,c,a.camera_layer,a.base_scene))
        if a.command=='prepare-camera-layer':
            from pxr import Usd,UsdGeom
            from .usd_cameras import create_configured_cameras
            path=Path(a.output).resolve()
            if path.exists():raise ContractError('Camera preparation never overwrites an existing layer')
            path.parent.mkdir(parents=True,exist_ok=True);stage=Usd.Stage.CreateNew(str(path))
            world=UsdGeom.Xform.Define(stage,'/World');stage.SetDefaultPrim(world.GetPrim())
            UsdGeom.SetStageUpAxis(stage,'Z');UsdGeom.SetStageMetersPerUnit(stage,1)
            create_configured_cameras(stage,c);stage.GetRootLayer().Save()
            result.update(camera_layer=str(path),sha256=file_sha(path),virtual_design_only=True)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
