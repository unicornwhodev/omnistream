"""Explicit Colab Kit bootstrap, using the compatible environment's Python."""
import argparse,asyncio,os
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--scene',required=True)
    p.add_argument('--output',required=True);p.add_argument('--adapter-factory');p.add_argument('--fixture-log')
    p.add_argument('--gpu-timing-factory');p.add_argument('--max-groups',type=int)
    p.add_argument('--residency-factory')
    a=p.parse_args()
    if os.name!='posix' or not Path('/content').is_dir():raise RuntimeError('Keep this scene and Kit execution on Colab')
    if os.environ.get('OMNI_KIT_ACCEPT_EULA')!='YES':raise RuntimeError('Use the existing recorded NVIDIA agreement; this script does not accept a license')
    if bool(a.adapter_factory)==bool(a.fixture_log):p.error('Choose one real engine factory or qualification fixture log')
    from isaacsim import SimulationApp
    app=SimulationApp({'headless':True,'renderer':'RayTracedLighting','disable_viewport_updates':True,
                       'width':1280,'height':720,'anti_aliasing':3})
    import omni.usd
    from fireviewer_capture.runner import run_in_current_kit
    async def run():
        result=await omni.usd.get_context().open_stage_async(str(Path(a.scene).resolve()),load_set=omni.usd.UsdContextInitialLoadSet.LOAD_NONE)
        if isinstance(result,tuple) and not result[0]:raise RuntimeError('Kit could not open the configured USD stage')
        return await run_in_current_kit(a.config,a.output,a.adapter_factory,a.fixture_log,a.max_groups,a.gpu_timing_factory,a.residency_factory)
    task=asyncio.ensure_future(run())
    try:
        while not task.done():app.update()
        print(task.result())
    finally:app.close()


if __name__=='__main__':main()
