"""Launch a minimal .kit experience using the isolated Isaac Python kernel.

The pip kernel intentionally has no bundled Python directory. Use its supported
KitApp Python bootstrap rather than invoking that kernel's kit.exe directly.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--license-receipt', required=True)
    parser.add_argument('kit_arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    receipt = json.loads(Path(args.license_receipt).read_text(encoding='utf-8'))
    if receipt.get('accepted') is not True:
        raise RuntimeError('Existing NVIDIA authorization receipt is required')
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    kit_arguments = args.kit_arguments
    if kit_arguments and kit_arguments[0] == '--':
        kit_arguments = kit_arguments[1:]
    if not kit_arguments or not Path(kit_arguments[0]).is_file():
        raise RuntimeError('An existing explicit .kit experience is required')
    import isaacsim  # Boots the kernel with the current Python environment.
    from kit_app import KitApp
    app = KitApp()
    app.startup(kit_arguments)
    import carb.settings
    settings = carb.settings.get_settings()
    keys = ('/rtx/rendermode','/rtx/minimal/mode',
            '/persistent/rtx/modes/rt/enabled',
            '/persistent/rtx/modes/pt/enabled','/persistent/rtx/modes/rt2/enabled',
            '/persistent/rtx/modes/minimal/enabled',
            '/plugins/carb.tasking.plugin/threadCount',
            '/plugins/omni.tbb.globalcontrol/maxThreadCount',
            '/gpu/shadercompiler/warmcount','/gpu/shadercompiler/warmcountMax',
            '/gpu/shadercompiler/warmcountPerGB',
            '/rtx/shaderDb/concurrency',
            '/rtx-transient/psoDb/serializeAllCompiles',
            '/rtx/materialDb/compileMdlAsLibrary',
            '/rtx/raytracing/debug/oneUberPermutation',
            '/rtx/raytracing/debug/uberThenDeferNonUber',
            '/exts/omni.kit.viewport.window/startup/disableWindowOnLoad')
    keys = (*keys, '/renderer/enabled', '/renderer/active')
    print('LOCAL_RUNTIME_SETTINGS '+json.dumps({k:settings.get(k) for k in keys}),flush=True)
    update_count = 0
    started = last_report = time.monotonic()
    max_update_s = 0.0
    while app.is_running():
        before = time.monotonic()
        app.update()
        update_count += 1
        after = time.monotonic()
        max_update_s = max(max_update_s, after-before)
        if after-last_report >= 5:
            print('LOCAL_RUNTIME_HEARTBEAT '+json.dumps({
                'wall_s':after-started,'completed_app_updates':update_count,
                'max_update_wall_s':max_update_s}),flush=True)
            last_report = after
    return app.shutdown()


if __name__ == '__main__':
    sys.exit(main())
