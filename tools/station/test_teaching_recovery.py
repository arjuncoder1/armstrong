import asyncio
import io
import json
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import makerarm_teaching
import proxy


class TeachingRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_rehooks_replacement_drivers(self):
        teaching = makerarm_teaching.Teaching.__new__(makerarm_teaching.Teaching)
        teaching.c = SimpleNamespace(_arms={'left': SimpleNamespace(), 'right': SimpleNamespace()})
        calls = []
        teaching.driver_call = lambda *args: calls.append(args)
        async def enter(body):
            teaching.c._arms[body['arm']].call('teach_enter', 'token')
            return {'status': 'recording'}
        with patch.object(makerarm_teaching.mac_teach.Teaching, 'start', side_effect=enter):
            result = await teaching.start({'arm': 'right'})
        self.assertEqual(result['status'], 'recording')
        self.assertEqual(calls, [('right', 'teach_enter', 'token')])

    def test_proxy_preserves_station_rejection(self):
        payload = b'{"arm":"right","ready":false}'
        codes = []
        handler = SimpleNamespace(command='POST', path='/api/teach/start',
            headers={'Content-Length': str(len(payload))}, rfile=io.BytesIO(payload), wfile=io.BytesIO(),
            send_response=codes.append, send_header=lambda *a: None, end_headers=lambda: None)
        app = SimpleNamespace(config={'body': 'makers'}, station='http://station')
        message = 'Hold the selected empty arm and confirm the workspace is clear'
        error = urllib.error.HTTPError('http://station', 409, 'Conflict', {},
                                       io.BytesIO(json.dumps({'error':message}).encode()))
        with patch('urllib.request.urlopen', side_effect=error):
            proxy.forward(handler, app)
        self.assertEqual(codes, [409])
        self.assertEqual(json.loads(handler.wfile.getvalue()), {'error': message})


if __name__ == '__main__':
    unittest.main()
