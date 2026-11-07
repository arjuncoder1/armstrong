"""Waits until every MakerArm motor reads at or below COOL_C on the commissioning station, then starts the powered one.

Reads temperatures from the commissioning station's preview only, so it never touches the CAN bus. The powered
station refuses to energize at 55 C or more; COOL_C leaves 2 C so a reading that ticks up does not trip it.
If the powered station fails to start, the commissioning station is started again so the feed stays up.

Run on the Halo while manifest-makerarm-setup serves the preview: python3 -u start_when_cool.py
"""
import json
import subprocess
import time
import urllib.request

COOL_C = 53.0
PREVIEW = "http://127.0.0.1:8091/supervisor/preview"


def active(unit: str) -> bool:
    return subprocess.run(["systemctl", "--user", "is-active", "-q", unit]).returncode == 0


def temps() -> dict:
    request = urllib.request.Request(PREVIEW, b"{}", {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=4) as reply:
        measured = json.load(reply)["measured"]
    return {side: measured[side]["motor_temps_c"] for side in ("left", "right")}


last_print = 0.0
for _ in range(240):  # 40 min at 10 s
    if active("manifest-makerarm"):
        print(time.strftime("%H:%M:%S"), "powered station already running")
        raise SystemExit(0)
    try:
        now = temps()
    except Exception as exc:
        print(time.strftime("%H:%M:%S"), "preview unreadable:", exc, flush=True)
        time.sleep(10)
        continue
    hottest = max(max(values) for values in now.values())
    if time.monotonic() - last_print > 60:
        print(time.strftime("%H:%M:%S"), f"hottest {hottest:.0f} C", now, flush=True)
        last_print = time.monotonic()
    if hottest <= COOL_C:
        print(time.strftime("%H:%M:%S"), f"all motors at or below {COOL_C:.0f} C: starting the powered station", now)
        subprocess.run(["systemctl", "--user", "stop", "manifest-makerarm-setup"])
        subprocess.run(["systemctl", "--user", "start", "manifest-makerarm"])
        for _ in range(30):
            time.sleep(1)
            try:
                with urllib.request.urlopen("http://127.0.0.1:8091/status", timeout=2):
                    break
            except Exception:
                if not active("manifest-makerarm"):
                    break
        time.sleep(2)
        if active("manifest-makerarm"):
            print(time.strftime("%H:%M:%S"), "powered station is up")
            raise SystemExit(0)
        print(time.strftime("%H:%M:%S"), "powered station failed; restarting the commissioning feed")
        print(subprocess.run(["journalctl", "--user", "-u", "manifest-makerarm", "--since", "-1 min", "--no-pager",
                              "-o", "cat"], capture_output=True, text=True).stdout[-1500:])
        subprocess.run(["systemctl", "--user", "start", "manifest-makerarm-setup"])
        raise SystemExit(1)
    time.sleep(10)
print(time.strftime("%H:%M:%S"), "gave up after 40 min")
raise SystemExit(2)
