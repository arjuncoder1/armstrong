"""No camera, model or arm needed: `uv run python -m unittest test_blackjack`."""
import http.server
import json
import threading
import unittest

import hand
from cards import Detection, split_table, vote
from station import Station, StationError


class HandTest(unittest.TestCase):
    def test_totals(self):
        self.assertEqual(hand.total(['KH', '7S']), (17, False))
        self.assertEqual(hand.total(['AH', '6S']), (17, True))
        self.assertEqual(hand.total(['AH', '6S', '9D']), (16, False))
        self.assertEqual(hand.total(['AH', 'AS', '9D']), (21, True))
        self.assertEqual(hand.total(['10C', 'QD', '2H']), (22, False))

    def test_blackjack_and_bust(self):
        self.assertTrue(hand.is_blackjack(['AS', 'JD']))
        self.assertFalse(hand.is_blackjack(['7S', '7D', '7H']))
        self.assertTrue(hand.is_bust(['10C', 'QD', '2H']))

    def test_dealer_stands_on_soft_17(self):
        self.assertFalse(hand.dealer_hits(['AH', '6S']))
        self.assertTrue(hand.dealer_hits(['10H', '6S']))

    def test_outcome(self):
        self.assertEqual(hand.outcome(['10C', 'QD', '2H'], ['10H', '10S', '5C']), 'dealer')  # player busts first
        self.assertEqual(hand.outcome(['AS', 'KD'], ['10H', '5S', '6C']), 'player')  # blackjack beats 21
        self.assertEqual(hand.outcome(['10S', '8D'], ['10H', '8C']), 'push')
        self.assertEqual(hand.outcome(['10S', '8D'], ['10H', '6C', '9D']), 'player')


class TableTest(unittest.TestCase):
    def test_split_dedupes_corners_and_drops_weak(self):
        dets = [Detection('KH', .9, .2, .2), Detection('KH', .8, .3, .3),  # two corners of one card
                Detection('5S', .9, .5, .8), Detection('9D', .3, .6, .8)]  # 9D too weak
        self.assertEqual(split_table(dets), {'dealer': ['KH'], 'player': ['5S']})

    def test_vote_needs_majority(self):
        reads = [{'dealer': ['KH'], 'player': ['5S', '2C']}, {'dealer': ['KH'], 'player': ['5S']},
                 {'dealer': ['KH'], 'player': ['5S']}]
        self.assertEqual(vote(reads), {'dealer': ['KH'], 'player': ['5S']})


class FakeStation(http.server.BaseHTTPRequestHandler):
    states: list[str] = []
    prompts: list[str] = []

    def do_GET(self):
        self.reply({'state': self.states.pop(0) if len(self.states) > 1 else self.states[0], 'last_error': 'x'})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])) or b'{}')
        if self.path == '/start':
            self.prompts.append(body['prompt'])
        self.reply({'state': 'starting'})

    def reply(self, payload):
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class StationTest(unittest.TestCase):
    def setUp(self):
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FakeStation)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.station = Station(f'http://127.0.0.1:{self.server.server_address[1]}', timeout_s=2)
        FakeStation.prompts = []

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_run_waits_for_idle(self):
        FakeStation.states = ['idle', 'running', 'running', 'idle']
        self.assertEqual(self.station.run('deal', poll_s=0.01)['state'], 'idle')
        self.assertEqual(FakeStation.prompts, ['deal'])

    def test_refuses_when_busy(self):
        FakeStation.states = ['running']
        with self.assertRaises(StationError):
            self.station.run('deal')
        self.assertEqual(FakeStation.prompts, [])

    def test_error_state_raises(self):
        FakeStation.states = ['idle', 'error']
        with self.assertRaises(StationError):
            self.station.run('deal', poll_s=0.01)


if __name__ == '__main__':
    unittest.main()
