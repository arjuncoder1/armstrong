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
(`h` then `y` in hand-teleop), with payload "grippers_empty" because it opens both grippers, from
the operator in control or anyone while nobody is, releases control and runs Manifest's native home.
An action older than ACTION_STALE_S is never replayed: if the operator goes quiet, the arms hold.

The grab RPC (`g` or Grab in hand-teleop) is shared autonomy: the operator steers a gripper next to an
object and types a task ("pick up the blue cube"), then Dream-1 does that task verbatim through
Manifest's action, scoped to that arm (the other arm and its gripper hold). Manifest's action lasts at
most 12 s, so the bridge renews it on the same task until Dream-1 ends it, GRAB_TOTAL_S pass, or a motor
on that arm reaches HOT_C. Taking control stops it at once.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request

import cv2
import numpy as np
from livekit.portal import Action, Robot, RobotConfig

from utils.common import (CONFIG_PATH, GRAB_RPC, HOME_RPC, PARK_RPC, ROBOT_IDENTITY, HardwareThread, env_float,
                          load_env, mint_token, pace, required_env)
from utils.metal import StepLimiter, arm_fields, clamp_to_limits, gripper_max_mm

STATION = os.environ.get("MANIFEST_STATION_URL", "http://127.0.0.1:8091")
SIDES = ("left", "right")
# How far a target may lead its joint. Leading is what lifts against gravity (the station has no
# feedforward); it also bounds the push on something in the way: lift kp 150 * 0.08 = 12 N.m, under
# the RS02's 17 N.m peak. The station refuses a target past 0.12; the 0.04 left covers the age of
# the state the lead is measured against.
MAX_LAG_RAD = 0.08
ACTION_STALE_S = 0.25  # an operator action older than this is never replayed: the arms hold
IMAGE_EVERY_S = 0.2  # the station encodes its camera JPEGs at 5 fps
TRACKS = {"top": "overhead_camera", "left": "left_wrist_camera", "right": "right_wrist_camera"}
WIDTH = 640
HOME_CONFIRMED = "grippers_empty"  # the home RPC payload: Manifest's native home opens both grippers
GRAB_ROUND_S = 12.0  # one Manifest action: it allows 0.5-12 s, and each start waits 2-3 s for Dream-1's first chunk
GRAB_TOTAL_S = env_float("GRAB_TOTAL_S", 60.0)  # Dream-1's running time for one grab, across renewals
HOT_C = 55.0  # Manifest warns at this and refuses to energize an arm this hot; the run itself stops at 65


