import unittest
from render_policy import MINIMAL_POLICY, enforce_policy, assert_policy


class Settings(dict):
    def set(self, key, value):
        self[key] = value


class RenderPolicyTests(unittest.TestCase):
    def test_reactivated_native_default_is_corrected_and_recorded(self):
        settings = Settings(MINIMAL_POLICY)
        settings['/rtx/flow/pathTracingEnabled'] = True
        result = enforce_policy(settings)
        self.assertTrue(result['before']['/rtx/flow/pathTracingEnabled'])
        self.assertFalse(result['after']['/rtx/flow/pathTracingEnabled'])

    def test_mid_run_change_is_rejected(self):
        settings = Settings(MINIMAL_POLICY)
        settings['/persistent/rtx/modes/pt/enabled'] = True
        with self.assertRaisesRegex(RuntimeError, 'pt/enabled'):
            assert_policy(settings)

    def test_failed_write_is_not_accepted_as_applied(self):
        class ReadOnly(Settings):
            def set(self, key, value):
                pass
        with self.assertRaises(RuntimeError):
            enforce_policy(ReadOnly())

    def test_explicit_flow_diagnostic_does_not_select_path_tracing(self):
        settings = Settings(MINIMAL_POLICY)
        result = enforce_policy(settings, flow_volume_gate=True)
        self.assertTrue(result['after']['/rtx/flow/pathTracingEnabled'])
        self.assertEqual(settings['/rtx/rendermode'], 'MinimalRendering')
        self.assertFalse(settings['/persistent/rtx/modes/pt/enabled'])
        self.assertFalse(settings['/persistent/rtx/modes/rt2/enabled'])
        settings['/persistent/rtx/modes/pt/enabled'] = True
        with self.assertRaises(RuntimeError):
            assert_policy(settings, flow_volume_gate=True)
