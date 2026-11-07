"""No-hardware test of manifest_bridge: a fake Manifest station plus a scripted Portal operator.

The fake station tracks each written target perfectly and applies the real station's lead check (0.12 rad).
The operator waits for an observation, takes control, asks for a 0.3 rad jump on right joint2 and an open
gripper, then releases. Run from ~/portal-makermods with PYTHONPATH=src, after starting the bridge with
MANIFEST_STATION_URL=http://127.0.0.1:18091 in the same LIVEKIT_ROOM.
"""
import asyncio
import base64
import json
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

Q = {"left": np.array([-0.054, -0.058, 0.024, -0.027, 0.111, 0.019]),
     "right": np.array([-0.085, -0.057, 0.032, -0.022, -0.009, -0.077])}
GRIP = {"left": 0.5, "right": 0.5}
LOG = {"starts": 0, "stops": 0, "heartbeats": 0, "writes": [], "refused": [], "homes": [],
       "actions": [], "action_beats": 0, "action_stops": 0}
ACTION = {"id": None, "active": False, "ends": 0.0, "reason": None}
ACTION_S = [10.0]  # how long the fake Dream-1 action runs before it completes
LEASE = {"id": None}
CV_START_S = 4.5  # the real station readies its IK this long before cv/start answers
JPEG = base64.b64encode(cv2.imencode(".jpg", np.full((480, 640, 3), 90, np.uint8))[1]).decode()


