"""Enforce the requested native renderer policy at initialization boundaries."""

MINIMAL_POLICY = {
    '/rtx/rendermode': 'MinimalRendering',
    '/rtx/minimal/mode': 3,
    '/persistent/rtx/modes/minimal/enabled': True,
    '/persistent/rtx/modes/pt/enabled': False,
    '/persistent/rtx/modes/rt/enabled': False,
    '/persistent/rtx/modes/rt2/enabled': False,
    '/rtx/flow/enabled': True,
    '/rtx/flow/compositeEnabled': True,
    '/rtx/flow/pathTracingEnabled': False,
    '/rtx/flow/rayTracedShadowsEnabled': False,
    '/rtx/flow/rayTracedReflectionsEnabled': False,
    '/rtx/flow/rayTracedTranslucencyEnabled': False,
}


CLASSIC_LIGHT_OPTIONS = {
    # Current Kit uses the DLSS family; execMode 4 selects native-resolution
    # DLAA. The former op=2 was legacy FXAA, not TAA, and was reset by Kit.
    '/rtx/post/aa/op': 3,
    '/rtx/post/dlss/execMode': 4,
    '/rtx-transient/dlssg/enabled': False,
    '/rtx/directLighting/enabled': True,
    '/rtx/indirectDiffuse/enabled': False,
    '/rtx/reflections/enabled': False,
    '/rtx/translucency/enabled': False,
    '/rtx/ambientOcclusion/enabled': False,
    '/rtx/shadows/enabled': False,
    '/rtx/raytracing/subsurface/enabled': False,
}


def read_policy(settings, keys=None):
    return {key: settings.get(key) for key in (MINIMAL_POLICY if keys is None else keys)}


def expected_policy(*, flow_volume_gate=False, renderer_mode='minimal', lightweight=False,
                    allow_realtime_path_tracing=False):
    expected = {**MINIMAL_POLICY, '/rtx/flow/pathTracingEnabled': bool(flow_volume_gate)}
    if renderer_mode == 'realtime_classic':
        expected.update({
            '/rtx/rendermode': 'RaytracedLighting',
            '/persistent/rtx/modes/minimal/enabled': False,
            '/persistent/rtx/modes/rt/enabled': True,
        })
        if lightweight:
            expected.update(CLASSIC_LIGHT_OPTIONS)
    elif renderer_mode == 'realtime2':
        if allow_realtime_path_tracing is not True:
            raise ValueError('RTX Real-Time 2.0 uses path tracing; explicit selection approval is required')
        expected.update({
            '/rtx/rendermode': 'RealTimePathTracing',
            '/persistent/rtx/modes/minimal/enabled': False,
            '/persistent/rtx/modes/rt/enabled': False,
            '/persistent/rtx/modes/rt2/enabled': True,
        })
        if lightweight:
            expected.update({'/rtx/rtpt/maxBounces':1,
                             '/rtx/rtpt/maxSpecularAndTransmissionBounces':1,
                             '/rtx/rtpt/maxVolumeBounces':1,
                             '/rtx-transient/dlssg/enabled':False})
    elif renderer_mode != 'minimal':
        raise ValueError('Unknown renderer policy; choose minimal, realtime_classic or explicit realtime2')
    return expected


def assert_policy(settings, *, flow_volume_gate=False, renderer_mode='minimal', lightweight=False,
                  allow_realtime_path_tracing=False):
    expected = expected_policy(flow_volume_gate=flow_volume_gate, renderer_mode=renderer_mode,
                               lightweight=lightweight, allow_realtime_path_tracing=allow_realtime_path_tracing)
    actual = read_policy(settings, expected)
    if actual != expected:
        changed = [f'{key}: expected {value!r}, read {actual[key]!r}'
                   for key, value in expected.items() if actual[key] != value]
        raise RuntimeError('Native rendering policy changed: '+', '.join(changed))
    return actual


def enforce_policy(settings, *, flow_volume_gate=False, renderer_mode='minimal', lightweight=False,
                   allow_realtime_path_tracing=False):
    expected = expected_policy(flow_volume_gate=flow_volume_gate, renderer_mode=renderer_mode,
                               lightweight=lightweight, allow_realtime_path_tracing=allow_realtime_path_tracing)
    before = read_policy(settings, expected)
    for key, value in expected.items():
        settings.set(key, value)
    return {'before': before, 'after': assert_policy(settings,
            flow_volume_gate=flow_volume_gate, renderer_mode=renderer_mode, lightweight=lightweight,
            allow_realtime_path_tracing=allow_realtime_path_tracing)}
