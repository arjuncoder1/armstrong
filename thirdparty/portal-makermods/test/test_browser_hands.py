import time
import unittest
import cv2
import numpy as np
from aiohttp.test_utils import TestClient, TestServer
from aiohttp import web
from utils.browser_hands import BrowserHands, BrowserCapture


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


class BrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.browser = BrowserHands()
        app = web.Application()
        app.router.add_get('/camera', self.browser.camera)
        self.client = TestClient(TestServer(app))
        try:
            await self.client.start_server()
        except PermissionError:
            await self.client.close()
            self.skipTest("Environment prohibits TCP sockets")

    async def asyncTearDown(self):
        await self.browser.stop()
        await self.client.close()

    async def test_auth_frames_commands_and_disconnect(self):
        denied = await self.client.get('/camera?token=wrong')
        self.assertEqual(denied.status, 403)
        ws = await self.client.ws_connect('/camera?token=' + self.browser.token)
        self.assertFalse(self.browser.fresh)
        _, jpeg = cv2.imencode('.jpg', np.zeros((480, 640, 3), np.uint8))
        await ws.send_bytes(jpeg.tobytes())
        self.assertTrue((await ws.receive_json())['next'])
        self.assertTrue(self.browser.fresh)
        second = await self.client.get('/camera?token=' + self.browser.token)
        self.assertEqual(second.status, 409)
        await ws.send_str('c')
        await ws.send_bytes(jpeg.tobytes())
        await ws.receive_json()
        self.assertEqual(self.browser.drain(), {'c'})
        self.browser.last_frame -= 1
        self.assertFalse(self.browser.fresh)
        await ws.close()
        self.assertFalse(self.browser.fresh)
        self.assertEqual(self.browser.drain(), set())

    async def test_bad_frame_disconnects(self):
        ws = await self.client.ws_connect('/camera?token=' + self.browser.token)
        await ws.send_bytes(b'not jpeg')
        await ws.receive()
        self.assertFalse(self.browser.fresh)