class Station(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        measured = {s: {"positions_rad": Q[s].tolist(), "gripper": GRIP[s]} for s in Q}
        if self.path in ("/supervisor/preview", "/supervisor/observe"):
            images = [{"camera": c, "jpeg": JPEG, "age_s": 0.05} for c in ("top", "left", "right")]
            return self.reply(200, {"observation_id": "obs-1", "measured": measured, "problem": None,
                                    "images": images if self.path.endswith("observe") else []})
        if self.path == "/supervisor/home":
            LOG["homes"].append((body, LEASE["id"]))
            return self.reply(200, {"lease": {"reached_home": True, "reason": "home_reached"}})
        if self.path == "/supervisor/action":
            if ACTION["active"] or LEASE["id"]:
                return self.reply(409, {"error": "An action is already running"})
            LOG["actions"].append(body)
            ACTION.update(id=uuid.uuid4().hex, active=True, ends=time.monotonic() + ACTION_S[0], reason=None)
            return self.reply(200, {"status": {}, "lease": dict(ACTION)})
        if self.path == "/supervisor/heartbeat":
            if body.get("lease_id") != ACTION["id"]:
                return self.reply(409, {"error": "Unknown action lease"})
            LOG["action_beats"] += 1
            if ACTION["active"] and time.monotonic() > ACTION["ends"]:
                ACTION.update(active=False, reason="duration_complete")
            return self.reply(200, {"status": {}, "lease": dict(ACTION)})
        if self.path == "/supervisor/stop":
            if body.get("lease_id") == ACTION["id"] and ACTION["active"]:
                LOG["action_stops"] += 1
                ACTION.update(active=False, reason="operator_stop")
            return self.reply(200, {"status": {}, "lease": dict(ACTION)})
        if self.path == "/supervisor/cv/start":
            if ACTION["active"]:
                return self.reply(409, {"error": "Stop the current task or teaching session before CV teleop"})
            time.sleep(CV_START_S)
            LEASE["id"] = uuid.uuid4().hex
            LOG["starts"] += 1
            return self.reply(200, {"lease_id": LEASE["id"], "status": "CV ready"})
        if self.path == "/supervisor/cv/stop":
            LOG["stops"] += LEASE["id"] == body.get("lease_id")
            LEASE["id"] = None
            return self.reply(200, {"status": "CV stopped"})
        if self.path == "/supervisor/cv/frame":
            if body.get("lease_id") != LEASE["id"] or LEASE["id"] is None:
                return self.reply(409, {"error": "CV session expired; enable CV control again"})
            if not body["targets"]:
                LOG["heartbeats"] += 1
                return self.reply(200, {"status": "Following: none"})
            for side, q in body["targets"].items():
                lead = float(np.max(np.abs(np.array(q) - Q[side])))
                if lead > 0.12:
                    LOG["refused"].append((side, lead))
                    LEASE["id"] = None
                    return self.reply(409, {"error": f"{side} target {lead:.2f} rad ahead of the arm"})
            LOG["writes"].append({s: (np.array(q) - Q[s]) for s, q in body["targets"].items()})
            for side, q in body["targets"].items():
                Q[side] = np.array(q)  # perfect tracking
                GRIP[side] = body["grippers"][side]
            return self.reply(200, {"status": "Following"})
        self.reply(404, {"error": "no route"})


async def operator(room: str) -> None:
    from livekit.portal import Operator, OperatorConfig

    from utils.common import CONFIG_PATH, load_env, mint_token, required_env
    from utils.metal import arm_fields

    load_env()
    op = Operator(OperatorConfig.from_yaml_file(CONFIG_PATH, room))
    latest = {}
    seen = [0]

    def on_obs(obs):
        latest.update(obs=obs, at=time.monotonic())
        seen[0] += 1
    op.on_observation(on_obs)
    await op.connect(required_env("LIVEKIT_URL"), mint_token("hand-teleop", room))
    for _ in range(100):
        if "obs" in latest:
            break
        await asyncio.sleep(0.1)
    obs = latest.get("obs")
    print("observation:", None if obs is None else
          f"{len(obs.state)} state values, frames {sorted(obs.frames)}, right_joint2 {obs.state['right_joint2.pos']:.3f}")
    if obs is None:
        return
    await op.set_active_operator(op.local_identity())
    before = seen[0]
    await asyncio.sleep(CV_START_S - 0.5)  # the lease is still opening
    print(f"observations while the lease opened: {seen[0] - before} in {CV_START_S - 0.5:.1f} s (the old bridge sent none)")
    await asyncio.sleep(1.5)
    print("lease opened:", LOG["starts"] == 1, "| heartbeats while idle:", LOG["heartbeats"])
    start = dict(obs.state)
    goal = dict(start)
    goal["right_joint2.pos"] = start["right_joint2.pos"] - 0.3
    goal["right_gripper.pos"] = 80.0
    for _ in range(45):  # 1.5 s at 30 fps, the goal held 0.3 rad away
        op.send_action(goal, in_reply_to_ts_us=latest["obs"].timestamp_us)
        await asyncio.sleep(1 / 30)
    await asyncio.sleep(0.3)
    quiet_from = len(LOG["writes"])
    await asyncio.sleep(0.6)  # the operator sends nothing: the bridge must not replay its last action
    print("writes while the operator was quiet (0.3-0.9 s after its last action):", len(LOG["writes"]) - quiet_from)
    steps = [abs(w["right"][1]) for w in LOG["writes"] if "right" in w]
    print(f"writes {len(LOG['writes'])}, largest step {max(steps):.3f} rad, refused {LOG['refused']}, "
          f"right_joint2 moved {Q['right'][1] - start['right_joint2.pos']:+.3f} rad (asked -0.300), "
          f"right gripper {GRIP['right']:.2f}, left moved {np.max(np.abs(Q['left'] - [start[n] for n in arm_fields('left')[:6]])):.3f}")
    await op.set_active_operator(None)
    await asyncio.sleep(0.8)
    print("released: lease stopped", LOG["stops"] == 1, "| lease now", LEASE["id"])
    await op.set_active_operator(op.local_identity())
    await asyncio.sleep(1.0)
    await op.set_active_operator(None)  # released while the lease is still opening
    await asyncio.sleep(CV_START_S + 0.5)
    print("released mid-open: opened", LOG["starts"] == 2, "and closed", LOG["stops"] == 2, "| lease now", LEASE["id"])
    print("home, unconfirmed:", await op.perform_rpc("home", payload="", destination="robot"))
    await op.set_active_operator(op.local_identity())
    await asyncio.sleep(1.5)  # asked while the lease is still opening
    print("home, confirmed, while in control:", await op.perform_rpc("home", payload="grippers_empty", destination="robot"))
    await asyncio.sleep(CV_START_S + 1.0)
    print(f"homes {len(LOG['homes'])}: body {LOG['homes'][0][0] if LOG['homes'] else None}, "
          f"station lease during home {LOG['homes'][0][1] if LOG['homes'] else '-'}, control after: {op.active_operator()}")
    # Shared autonomy: Dream-1 finishes a grasp on one arm; taking control stops it.
    grab = lambda arm, thing="": op.perform_rpc("grab", payload=json.dumps({"arm": arm, "object": thing}), destination="robot")
    status = lambda: op.perform_rpc("grab", payload="status", destination="robot")
    print("grab, bad payload:", await op.perform_rpc("grab", payload="left", destination="robot"))
    print("grab:", await grab("left", "orange cube"))
    await asyncio.sleep(2.5)
    a = LOG["actions"][0] if LOG["actions"] else {}
    print(f"action: arm {a.get('arm')}, gripper {a.get('gripper_mode')}, {a.get('seconds')} s, cv lease during it {LEASE['id']}, "
          f"heartbeats {LOG['action_beats']}, object in prompt {'orange cube' in a.get('instruction', '')}")
    print("status while grabbing:", json.loads(await status()))
    print("grab while grabbing:", await grab("right"))
    await op.set_active_operator(op.local_identity())  # the override
    await asyncio.sleep(0.8)
    print("took control: Dream-1 stopped", LOG["action_stops"] == 1, "| status", json.loads(await status())["line"])
    await asyncio.sleep(CV_START_S + 1.0)
    print("then the CV lease opened:", LEASE["id"] is not None, "| control:", op.active_operator())
    ACTION_S[0] = 1.5
    print("grab right while in control:", await grab("right"))
    await asyncio.sleep(4.0)
    st = json.loads(await status())
    print(f"natural end: active {st['active']}, line {st['line']!r}, control after: {op.active_operator()}, "
          f"cv lease {LEASE['id']}, actions {len(LOG['actions'])}")
    await op.disconnect()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 18091), Station)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if sys.argv[1:] == ["station"]:
        print("fake station on 18091")
        threading.Event().wait()
    asyncio.run(operator(sys.argv[1]))
