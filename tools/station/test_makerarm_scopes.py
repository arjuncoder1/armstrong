"""Regression: native reset replaces the arm objects after returning its response."""
import asyncio
from types import SimpleNamespace
import unittest
import numpy as np
from robots.types import ArmCommand
from makerarm_control import Bridge


class Arm:
    def __init__(self):
        self.last = None
    def write(self, command):
        self.last = command
    def is_alive(self):
        return True
    def hold(self):
        pass


class Controller:
    def __init__(self):
        self.state = 'idle'
        self._arms = {side: Arm() for side in ('left', 'right')}
    def arms_alive(self):
        return {side: True for side in self._arms}
    def _alarms(self):
        return {}
    def arm_states(self):
        return {side: {'positions_rad': [0.] * 6, 'gripper': .7,
                       'commanded_gripper': .7} for side in self._arms}
    def status(self):
        return {'state': self.state, 'arms': self.arms_alive()}
    async def start(self, *args):
        self.state = 'running'
    async def stop(self):
        self.state = 'idle'
    async def reset(self):
        self.state = 'resetting'
        # Just like native reset: replacement occurs after the response.
        return self.status()


class ScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_arm_and_jaw_guards_survive_async_driver_replacement(self):
        for selected in ('left', 'right'):
            with self.subTest(selected=selected):
                c = Controller()
                b = Bridge.__new__(Bridge)
                b.c = c
                b.lease = b.watch = b.scope = b.native_task = None
                b.obs = {}
                b.teaching = SimpleNamespace(active=False, public=lambda: {})
                b.cv = SimpleNamespace(busy=False)
                b.rest = SimpleNamespace(resting={}, public=lambda: {}, held=lambda: [], blocks=lambda arm: None)
                b.fd = SimpleNamespace(public=lambda: {'active': []}, blocks=lambda arm: None)
                b.install_scopes()
                await b.recover()
                c._arms = {side: Arm() for side in ('left', 'right')}
                c.state = 'idle'
                obs = b.observe(False)
                await b.action({'observation_id': obs['observation_id'], 'arm': selected,
                                'instruction': 'pick up cube', 'gripper_mode': 'hold', 'seconds': 1})
                try:
                    # Policy requests movement and jaw closure on BOTH sides.
                    for arm in c._arms.values():
                        arm.write(ArmCommand(np.ones(6) * .1, 0.))
                    for side, arm in c._arms.items():
                        np.testing.assert_allclose(arm.last.positions_rad, .1 if side == selected else 0.)
                        self.assertEqual(arm.last.gripper, .7)
                    # Reinstall is idempotent on the same drivers.
                    previous = c._arms[selected].write
                    b.install_scopes()
                    self.assertIs(c._arms[selected].write, previous)
                finally:
                    await b.stop()
                    b.watch.cancel()
                    try:
                        await b.watch
                    except asyncio.CancelledError:
                        pass


if __name__ == '__main__':
    unittest.main()
