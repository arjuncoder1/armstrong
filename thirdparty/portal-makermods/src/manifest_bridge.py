"""Portal robot peer for arms that Manifest's station owns: LiveKit operators drive them through its lease.

Run on the Halo with Manifest's station up, in a room of its own:

    LIVEKIT_ROOM=manifest-hands uv run python src/manifest_bridge.py

It never opens CAN or a camera, so Manifest keeps the arms. Each tick it reads both arms from the
station and publishes them, with the station's camera JPEGs, as Portal state and video. When an
operator takes control (`c` in hand-teleop), it opens the station's CV lease; that operator's
actions go through Portal's own step limiter and soft-limit clamp, then to the station, which writes
them only while the lease holds and checks each target against the measured arm. Releasing control,
the operator leaving, or any station refusal ends the lease and releases control. While no operator
has control, Manifest's own tasks and teaching run as usual. Park stays Manifest's. The home RPC
(`h` twice in hand-teleop), with payload "grippers_empty" because it opens both grippers, releases
control and runs Manifest's native home.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import urllib.error
import urllib.request

import cv2
import numpy as np
from livekit.portal import Action, Robot, RobotConfig

from utils.common import (CONFIG_PATH, HOME_RPC, PARK_RPC, ROBOT_IDENTITY, HardwareThread, env_float, load_env,
                          mint_token, pace, required_env)
from utils.metal import StepLimiter, arm_fields, clamp_to_limits, gripper_max_mm

STATION = os.environ.get("MANIFEST_STATION_URL", "http://127.0.0.1:8091")
SIDES = ("left", "right")
# How far a target may lead its joint. Leading is what lifts against gravity (the station has no
# feedforward); it also bounds the push on something in the way: lift kp 150 * 0.1 = 15 N.m, under
# the RS02's 17 N.m peak. The station refuses a target past 0.12.
MAX_LAG_RAD = 0.1
IMAGE_EVERY_S = 0.2  # the station encodes its camera JPEGs at 5 fps
TRACKS = {"top": "overhead_camera", "left": "left_wrist_camera", "right": "right_wrist_camera"}
WIDTH = 640
HOME_CONFIRMED = "grippers_empty"  # the home RPC payload: Manifest's native home opens both grippers


def post(route: str, body: dict | None = None, timeout: float = 3.0) -> dict:
    request = urllib.request.Request(STATION + route, json.dumps(body or {}).encode(),
                                     {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return json.load(reply)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(json.loads(exc.read() or b"{}").get("error") or f"station HTTP {exc.code}") from None


def portal_state(measured: dict) -> dict[str, float]:
    """Both arms as Portal state, or {} unless both are read: never half a row."""
    if any(side not in measured for side in SIDES):
        return {}
    state = {}
    for side in SIDES:
        values = list(measured[side]["positions_rad"]) + [float(measured[side]["gripper"]) * gripper_max_mm()]
        state.update(zip(arm_fields(side), map(float, values)))
    return state


def decode(images: list[dict]) -> dict[str, np.ndarray]:
    frames = {}
    for image in images:
        if (name := TRACKS.get(image["camera"])) is None:
            continue
        bgr = cv2.imdecode(np.frombuffer(base64.b64decode(image["jpeg"]), np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        if bgr.shape[1] > WIDTH:
            bgr = cv2.resize(bgr, (WIDTH, round(bgr.shape[0] * WIDTH / bgr.shape[1])), interpolation=cv2.INTER_AREA)
        frames[name] = np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    return frames


def station_command(target: dict[str, float]) -> tuple[dict, dict]:
    """Portal's ramped, clamped action as the station's joint targets (rad) and grippers (0 closed to 1 open)."""
    fields = {side: arm_fields(side) for side in SIDES}
    joints = {side: [target[name] for name in fields[side][:6]] for side in SIDES}
    grippers = {side: min(max(target[fields[side][6]] / gripper_max_mm(), 0.0), 1.0) for side in SIDES}
    return joints, grippers


def home() -> str:
    """Manifest's native home: both arms to their home pose, grippers open. Blocks until it ends."""
    seen = post("/supervisor/preview")
    lease = post("/supervisor/home", {"observation_id": seen["observation_id"], "grippers_empty": True},
                 timeout=90).get("lease") or {}
    if lease.get("reached_home"):
        return "home reached; c gives an operator control"
    return f"home not reached ({lease.get('reason')}; joint error {lease.get('max_joint_error_rad')})"


class Lease:
    """The station's CV lease, held while an operator has control."""

    def __init__(self) -> None:
        self.id: str | None = None

    def open(self) -> None:
        self.id = post("/supervisor/cv/start", timeout=120)["lease_id"]

    def send(self, joints: dict, grippers: dict) -> None:
        post("/supervisor/cv/frame", {"lease_id": self.id, "targets": joints, "grippers": grippers})

    def close(self) -> None:
        ident, self.id = self.id, None
        if ident:
            post("/supervisor/cv/stop", {"lease_id": ident})


