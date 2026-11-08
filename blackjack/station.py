"""Client for the dreamlabs station API (`python -m robots.station`, default port 8091).

A deal is one Dream-1 run: POST /start with the prompt, then wait until the station is idle again (each run has a
fixed step count, so it ends on its own). Stop is always available and only makes the arms hold.
"""
import json
import time
import urllib.error
import urllib.request


class StationError(RuntimeError):
    pass


class Station:
    def __init__(self, url: str = 'http://127.0.0.1:8091', timeout_s: float = 90.0):
        self.url = url.rstrip('/')
        self.timeout_s = timeout_s

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=70) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise StationError(f'{method} {path}: {e.code} {e.read().decode(errors="replace")}') from e

    def status(self) -> dict:
        return self._call('GET', '/status')

    def stop(self) -> dict:
        return self._call('POST', '/stop', {})

    def run(self, prompt: str, poll_s: float = 0.5) -> dict:
        """One Dream-1 run with this prompt; returns the final status. Stops the run if it outlasts timeout_s."""
        state = self.status()['state']
        if state != 'idle':
            raise StationError(f'station is {state!r}, not idle')
        self._call('POST', '/start', {'prompt': prompt})
        deadline = time.monotonic() + self.timeout_s
        while True:
            s = self.status()
            if s['state'] == 'idle':
                return s
            if s['state'] == 'error':
                raise StationError(f'run failed: {s.get("last_error")}')
            if time.monotonic() > deadline:
                self.stop()
                raise StationError(f'run took longer than {self.timeout_s:g} s, stopped')
            time.sleep(poll_s)
