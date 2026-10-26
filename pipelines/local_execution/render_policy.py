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


def read_policy(settings):
    return {key: settings.get(key) for key in MINIMAL_POLICY}


def assert_policy(settings, *, flow_volume_gate=False):
    expected = {**MINIMAL_POLICY, '/rtx/flow/pathTracingEnabled': bool(flow_volume_gate)}
    actual = read_policy(settings)
    if actual != expected:
        changed = [key for key, value in expected.items() if actual[key] != value]
        raise RuntimeError('Native rendering policy changed: '+', '.join(changed))
    return actual


def enforce_policy(settings, *, flow_volume_gate=False):
    expected = {**MINIMAL_POLICY, '/rtx/flow/pathTracingEnabled': bool(flow_volume_gate)}
    before = read_policy(settings)
    for key, value in expected.items():
        settings.set(key, value)
    return {'before': before, 'after': assert_policy(settings, flow_volume_gate=flow_volume_gate)}
