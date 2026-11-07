"""Reads every MakerArm motor's driver temperature with the station down; prints one line.

Each read is the station's own handshake (a stop/clear-fault state query per motor): no torque.
Exits 3 without touching the bus if the station or a setup station is running. While the commissioning
station runs, read `motor_temps_c` from its /supervisor/preview instead.

Run on the Halo from Manifest's halo/dreamapi folder with its venv: ../../.venv/bin/python motor_temps.py
"""
import subprocess
import sys
import time

from robots import config, errors, makers, robstride

busy = subprocess.run(["systemctl", "--user", "is-active", "-q", "manifest-makerarm"]).returncode == 0
busy |= subprocess.run(["pgrep", "-f", "makerarm_setup_station|makerarm_control"], capture_output=True).returncode == 0
if busy:
    print(time.strftime("%H:%M:%S"), "station running: not probing")
    sys.exit(3)
cfg = config.load("makerarm-station.yaml")
hot, parts = [], []
for side, arm_cfg in (("left", cfg.follower_l), ("right", cfg.follower_r)):
    bus = makers.ARM.chain(side, arm_cfg, opener=robstride.open_can_bus, clock=time.monotonic, sleep=time.sleep).bus
    try:
        bus.open()
        temps = {name: bus.query_state(name).temp_c for name in bus.motors}
        parts.append(f"{side}: " + " ".join(f"{n.split('_')[-1]}={t:.0f}" for n, t in temps.items()))
        hot += [f"{side} {n} {t:.0f}C" for n, t in temps.items() if t >= makers.ARM.temp_warn_c]
    except errors.ArmError as exc:
        parts.append(f"{side}: {exc}")
        hot.append(f"{side} unreadable")
    finally:
        bus.close(disable_torque=False)
print(time.strftime("%H:%M:%S"), " | ".join(parts), "| HOT:", ", ".join(hot) or "none")
sys.exit(1 if hot else 0)