def post(route: str, body: dict | None = None, timeout: float = 3.0) -> dict:
    request = urllib.request.Request(STATION + route, json.dumps(body or {}).encode(),
                                     {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return json.load(reply)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(json.loads(exc.read() or b"{}").get("error") or f"station HTTP {exc.code}") from None


def portal_state(measured: dict, commanded: bool = False) -> dict[str, float]:
    """Both arms as Portal state, or {} unless both are read: never half a row.

    `commanded` gives the station's last targets where it reports them: an operator that takes over or lets
    go starts from those, so a held arm keeps its gravity lead and a closed gripper keeps squeezing.
    """
    if any(side not in measured for side in SIDES):
        return {}
    state = {}
    for side in SIDES:
        arm = measured[side]
        joints = (commanded and arm.get("commanded_rad")) or arm["positions_rad"]
        grip = arm.get("commanded_gripper") if commanded else None
        values = list(joints) + [float(arm["gripper"] if grip is None else grip) * gripper_max_mm()]
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


def grab_task(side: str, task: str) -> str:
    """The operator's task verbatim, as the voice agent sends Dream-1's; Manifest moves only `side`, so say so."""
    if not task:
        return f"Pick up the object between the {side} gripper's fingers with the {side} arm."
    return task if side in task.lower() else f"{task.rstrip('.')}. Use the {side} arm."


def hottest(measured: dict, side: str) -> float:
    """The hottest motor on one arm, degrees C, or 0 when the station does not report temperatures."""
    return max((t for t in measured.get(side, {}).get("motor_temps_c") or [] if t is not None), default=0.0)


class Grab:
    """One Dream-1 task on one arm: Manifest's scoped action, renewed until it ends, the cap, heat, or `stop`.

    `measured` returns the station's latest reading of both arms (the bridge loop keeps it fresh).
    """

    def __init__(self, side: str, task: str, measured=lambda: {}) -> None:
        self.side, self.task = side, grab_task(side, task)
        self.measured = measured
        self.stop = threading.Event()
        self.line = f"Dream-1 is starting on the {side} arm: {self.task}"

    def hot(self) -> float:
        temp = hottest(self.measured(), self.side)
        return temp if temp >= HOT_C else 0.0

    def run(self) -> str:
        started = time.monotonic()
        while True:
            if self.stop.is_set():
                return f"Dream-1 stopped on the {self.side} arm: an operator took control"
            if temp := self.hot():
                return f"Dream-1 stopped on the {self.side} arm: a motor is at {temp:.0f} C, let it rest"
            left = GRAB_TOTAL_S - (time.monotonic() - started)
            if left < 1.0:
                return f"Dream-1 stopped on the {self.side} arm after {GRAB_TOTAL_S:.0f} s; c takes control"
            seen = post("/supervisor/observe")
            lease = post("/supervisor/action", {"observation_id": seen["observation_id"], "arm": self.side,
                                                "gripper_mode": "active", "seconds": min(GRAB_ROUND_S, left),
                                                "instruction": self.task}, timeout=30)["lease"]
            reason = self.follow(lease, started)
            if reason == "operator_stop":
                return f"Dream-1 stopped on the {self.side} arm: an operator took control"
            if reason != "duration_complete":  # Dream-1 ended it, the station stopped it, or heat
                return f"Dream-1 ended on the {self.side} arm ({reason}); c takes control"

    def follow(self, lease: dict, started: float) -> str:
        """Heartbeats one action until it ends; returns why it ended."""
        ident = lease["id"]
        try:
            while lease.get("active"):
                stopped = self.stop.wait(0.5)
                temp = 0.0 if stopped else self.hot()
                if stopped or temp:
                    post("/supervisor/stop", {"lease_id": ident})
                    return "operator_stop" if stopped else f"a motor at {temp:.0f} C, let it rest"
                lease = post("/supervisor/heartbeat", {"lease_id": ident})["lease"]
                self.line = f"Dream-1 on the {self.side} arm, {time.monotonic() - started:.0f} s: {self.task}"
            return lease.get("reason") or "ended"
        except BaseException:
            try:
                post("/supervisor/stop", {"lease_id": ident})  # never leave Dream-1 running
            except Exception:
                pass
            raise


class Lease:
    """The station's CV lease, held while an operator has control."""

    def __init__(self) -> None:
        self.id: str | None = None

    @staticmethod
    def open() -> str:
        """Seconds the first time: the station readies its IK. The loop keeps publishing meanwhile."""
        return post("/supervisor/cv/start", timeout=120)["lease_id"]

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
    homing: asyncio.Task | None = None  # the station's home, run off the loop so video keeps flowing
    opening: asyncio.Task | None = None  # the station's cv/start, likewise
    grab_from: tuple[str, str, str] | None = None  # (caller, arm, object) of a grab the loop has not started
    grab: Grab | None = None  # the latest grab
    grabbing: asyncio.Task | None = None
    grab_line = "no grab yet"
    measured: dict = {}  # the station's latest reading of both arms, for a grab's heat check
    latest_at = 0.0

    def on_action(action: Action) -> None:
        nonlocal latest, latest_at
        latest, latest_at = {k: float(v) for k, v in action.values.items()}, time.monotonic()

    def is_homing() -> bool:
        return homing is not None and not homing.done()

    async def run_home() -> None:
        try:
            print(f"[bridge] {await asyncio.to_thread(home)}")
        except Exception as exc:
            print(f"[bridge] home failed: {exc}")

    def is_opening() -> bool:
        return opening is not None and not opening.done()

    def is_grabbing() -> bool:
        return grabbing is not None and not grabbing.done()

    async def run_grab(job: Grab) -> None:
        nonlocal grab_line
        try:
            grab_line = await asyncio.to_thread(job.run)
        except Exception as exc:
            grab_line = f"Dream-1's {job.side} grab failed: {exc}"
        print(f"[bridge] {grab_line}")

    def on_grab(data) -> str:
        nonlocal grab_from
        if data.payload == "status":
            busy = bool(grab_from) or is_grabbing()
            return json.dumps({"active": busy, "line": grab.line if busy and grab else grab_line})
        try:
            ask = json.loads(data.payload)
            side, thing = ask["arm"], str(ask.get("object", "")).strip()[:160]  # the task, verbatim
        except (ValueError, KeyError, TypeError, AttributeError):
            return 'grab payload: {"arm": "left" or "right", "object": "..."}'
        if side not in SIDES:
            return f"grab: unknown arm {side!r}"
        holder = robot.active_operator()
        if holder not in (None, data.caller_identity):
            return f"{holder} has control: only they can hand an arm to Dream-1"
        if is_grabbing() or grab_from or is_homing() or home_from:
            return "busy: a grab or home is already running"
        if (temp := hottest(measured, side)) >= HOT_C:
            return f"the {side} arm has a motor at {temp:.0f} C: let it rest under {HOT_C:.0f} C first"
        grab_from = (data.caller_identity, side, thing)
        return f"Dream-1 takes the {side} arm: {grab_task(side, thing)} (c takes it back)"

    async def open_lease(who: str) -> None:
        """Holds the lease once it opens; the loop closes it if control moved on meanwhile."""
        try:
            lease.id = await asyncio.to_thread(Lease.open)  # its own thread: the station thread keeps reading
        except Exception as exc:
            if wanted == who:
                await release(f"Manifest refused control: {exc}")
            else:
                print(f"[bridge] the lease {who} asked for did not open: {exc}")
            return
        print("[bridge] lease open: the operator drives the arms" if wanted == who else
              "[bridge] lease open, but control moved on: closing it")

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
            return f"Manifest's home opens both grippers: confirm with payload {HOME_CONFIRMED!r} (h then y in hand-teleop)"
        holder = robot.active_operator()
        if holder not in (None, data.caller_identity):
            return f"{holder} has control: only they can home the arms"
        if is_homing() or home_from:
            return "already homing"
        if is_grabbing() or grab_from:
            return "Dream-1 is grabbing: take control (c) to stop it, then home"
        home_from = data.caller_identity
        return "homing both arms through Manifest: control released, grippers opening"

    robot.register_rpc_method(PARK_RPC, lambda data: "Manifest powers these arms: park from its GUI")
    robot.register_rpc_method(HOME_RPC, on_home)
    robot.register_rpc_method(GRAB_RPC, on_grab)
    robot.on_action(on_action)
    robot.on_active_operator_changed(on_active_operator_changed)
    robot.on_operator_left(on_operator_left)

    try:
        print(f"[bridge] station {STATION}; connecting to {url} as '{ROBOT_IDENTITY}' in room '{room}' ...")
        await robot.connect(url, mint_token(ROBOT_IDENTITY, room))
        print(f"[bridge] connected; {cfg.fps} fps; c in an operator takes control through Manifest's lease")
        async for _ in pace(cfg.fps):
            if home_from and not is_opening():  # a lease still opening is closed first, below
                who, home_from = home_from, None
                print(f"[bridge] {who} asked for home: releasing control ...")
                latest, wanted = {}, None
                await robot.set_active_operator(None)  # an operator's next action would pull the arms back out
                try:
                    await station.run(lease.close)
                except Exception as exc:
                    lease.id = None
                    print(f"[bridge] closing the lease: {exc}")
                homing = asyncio.create_task(run_home())
                continue
            if grab_from and not is_opening():  # likewise: the operator's lease closes first
                who, side, thing = grab_from
                grab_from = None
                print(f"[bridge] {who} handed the {side} arm to Dream-1: {grab_task(side, thing)}")
                latest, wanted = {}, None
                await robot.set_active_operator(None)
                try:
                    await station.run(lease.close)
                except Exception as exc:
                    lease.id = None
                    print(f"[bridge] closing the lease: {exc}")
                grab = Grab(side, thing, lambda: measured)
                grabbing = asyncio.create_task(run_grab(grab))
                continue
            if wanted and lease.id is None and is_homing():
                await release("the arms are homing: wait for it to finish")
                continue
            if wanted and is_grabbing():  # taking control is the override: Dream-1 stops, then the lease opens
                if not grab.stop.is_set():
                    print(f"[bridge] {wanted} took control: stopping Dream-1's grab")
                    grab.stop.set()
            elif wanted and lease.id is None:
                if not is_opening():
                    print(f"[bridge] {wanted} has control: opening Manifest's lease ...")
                    opening = asyncio.create_task(open_lease(wanted))
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
            measured = obs.get("measured", {})
            state = portal_state(measured)  # measured: what the step limiter leads from
            problem = obs.get("problem") or ("" if state else "an arm is not reporting")
            if problem != last_problem:
                last_problem = problem
                print(f"[bridge] station: {problem or 'both arms reporting'}")
            if images:
                next_image = time.monotonic() + IMAGE_EVERY_S
                frames.update(decode(obs.get("images", [])))
            if state:  # never invent a state; keep the video
                limiter.present.update(state)
                robot.send_state(portal_state(obs["measured"], commanded=True), timestamp_us=ts_us)
            for name, frame in frames.items():
                robot.send_video_frame(name, frame, timestamp_us=ts_us)

            if lease.id:
                fresh = latest and time.monotonic() - latest_at < ACTION_STALE_S
                try:
                    if fresh and state:
                        await station.run(lease.send, *station_command(clamp_to_limits(limiter.step(latest))))
                    else:
                        await station.run(lease.send, {}, {})  # keeps the lease: no target, nothing written
                except Exception as exc:
                    await release(f"Manifest stopped the arms: {exc}")  # close() still sends the stop
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[bridge] stopping ...")
    finally:
        if is_opening():  # a lease that opens after this would be left for the station's watchdog
            await asyncio.wait({opening}, timeout=15)
        if is_grabbing():  # Dream-1 stops with the bridge (its watchdog would stop it 3 s later anyway)
            grab.stop.set()
            await asyncio.wait({grabbing}, timeout=10)
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
