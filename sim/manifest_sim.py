"""manifest_sim: a fake Manifest station on 127.0.0.1:8191, backed by a Genesis sim of the two-arm rig.

    uv run sim/manifest_sim.py [--port 8191] [--headless | --viewer] [--backend metal|cpu]

It serves the routes `thirdparty/portal-makermods/src/manifest_bridge.py` uses (the station_proxy plugin's
/supervisor/*) and Manifest's built-in /v1/* ones. The sim steps on the main thread (OpenGL wants it on macOS);
the HTTP server and the lease watchdog run on their own threads. See sim/README.md.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

SIDES = ("left", "right")
MAX_LEAD_RAD = 0.12  # a CV target further than this from the measured joint is refused and ends the lease
LEASE_SILENCE_S = 2.0  # no frame for this long ends a CV lease
HOME_SPEED_RAD_S = 0.6
HOME_TOL_RAD = 0.05


class Refused(Exception):
    """Answered as HTTP 409 {"error": ...}."""


class Station:
    def __init__(self, world) -> None:
        self.world = world
        self.lock = threading.RLock()
        self.lease: dict | None = None  # the active lease
        self.last_lease: dict | None = None
        self.obs = 0
        self.stop_home = threading.Event()

    # ---- leases ----------------------------------------------------------------------------------------------

    def _end(self, reason: str) -> dict | None:
        with self.lock:
            lease = self.lease
            if lease is None:
                return self.last_lease
            lease.update(active=False, reason=reason, ended_at=time.time())
            self.lease, self.last_lease = None, lease
            if lease["kind"] == "home":
                self.stop_home.set()
            print(f"[station] {lease['kind']} lease {lease['id'][:8]} ended: {reason}")
            return lease

    def _public(self, lease: dict | None) -> dict | None:
        if lease is None:
            return None
        return {k: v for k, v in lease.items() if not k.startswith("_")}

    def watchdog(self) -> None:
        while True:
            time.sleep(0.1)
            with self.lock:
                lease = self.lease
                if lease and lease["kind"] == "cv" and time.monotonic() - lease["_last"] > LEASE_SILENCE_S:
                    self._end("watchdog: no frame for 2 s")

    def cv_start(self, body: dict) -> dict:
        with self.lock:
            if self.lease and self.lease["kind"] == "home":
                raise Refused("the arms are homing")
            if self.lease:
                self._end("replaced by a new CV lease")
            ident = uuid.uuid4().hex
            self.lease = {"id": ident, "kind": "cv", "active": True, "reason": None, "started_at": time.time(),
                          "_last": time.monotonic()}
            print(f"[station] cv lease {ident[:8]} open")
            return {"lease_id": ident, "lease": self._public(self.lease)}

    def _cv_lease(self, ident) -> dict:
        lease = self.lease
        if not lease or lease["kind"] != "cv" or lease["id"] != ident:
            ended = self.last_lease if self.last_lease and self.last_lease["id"] == ident else None
            raise Refused(f"lease ended: {ended['reason']}" if ended else "no such CV lease")
        return lease

    def cv_frame(self, body: dict) -> dict:
        with self.lock:
            lease = self._cv_lease(body.get("lease_id"))
            targets = body.get("targets") or {}
            grippers = body.get("grippers") or {}
            if targets:
                state, _ = self.world.snapshot()
                for side, target in targets.items():
                    if side not in SIDES:
                        self._end(f"unknown arm {side!r}")
                        raise Refused(f"unknown arm {side!r}")
                    if len(target) != 6:
                        self._end("a target needs 6 joints")
                        raise Refused("a target needs 6 joints")
                    lead = np.abs(np.asarray(target, float) - np.asarray(state[side]["positions_rad"]))
                    if lead.max() > MAX_LEAD_RAD:
                        j = int(lead.argmax())
                        why = (f"{side} joint{j + 1} target leads the measured joint by {lead[j]:.3f} rad "
                               f"(max {MAX_LEAD_RAD})")
                        self._end(why)
                        raise Refused(why)
                self.world.command(targets, {s: g for s, g in grippers.items() if s in SIDES})
            lease["_last"] = time.monotonic()
            return {"ok": True, "lease": self._public(lease)}

    def cv_stop(self, body: dict) -> dict:
        with self.lock:
            ident = body.get("lease_id")
            if self.lease and self.lease["kind"] == "cv" and (ident is None or self.lease["id"] == ident):
                return {"ok": True, "lease": self._public(self._end("stopped"))}
            return {"ok": True, "lease": None}

    def stop(self, body: dict) -> dict:
        with self.lock:
            ident = body.get("lease_id")
            if self.lease and (ident is None or self.lease["id"] == ident):
                return {"ok": True, "lease": self._public(self._end("operator_stop"))}
            return {"ok": True, "lease": self._public(self.last_lease)}

    def heartbeat(self, body: dict) -> dict:
        with self.lock:
            ident = body.get("lease_id")
            if self.lease and self.lease["id"] == ident:
                self.lease["_last"] = time.monotonic()
                return {"lease": self._public(self.lease)}
            if self.last_lease and self.last_lease["id"] == ident:
                return {"lease": self._public(self.last_lease)}
            raise Refused("no such lease")

    def action(self, body: dict) -> dict:
        raise Refused("Dream-1 action is not supported in sim (manifest_sim): use the Mac-side Dream-1 node")

    def home(self, body: dict) -> dict:
        """Manifest's native home, slowly: both arms to joint zero (the rest pose), grippers open. Blocks."""
        with self.lock:
            if self.lease:
                if self.lease["kind"] == "home":
                    raise Refused("already homing")
                self._end("home")
            ident = uuid.uuid4().hex
            lease = self.lease = {"id": ident, "kind": "home", "active": True, "reason": None, "started_at": time.time()}
            self.stop_home.clear()
        state, _ = self.world.snapshot()
        start = {s: np.asarray(state[s]["commanded_rad"], float) for s in SIDES}
        span = max(float(np.abs(start[s]).max()) for s in SIDES)
        duration = max(span / HOME_SPEED_RAD_S, 0.5)
        t0 = time.monotonic()
        self.world.command(grippers={s: 1.0 for s in SIDES})
        while not self.stop_home.is_set():
            a = min((time.monotonic() - t0) / duration, 1.0)
            self.world.command({s: (1 - a) * start[s] for s in SIDES})
            if a >= 1.0:
                break
            time.sleep(1 / 30)
        deadline = time.monotonic() + 5.0
        err = 1e9
        while not self.stop_home.is_set() and time.monotonic() < deadline:
            state, _ = self.world.snapshot()
            err = max(float(np.abs(state[s]["positions_rad"]).max()) for s in SIDES)
            if err < HOME_TOL_RAD:
                break
            time.sleep(0.05)
        with self.lock:
            if lease["active"]:
                self._end("home_reached" if err < HOME_TOL_RAD else "home_timeout")
            lease.update(reached_home=err < HOME_TOL_RAD, max_joint_error_rad=round(err, 4))
        return {"ok": True, "lease": self._public(lease)}

    # ---- observation -----------------------------------------------------------------------------------------

    def observe(self, images: bool) -> dict:
        state, imgs = self.world.snapshot()
        with self.lock:
            self.obs += 1
            lease = self._public(self.lease)
            mode = self.lease["kind"] if self.lease else "idle"
        out = {
            "observation_id": f"sim-{self.obs}",
            "status": {"state": "running" if lease else "idle", "arms": {s: s in state for s in SIDES}},
            "measured": state,
            "enabled_arms": list(SIDES),
            "lease": lease,
            "problem": None,
            "mode": mode,
        }
        if images:
            now = time.monotonic()
            out["images"] = [{"camera": i["camera"], "jpeg": i["jpeg"], "age_s": round(now - i["at"], 3)} for i in imgs]
        return out

    def robot(self) -> dict:
        state, _ = self.world.snapshot()
        with self.lock:
            st = "running" if self.lease else "idle"
        return {"station": {"state": st, "sim": True, "arms_enabled": list(SIDES)},
                "arms": {s: {"ok": True, "joints_rad": state[s]["positions_rad"], "gripper": state[s]["gripper"],
                             "velocities_rad_s": state[s]["velocities_rad_s"],
                             "motor_temps_c": state[s]["motor_temps_c"]} for s in SIDES}}


