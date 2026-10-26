"""Run the native laboratory Flow diagnostic with bounded local resources.

Uses an already installed compatible Kit and licensed NVIDIA extensions. No
download, credential, driver, full-scene or production action is performed.
"""
import argparse
import json
from pathlib import Path

from bounded_process import run_bounded
from host_budget import exclusive_heavy_work
from restore_scene import atomic_json, no_links, bounded_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--run-name', required=True)
    parser.add_argument('--kit-root', required=True)
    parser.add_argument('--flow-extension', required=True)
    parser.add_argument('--flow-schema-extension', required=True)
    parser.add_argument('--license-receipt', required=True)
    parser.add_argument('--recipe-stage', required=True)
    parser.add_argument('--duration-s', type=float, default=10)
    parser.add_argument('--resolution', choices=('320x180','1280x720','1920x1080'), default='1920x1080')
    parser.add_argument('--physics-collision', action='store_true')
    parser.add_argument('--measure-fields', action='store_true')
    parser.add_argument('--runtime-state', default='flow-diagnostic-runtime-state',
                        help='Relative directory in the workspace; reuse only with the same SDK/extension set')
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', args.run_name):
        raise ValueError('Use a plain unique diagnostic run name')
    if not 0 < args.duration_s <= 30:
        raise ValueError('The diagnostic is limited to 30 simulated seconds')
    if json.loads(Path(args.license_receipt).read_text()).get('accepted') is not True:
        raise RuntimeError('An existing explicit NVIDIA license acceptance receipt is required')
    work = no_links(args.workspace)
    runtime_state = bounded_path(work, args.runtime_state)
    kit = Path(args.kit_root).resolve(strict=True)
    executable = kit/'kit/kit.exe'
    if not executable.is_file() or not (kit/'extscache').is_dir():
        raise ValueError('Expected an installed Kit application build with kit/kit.exe and extscache')
    paths = [Path(args.flow_extension).resolve(strict=True), Path(args.flow_schema_extension).resolve(strict=True)]
    for path, name in zip(paths, ('omni.flowusd', 'omni.usd.schema.flow')):
        if not path.name.startswith(name+'-') or not (path/'config/extension.toml').is_file():
            raise ValueError('Expected the explicit installed '+name+' extension directory')
    source = Path(args.recipe_stage).resolve(strict=True)
    if not source.with_name('recipe.json').is_file():
        raise ValueError('The factory source must include its original recipe.json digest')
    scripts = Path(__file__).resolve().parent
    with exclusive_heavy_work(work):
        run = no_links(work/args.run_name)
        run.mkdir(exist_ok=False)
        context = {'duration_sim_s':args.duration_s, 'capture_resolution_px':[int(x) for x in args.resolution.split('x')],
                   'physics_collision':args.physics_collision, 'measure_fields':args.measure_fields,
                   'recipe_stage':str(source), 'output':str(run/'probe')}
        atomic_json(run/'context.private.json', context)
        dependencies = '"omni.flowusd" = {}\n"omni.usd.schema.flow" = {}\n'
        if args.physics_collision:
            dependencies += '"omni.physx" = {}\n"omni.physx.stageupdate" = {}\n'
        experience = (scripts/'renderer_control.kit').read_text()
        experience = experience.replace('[dependencies]', '[dependencies]\n'+dependencies)
        experience = experience.replace('Renderer Negative Control', 'Native Flow Diagnostic')
        experience = experience.replace('No fire, Flow or physics: native renderer initialization only',
                                        'Native laboratory Flow visibility and optional PhysX collision test')
        experience = experience.replace('rtx.flow.enabled = false', 'rtx.flow.enabled = true')
        experience = experience.replace('rtx.flow.compositeEnabled = false', 'rtx.flow.compositeEnabled = true')
        (run/'diagnostic.kit').write_text(experience, encoding='utf-8')
        command = [str(executable), str(run/'diagnostic.kit'), '--no-window', '--/app/vulkan=false',
                   '--disable-crashreporter', '--portable-root', str(runtime_state),
                   '--ext-folder', str(kit/'extscache'), '--/app/extensions/registryEnabled=false',
                   '--/app/enableStdoutOutput=true', '--/log/flushStandardStreamOutput=true',
                   '--/exts/omnistream.local/probeContext='+str(run/'context.private.json'),
                   '--exec', str(scripts/'probe_flow_viewport.py')]
        for path in paths:
            command += ['--ext-path', str(path)]
        result = run_bounded(command, run/'host', ram_bytes=11_500_000_000,
                             ram_stop_bytes=10_500_000_000, vram_ceiling_bytes=15_000_000_000,
                             vram_stop_bytes=14_000_000_000, timeout_s=600,
                             min_available_ram_bytes=4_000_000_000)
        print(json.dumps(result), flush=True)
        return 0 if result['exit_code']==0 and result['reason']=='normal_exit' else 1


if __name__ == '__main__':
    raise SystemExit(main())
