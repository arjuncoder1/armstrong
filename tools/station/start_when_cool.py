"""Wait for complete, cool commissioning feedback, then start the powered station.

Run explicitly on the Halo: python3 -u tools/station/start_when_cool.py
No CAN access, temperature overrides, homing, or operator control requests.
"""
import json
import math
import subprocess
import time
import urllib.request

COOL_C = 53.0  # two degrees below the native startup threshold
PREVIEW = "http://127.0.0.1:8091/supervisor/preview"


def active(unit: str) -> bool:
    return subprocess.run(["systemctl", "--user", "is-active", "-q", unit]).returncode == 0


def service(action, unit):
    subprocess.run(["systemctl", "--user", action, unit], check=True)


def observe():
    request = urllib.request.Request(PREVIEW, b"{}", {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=4) as reply:
        return json.load(reply)


def temperatures(observation):
    status = observation.get("status", {})
    if status.get("state") != "commissioning":
        raise ValueError("Expected commissioning feedback")
    result = {}
    for side in ("left", "right"):
        if status.get("arms", {}).get(side) is not True:
            raise ValueError(f"{side}: fresh feedback unavailable")
        values = observation.get("measured", {}).get(side, {}).get("motor_temps_c", [])
        if len(values) != 7 or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in values
        ):
            raise ValueError(f"{side}: seven finite motor temperatures required")
        result[side] = values
    return result


def powered_ready(observation):
    status = observation.get("status", {})
    return (status.get("state") == "idle"
            and status.get("control_adapter") == "manifest-makerarm-v1"
            and all(status.get("arms", {}).get(s) is True for s in ("left", "right"))
            and not status.get("last_error")
            and not observation.get("motion_problem"))


def start_powered():
    try:
        service("stop", "manifest-makerarm-setup")
        service("start", "manifest-makerarm")
        for _ in range(30):
            time.sleep(1)
            if not active("manifest-makerarm"):
                break
            try:
                if powered_ready(observe()):
                    print("Powered station ready; both arms connected.", flush=True)
                    return 0
            except Exception:
                pass
        raise RuntimeError("Powered station did not become ready")
    except Exception as exc:
        print(f"Startup failed: {exc}; restoring commissioning preview", flush=True)
        print(subprocess.run(
            ["journalctl", "--user", "-u", "manifest-makerarm", "--since", "-1 min", "--no-pager", "-o", "cat"],
            capture_output=True, text=True,
        ).stdout[-1500:])
        # Stop completely before another process opens the same devices.
        service("stop", "manifest-makerarm")
        service("start", "manifest-makerarm-setup")
        return 1


def main():
    last_print = 0.0
    for _ in range(240):
        if active("manifest-makerarm"):
            try:
                ready = powered_ready(observe())
            except Exception:
                ready = False
            print("Powered station already running" + (" and ready" if ready else "; readiness not confirmed"))
            return 0 if ready else 1
        try:
            now = temperatures(observe())
        except Exception as exc:
            print(time.strftime("%H:%M:%S"), "preview unreadable:", exc, flush=True)
            time.sleep(10)
            continue
        hottest = max(max(values) for values in now.values())
        if time.monotonic() - last_print > 60:
            print(time.strftime("%H:%M:%S"), f"hottest {hottest:.0f} C", now, flush=True)
            last_print = time.monotonic()
        if hottest <= COOL_C:
            print(f"All 14 motors at or below {COOL_C:g} C; starting powered station", flush=True)
            return start_powered()
        time.sleep(10)
    print("Gave up after 40 min; commissioning remains available")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