def make_handler(station: Station):
    post_routes = {
        "/supervisor/observe": lambda b: station.observe(True),
        "/supervisor/preview": lambda b: station.observe(False),
        "/supervisor/cv/start": station.cv_start,
        "/supervisor/cv/frame": station.cv_frame,
        "/supervisor/cv/stop": station.cv_stop,
        "/supervisor/stop": station.stop,
        "/supervisor/heartbeat": station.heartbeat,
        "/supervisor/action": station.action,
        "/supervisor/home": station.home,
        "/v1/cv/start": station.cv_start,
        "/v1/cv/frame": station.cv_frame,
        "/v1/cv/stop": station.cv_stop,
    }
    get_routes = {
        "/v1/robot": station.robot,
        "/v1/health": lambda: {"ok": True, "sim": True},
        "/v1/plugins": lambda: {"plugins": []},
    }

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:  # quiet: the bridge polls at 30 Hz
            pass

        def _send(self, code: int, payload: dict) -> None:
            data = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _dispatch(self, fn, *args) -> None:
            try:
                self._send(200, fn(*args))
            except Refused as exc:
                self._send(409, {"error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            if path in get_routes:
                self._dispatch(get_routes[path])
            else:
                self._send(404, {"error": f"no route {path}"})

        def do_POST(self) -> None:
            path = self.path.split("?")[0]
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                return self._send(400, {"error": "body is not JSON"})
            if path in post_routes:
                self._dispatch(post_routes[path], body if isinstance(body, dict) else {})
            elif path in get_routes:
                self._dispatch(get_routes[path])
            else:
                self._send(404, {"error": f"no route {path}"})

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8191)
    ap.add_argument("--host", default="127.0.0.1")
    view = ap.add_mutually_exclusive_group()
    view.add_argument("--headless", action="store_true", help="no viewer window (the default)")
    view.add_argument("--viewer", action="store_true", help="open Genesis's interactive viewer")
    ap.add_argument("--backend", choices=("metal", "cpu"), default="metal")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    from world import World

    print(f"[sim] building the Genesis world ({args.backend}; first run compiles kernels, ~30 s) ...")
    world = World(viewer=args.viewer, backend=args.backend)
    station = Station(world)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(station))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="http", daemon=True).start()
    threading.Thread(target=station.watchdog, name="watchdog", daemon=True).start()
    print(f"[sim] manifest_sim serving on http://{args.host}:{args.port}  (Ctrl-C stops)")
    try:
        world.run()  # the main thread: Genesis and OpenGL live here
    except KeyboardInterrupt:
        print("\n[sim] stopping")
    finally:
        world.running = False
        server.shutdown()


if __name__ == "__main__":
    main()
