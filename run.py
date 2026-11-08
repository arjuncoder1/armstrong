"""Deploy Dream-1 on the two Maker Arms plugged into this Mac, with Dream's own SDK (robots.station).

    uv run run.py "pick up the card"            # run Dream-1 on that prompt; Ctrl-C to stop
    uv run run.py "pick up the card" --steps 600
    uv run run.py --check                       # open arms + cameras, print status, no motion, then exit

What it does:
  - writes station.mac.yaml (Maker Arm, gs_usb CAN adapters, OpenCV cameras, dream-1-beta, safe speed limits),
  - patches Dream's driver in memory so it opens the macOS candleLight adapters (tools/dreamcli-mac.py),
  - StationController.from_config(...) opens both arms (energized, holding where they rest) and the cameras,
  - start(prompt) runs Dream-1; the station's own limits (EE speed, ramp, stale frames, stalls) apply.
On exit (Ctrl-C or end): stop (arms hold) -> home (walk to the rest pose, grippers open) -> switch off.
The arms have no brakes: start with them resting on their supports, hands clear while it runs.
Dream credentials: your dreamcli login (~/.dreamlabs/credentials). Close MakerMods Lab and dreamcli setup first.
"""

import argparse
import asyncio
import importlib.util
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "station.mac.yaml"

# Set ARM_LEFT_CAN / ARM_RIGHT_CAN for your adapters; adjust camera numbers as needed (uv run main.py robot --list-adapters).
LEFT_CAN = os.environ.get("ARM_LEFT_CAN", "gs_usb:LEFT_ADAPTER_ID")
RIGHT_CAN = os.environ.get("ARM_RIGHT_CAN", "gs_usb:RIGHT_ADAPTER_ID")
CAM_SCENE, CAM_LEFT, CAM_RIGHT = (int(os.environ.get(k, d)) for k, d in
                                  (("CAM_SCENE", "1"), ("CAM_WRIST_L", "0"), ("CAM_WRIST_R", "2")))

STATION_YAML = f"""\
body: makers
checkpoint: dreamlabs/dream-1-beta
action_space: eef
action_horizon: 48
control_hz: 60
policy_image_size: 640x480
max_ee_speed_m_s: 0.15
ramp_max_rad_s: 0.3
stale_after_s: 0.2
max_stall_ticks: 240
face_blur: false
follower_l:
  can_channel: {LEFT_CAN}
follower_r:
  can_channel: {RIGHT_CAN}
cameras:
- {{name: scene, device: {CAM_SCENE}, width: 1280, height: 720, fps: 15}}
- {{name: wrist_l, device: {CAM_LEFT}, width: 640, height: 480, fps: 15}}
- {{name: wrist_r, device: {CAM_RIGHT}, width: 640, height: 480, fps: 15}}
rollouts:
  enabled: false
"""


VIRTUAL = "virtual"  # can_channel of a stand-in arm (--virtual): no hardware, follows its commands


class VirtualArm:
    """A stand-in for a dead or missing arm: always answers, sits at the rest pose, follows commands instantly.

    Dream's station needs both arms; this lets the real one run alone. Nothing physical moves on this side."""

    def __init__(self, side: str) -> None:
        import numpy as np

        self.side, self._np = side, np
        self.q, self.grip = np.zeros(6), 1.0

    def read(self):
        from robots.types import ArmState

        return ArmState(positions_rad=self.q.copy(), velocities_rad_s=self._np.zeros(6), gripper=self.grip,
                        commanded_rad=self.q.copy(), commanded_gripper=self.grip, gripper_effort=0.0,
                        motor_temps_c=(30.0,) * 7)

    def write(self, command) -> None:
        self.q = self._np.asarray(command.positions_rad, dtype=float).copy()
        self.grip = float(command.gripper)

    def hold(self) -> None: ...
    def is_alive(self) -> bool: return True
    def holds_dead(self) -> bool: return False
    def alarm(self): return None
    def why_stopped(self) -> str: return ""
    def disengage(self) -> None: ...
    def torque_off(self) -> None: ...
    def close(self) -> None: ...
    def close_for_reopen(self) -> None: ...
    drops_when_limp = False


