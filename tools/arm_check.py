"""Check the Maker Arms on this Mac's USB-CAN adapters: do all 7 motors of each arm answer? (no torque)

    uv run tools/arm_check.py                    # answer check + motor temperatures, energizes nothing
    uv run tools/arm_check.py --watch            # repeat every 2 s until Ctrl-C (for fixing power/cables)
    uv run tools/arm_check.py --disable-torque   # also switch every motor off (arms go LIMP: support them)
    uv run tools/arm_check.py --list             # list the gs_usb adapters only

Adapters come from ARM_LEFT_CAN / ARM_RIGHT_CAN (required for connected arms). Close dreamcli, run.py, MakerMods
Lab and main.py robot first: only one program can hold an adapter.
"""

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "thirdparty" / "portal-makermods" / "src"))

ARMS = (("left", os.environ.get("ARM_LEFT_CAN", "gs_usb:LEFT_ADAPTER_ID")),
        ("right", os.environ.get("ARM_RIGHT_CAN", "gs_usb:RIGHT_ADAPTER_ID")))
WARN_C = 55


def motors():
    import robots.makers as mk
    import robots.robstride as rs

    return ([rs.Motor(name=j.name, can_id=j.motor_id, model=j.model, kp=j.kp, kd=j.kd) for j in mk.JOINTS]
            + [rs.Motor("gripper", 7, "O0", 20.0, 0.5)])


def check(side: str, channel: str, disable: bool) -> bool:
    import robots.robstride as rs
    from utils.gs_usb_transport import open_gs_usb

    bus = rs.RobstrideBus(channel, motors(), opener=open_gs_usb, clock=time.monotonic, sleep=time.sleep)
    try:
        bus.open()  # handshake: one state query per motor; energizes nothing
        temps = {name: round(bus.query_state(name).temp_c) for name in bus.motors}
        hot = [f"{n} {t}C" for n, t in temps.items() if t >= WARN_C]
        line = " ".join(f"{n}={t}" for n, t in temps.items())
        if disable:
            bus.disable_torque()
            line += " | torque OFF"
        print(f"OK    {side:5} {channel}: all 7 answer | {line}" + (f" | HOT: {', '.join(hot)}" if hot else ""))
        return True
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "did not answer" in msg:
            msg = "no motor answers: arm power off / e-stop pressed / CAN cable loose (adapter itself is on USB)"
        elif "Expected exactly one" in msg or "found 0" in msg:
            msg = "adapter not found on USB: check its USB cable, or another program holds it"
        print(f"FAIL  {side:5} {channel}: {msg[:160]}")
        return False
    finally:
        try:
            bus.close(disable_torque=False)
        except Exception:  # noqa: BLE001
            pass


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--watch", action="store_true", help="repeat every 2 s until Ctrl-C")
    p.add_argument("--disable-torque", action="store_true", help="switch every motor off (arms go limp)")
    p.add_argument("--list", action="store_true", help="list gs_usb adapters only")
    args = p.parse_args()

    from utils.gs_usb_transport import available_gs_usb_ports

    print("adapters on USB:", ", ".join(available_gs_usb_ports()) or "none")
    if args.list:
        return
    for side, channel in ARMS:
        if channel.endswith("_ADAPTER_ID"):
            p.error(f"Set ARM_{side.upper()}_CAN to an adapter channel listed above.")
    try:
        while True:
            ok = [check(side, ch, args.disable_torque) for side, ch in ARMS]
            if not args.watch:
                sys.exit(0 if all(ok) else 1)
            print(time.strftime("%H:%M:%S"), "-" * 40)
            time.sleep(2)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