async def main() -> None:
    load_env()
    url, room = required_env("LIVEKIT_URL"), required_env("LIVEKIT_ROOM")
    cfg = RobotConfig.from_yaml_file(CONFIG_PATH, room)
    robot = Robot(cfg)
    station = HardwareThread("station")
    limiter = StepLimiter(env_float("METAL_MAX_STEP_RAD", 0.087))
    limiter.MAX_LAG = MAX_LAG_RAD
    lease = Lease()
    latest: dict[str, float] = {}
    wanted: str | None = None  # the operator that should hold the lease
    frames: dict[str, np.ndarray] = {}
    next_image = 0.0
    last_problem = ""
    home_from: str | None = None  # who asked for a home the loop has not run yet

    def on_action(action: Action) -> None:
        nonlocal latest
        latest = {k: float(v) for k, v in action.values.items()}

    def on_active_operator_changed(identity: str | None) -> None:
        nonlocal latest, wanted
        latest, wanted = {}, identity  # never replay the previous operator's last command
        print(f"[bridge] active operator now: {identity}")

    def on_operator_left(identity: str) -> None:
        if identity == robot.active_operator():
            print(f"[bridge] active operator '{identity}' left; releasing")
            asyncio.create_task(robot.set_active_operator(None))

    async def release(why: str) -> None:
        nonlocal latest, wanted
        print(f"[bridge] {why}; control released, press c to take it again")
        latest, wanted = {}, None
        try:
            await station.run(lease.close)
        except Exception:
            lease.id = None
        await robot.set_active_operator(None)

    def on_home(data) -> str:
        nonlocal home_from
        if data.payload != HOME_CONFIRMED:
            return f"Manifest's home opens both grippers: confirm with payload {HOME_CONFIRMED!r} (h twice in hand-teleop)"
        home_from = data.caller_identity
        return "homing both arms through Manifest: control released, grippers opening"

    robot.register_rpc_method(PARK_RPC, lambda data: "Manifest powers these arms: park from its GUI")
    robot.register_rpc_method(HOME_RPC, on_home)
    robot.on_action(on_action)
    robot.on_active_operator_changed(on_active_operator_changed)
    robot.on_operator_left(on_operator_left)

    try:
        print(f"[bridge] station {STATION}; connecting to {url} as '{ROBOT_IDENTITY}' in room '{room}' ...")
        await robot.connect(url, mint_token(ROBOT_IDENTITY, room))
        print(f"[bridge] connected; {cfg.fps} fps; c in an operator takes control through Manifest's lease")
        async for _ in pace(cfg.fps):
            if home_from:
                who, home_from = home_from, None
                print(f"[bridge] {who} asked for home: releasing control ...")
                latest, wanted = {}, None
                await robot.set_active_operator(None)  # an operator's next action would pull the arms back out
                try:
                    await station.run(lease.close)
                    print(f"[bridge] {await station.run(home)}")
                except Exception as exc:
                    lease.id = None
                    print(f"[bridge] home failed: {exc}")
                continue
            if wanted and lease.id is None:
                print(f"[bridge] {wanted} has control: opening Manifest's lease ...")
                try:
                    await station.run(lease.open)
                    print("[bridge] lease open: the operator drives the arms")
                except Exception as exc:
                    await release(f"Manifest refused control: {exc}")
                    continue
            elif not wanted and lease.id:
                try:
                    await station.run(lease.close)
                    print("[bridge] lease closed: arms holding, Manifest free")
                except Exception as exc:
                    lease.id = None
                    print(f"[bridge] closing the lease: {exc}")

            ts_us = robot.now_us()
            images = time.monotonic() >= next_image
            try:
                obs = await station.run(post, "/supervisor/observe" if images else "/supervisor/preview")
            except Exception as exc:
                if str(exc) != last_problem:
                    last_problem = str(exc)
                    print(f"[bridge] station unreadable: {exc}")
                if lease.id:
                    await release("station unreadable")
                continue
            state = portal_state(obs.get("measured", {}))
            problem = obs.get("problem") or ("" if state else "an arm is not reporting")
            if problem != last_problem:
                last_problem = problem
                print(f"[bridge] station: {problem or 'both arms reporting'}")
            if images:
                next_image = time.monotonic() + IMAGE_EVERY_S
                frames.update(decode(obs.get("images", [])))
            if state:  # never invent a state; keep the video
                limiter.present.update(state)
                robot.send_state(state, timestamp_us=ts_us)
            for name, frame in frames.items():
                robot.send_video_frame(name, frame, timestamp_us=ts_us)

            if lease.id:
                try:
                    if latest and state:
                        await station.run(lease.send, *station_command(clamp_to_limits(limiter.step(latest))))
                    else:
                        await station.run(lease.send, {}, {})  # keeps the lease: no target, nothing written
                except Exception as exc:
                    lease.id = None  # the station ended it
                    await release(f"Manifest stopped the arms: {exc}")
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[bridge] stopping ...")
    finally:
        try:
            await station.run(lease.close)  # the station holds the arms where they are
        except Exception as exc:
            print(f"[bridge] closing the lease: {exc}")
        try:
            await robot.disconnect()
        finally:
            robot.close()
            station.close()


if __name__ == "__main__":
    asyncio.run(main())