def patch_driver() -> None:
    """Load tools/dreamcli-mac.py (gs_usb on macOS) and let can_channel 'virtual' open a VirtualArm."""
    import dataclasses

    spec = importlib.util.spec_from_file_location("dreamcli_mac", ROOT / "tools" / "dreamcli-mac.py")
    spec.loader.exec_module(importlib.util.module_from_spec(spec))

    from robots import bodies

    real = bodies.MAKERS.open_arm

    def open_arm(arm_cfg, side, *args, **kwargs):
        if getattr(arm_cfg, "can_channel", "") == VIRTUAL:
            print(f"{side} arm: VIRTUAL stand-in (no hardware)")
            return VirtualArm(side)
        return real(arm_cfg, side, *args, **kwargs)

    patched = dataclasses.replace(bodies.MAKERS, open_arm=open_arm)
    bodies.MAKERS = patched
    for key, body in list(bodies.BODIES.items()):
        if body is not patched and getattr(body, "name", None) == "makers":
            bodies.BODIES[key] = patched


def summary(status: dict) -> str:
    keys = ("state", "prompt", "run", "steps", "chunks", "clamps", "stalls", "last_error")
    return " | ".join(f"{k}={status.get(k)}" for k in keys if status.get(k) not in (None, "", [], {}))


async def main(args: argparse.Namespace) -> None:
    from robots import config
    from robots.station import StationController

    for side, channel in (("left", LEFT_CAN), ("right", RIGHT_CAN)):
        if args.virtual != side and channel.endswith("_ADAPTER_ID"):
            raise SystemExit(f"Set ARM_{side.upper()}_CAN to the adapter channel (use --list-adapters to discover it).")
    yaml = STATION_YAML
    if args.virtual == "left":
        yaml = yaml.replace(f"can_channel: {LEFT_CAN}", f"can_channel: {VIRTUAL}")
    elif args.virtual == "right":
        yaml = yaml.replace(f"can_channel: {RIGHT_CAN}", f"can_channel: {VIRTUAL}")
    CONFIG.write_text(yaml)
    cfg = config.load(CONFIG)
    print(f"opening both arms and cameras ({CONFIG.name}) ...")
    ctl = StationController.from_config(cfg, inference_log_path=str(ROOT / "dream-inference.log"))
    try:
        print("ready:", summary(ctl.status()))
        if args.check:
            await asyncio.sleep(2)
            print("check:", summary(ctl.status()))
            return
        print(f'Dream-1: "{args.prompt}"  (Ctrl-C to stop)')
        print("start:", summary(await ctl.start(args.prompt, steps=args.steps)))
        last = ""
        while True:
            await asyncio.sleep(1)
            st = ctl.status()
            line = summary(st)
            if line != last:
                print(time.strftime("%H:%M:%S"), line)
                last = line
            if st.get("state") in ("idle", "error"):
                break
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nstopping ...")
    finally:
        try:
            print("stop:", summary(await ctl.stop()))
            if not args.check and not args.no_home:
                print("homing to the rest pose (grippers open) ...")
                print("home:", summary(await ctl.home()))
        finally:
            await ctl.close()  # cameras released, arms switched off (now at rest)
            print("closed: arms off")


def run() -> None:
    p = argparse.ArgumentParser(description="Deploy Dream-1 on the Maker Arms with Dream's SDK (macOS, gs_usb).")
    p.add_argument("prompt", nargs="?", default="pick up the card")
    p.add_argument("--steps", type=int, help="stop after this many control steps")
    p.add_argument("--check", action="store_true", help="open arms and cameras, print status, no motion")
    p.add_argument("--no-home", action="store_true", help="don't home before switching off (arms drop: support them)")
    p.add_argument("--virtual", choices=("left", "right"),
                   help="replace that arm with a stand-in (it's dead or unplugged); the other arm runs for real")
    args = p.parse_args()
    patch_driver()
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
