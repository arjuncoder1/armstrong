import unittest
from unittest.mock import patch
import start_when_cool as recovery


def observation(state='commissioning'):
    return {'status': {'state': state, 'arms': {'left': True, 'right': True},
                       'control_adapter': 'manifest-makerarm-v1'},
            'measured': {side: {'motor_temps_c': [53.0] * 7} for side in ('left', 'right')}}


class RecoveryTests(unittest.TestCase):
    def test_complete_cool_feedback(self):
        self.assertEqual(len(recovery.temperatures(observation())['right']), 7)

    def test_reject_invalid_or_missing_feedback(self):
        for values in ([], [53] * 6, [float('nan')] * 7, [True] * 7, [None] * 7):
            with self.subTest(values=values):
                obs = observation()
                obs['measured']['right']['motor_temps_c'] = values
                with self.assertRaises(ValueError):
                    recovery.temperatures(obs)
        obs = observation()
        obs['status']['arms']['right'] = False
        with self.assertRaises(ValueError):
            recovery.temperatures(obs)

    def test_readiness_requires_native_idle_and_both_arms(self):
        self.assertFalse(recovery.powered_ready(observation()))
        obs = observation('idle')
        self.assertTrue(recovery.powered_ready(obs))
        obs['status']['arms']['right'] = False
        self.assertFalse(recovery.powered_ready(obs))

    @patch.object(recovery.time, 'sleep')
    @patch.object(recovery, 'observe', return_value=observation('idle'))
    @patch.object(recovery, 'active', return_value=True)
    @patch.object(recovery, 'service')
    def test_successful_handoff(self, service, *_):
        self.assertEqual(recovery.start_powered(), 0)
        self.assertEqual([call.args for call in service.call_args_list],
                         [('stop', 'manifest-makerarm-setup'), ('start', 'manifest-makerarm')])

    @patch.object(recovery.subprocess, 'run')
    @patch.object(recovery.time, 'sleep')
    @patch.object(recovery, 'active', return_value=False)
    @patch.object(recovery, 'service')
    def test_failure_stops_powered_before_restoring_preview(self, service, *_):
        self.assertEqual(recovery.start_powered(), 1)
        self.assertEqual([call.args for call in service.call_args_list][-2:],
                         [('stop', 'manifest-makerarm'), ('start', 'manifest-makerarm-setup')])


if __name__ == '__main__':
    unittest.main()
