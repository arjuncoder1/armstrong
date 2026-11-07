import time
import unittest
import cv2
import numpy as np
from aiohttp.test_utils import TestClient, TestServer
from aiohttp import web
from utils.dashboard import Dashboard, BrowserCapture


class CaptureTests(unittest.TestCase):
    def test_only_latest_frame_is_retained(self):
        capture = BrowserCapture()
        capture.put(np.zeros((2, 2, 3)))
        capture.put(np.ones((2, 2, 3)))
        ok, image = capture.read()
        self.assertTrue(ok)
        self.assertTrue(image.all())
        self.assertLess(time.monotonic() - capture.at, 0.1)
        self.assertFalse(capture.read()[0])


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    browser_camera = True

    async def asyncSetUp(self):
        self.dash = Dashboard(browser_camera=self.browser_camera)
        app = web.Application()
        app.router.add_get('/state', self.dash._state)
        app.router.add_post('/command', self.dash._command)
        app.router.add_get('/camera', self.dash._camera)
        self.client = TestClient(TestServer(app))
        self.t = '?t=' + self.dash.token
        try:
            await self.client.start_server()
        except PermissionError:
            await self.client.close()
            self.skipTest("Environment prohibits TCP sockets")

    async def asyncTearDown(self):
        await self.dash.stop()
        await self.client.close()

    async def test_token_guards_every_route(self):
        self.assertEqual((await self.client.get('/state?t=wrong')).status, 403)
        self.assertEqual((await self.client.post('/command?t=wrong', data='home')).status, 403)
        self.assertEqual((await self.client.get('/camera?t=wrong')).status, 403)
        self.assertEqual(self.dash.drain(), set())

    async def test_commands_and_state(self):
        self.assertEqual((await self.client.post('/command' + self.t, data='rm -rf')).status, 400)
        for command in ('c', 'home'):
            self.assertEqual((await self.client.post('/command' + self.t, data=command)).status, 200)
        self.assertEqual(self.dash.drain(), {'c', 'home'})
        self.assertEqual(self.dash.drain(), set())
        self.dash.status = {'control': 'nobody'}
        self.dash.show('overhead', np.zeros((2, 2, 3), np.uint8))
        self.dash.show('tracking', np.zeros((2, 2, 3), np.uint8))
        self.dash.log('hello')
        state = await (await self.client.get('/state' + self.t)).json()
        self.assertEqual(state['control'], 'nobody')
        self.assertEqual(state['views'], ['overhead'])  # the tracking view has its own place on the page
        self.assertTrue(state['log'][-1].endswith('hello'))
        self.assertTrue(state['camera'])

    async def test_camera_frames_and_disconnect(self):
        ws = await self.client.ws_connect('/camera' + self.t)
        self.assertFalse(self.dash.fresh)
        _, jpeg = cv2.imencode('.jpg', np.zeros((480, 640, 3), np.uint8))
        await ws.send_bytes(jpeg.tobytes())
        self.assertTrue((await ws.receive_json())['next'])
        self.assertTrue(self.dash.fresh)
        self.assertTrue(self.dash.capture.read()[0])
        self.assertEqual((await self.client.get('/camera' + self.t)).status, 409)
        self.dash._last_frame -= 1
        self.assertFalse(self.dash.fresh)
        await ws.close()
        self.assertFalse(self.dash.fresh)

    async def test_bad_frame_disconnects(self):
        ws = await self.client.ws_connect('/camera' + self.t)
        await ws.send_bytes(b'not jpeg')
        await ws.receive()
        self.assertFalse(self.dash.fresh)


class LocalWebcamTests(DashboardTests):
    browser_camera = False

    async def test_no_browser_camera(self):
        self.assertEqual((await self.client.get('/camera' + self.t)).status, 404)
        state = await (await self.client.get('/state' + self.t)).json()
        self.assertFalse(state['camera'])

    async def test_camera_frames_and_disconnect(self):
        self.skipTest("--dashboard without --browser has no browser camera")

    async def test_bad_frame_disconnects(self):
        self.skipTest("--dashboard without --browser has no browser camera")

    async def test_commands_and_state(self):
        self.skipTest("covered by DashboardTests")
