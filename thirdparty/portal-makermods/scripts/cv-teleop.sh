#!/usr/bin/env bash
# Laptop-camera MediaPipe + IK teleop on the Maker Arms, with a safe hand-over from Manifest.
#   check    reads only: can the arms be handed over right now?
#   preview  camera + hand tracking; nothing is sent to the arms and Manifest keeps them
#   on       stop Manifest's controller (its motors go off), start Portal parked, start teleop
#   off      stop teleop, park, stop Portal, give the arms back to Manifest
# Portal takes no lock on the arms and SocketCAN lets two programs write one bus, so never run
# `uv run robot` by hand while manifest-makerarm is up.
# On the laptop: ssh -N -L 8081:127.0.0.1:8081 pablo@10.103.1.11, then open the printed URL.
set -euo pipefail
P=$HOME/portal-makermods
DEV=/dev/v4l/by-path/pci-0000:c4:00.4-usb-0
UNITS=(cv-teleop cv-robot)
# From Manifest's makerarm-profile.json and makerarm-station.yaml. Process env beats .env.
ROBOT_ENV=(--setenv=PYTHONUNBUFFERED=1 --setenv=MAKERMODS_MODEL=makers
  --setenv=METAL_FOLLOWER_LEFT_CAN=can1 --setenv=METAL_FOLLOWER_RIGHT_CAN=can0
  --setenv=METAL_GRIPPER_OPEN_DEG=-96 --setenv=METAL_GRIPPER_CLOSED_DEG=-2.5
  --setenv=METAL_CAM_OVERHEAD=$DEV:1.2.3:1.0-video-index0
  --setenv=METAL_CAM_LEFT_WRIST=$DEV:1.3:1.0-video-index0
  --setenv=METAL_CAM_RIGHT_WRIST=$DEV:1.4:1.0-video-index0
  --setenv=METAL_MAX_STEP_RAD=${METAL_MAX_STEP_RAD:-0.02})   # 0.02 rad/tick at 30 Hz = 0.6 rad/s
HAND_ENV=(--setenv=PYTHONUNBUFFERED=1 --setenv=PORTAL_HOTKEYS_GLOBAL=0 --setenv=MAKERMODS_MODEL=makers
  --setenv=HAND_MAX_SPEED_M_S=${HAND_MAX_SPEED_M_S:-0.15} --setenv=HAND_MAX_JOINT_RAD_S=${HAND_MAX_JOINT_RAD_S:-0.5})

can_holders() { cat /proc/net/can/rcvlist_all /proc/net/can/rcvlist_fil | grep -cE "^ +can[01] " || true; }
stop_unit() { systemctl --user stop "$1" 2>/dev/null || true; systemctl --user reset-failed "$1" 2>/dev/null || true; }

check() {
  if ! systemctl --user is-active -q manifest-makerarm; then
    echo "Manifest's controller is not running; CAN holders: $(can_holders)"; return 0
  fi
  curl -s -m 4 -X POST -H 'content-type: application/json' -d '{}' http://127.0.0.1:8091/supervisor/preview | python3 -c '
import json, sys
REST_TOL = 0.15  # rad: rest pose reads within 0.06 of zero; further out the arm would drop when its motors go off
d = json.load(sys.stdin); st = d["status"]; bad = []
if st["state"] != "idle": bad.append("Manifest is running: " + st["state"])
if (d.get("lease") or {}).get("active"): bad.append("Manifest has an action running")
if d.get("problem"): bad.append("Manifest reports: " + d["problem"])
for side, v in d["measured"].items():
    far = max(abs(x) for x in v["positions_rad"])
    print(f"{side}: furthest joint from rest {far:.3f} rad, gripper {v.get("gripper"):.2f}, hottest motor {max(v["motor_temps_c"])} C")
    if far > REST_TOL: bad.append(side + " arm is not at rest: it would drop when its motors go off")
print("\n".join("BLOCKED: " + b for b in bad) or "OK to hand over: both arms at rest, Manifest idle")
sys.exit(1 if bad else 0)'
}

teleop() {
  stop_unit cv-teleop
  systemd-run -q --user --unit=cv-teleop --collect -p KillSignal=SIGINT --working-directory="$P" "${HAND_ENV[@]}" \
    "$P/.venv/bin/hand-teleop" --browser "$@"
  local since; since=$(date +%H:%M:%S)
  for _ in $(seq 1 60); do
    journalctl --user -u cv-teleop --since "$since" -o cat --no-pager | grep -q "laptop camera:" && break; sleep 2
  done
  journalctl --user -u cv-teleop --since "$since" -o cat --no-pager | grep -E "laptop camera:|connecting|Error|error" | tail -4
}

case "${1:-}" in
  check) check ;;
  preview) teleop --offline ;;
  on)
    systemctl --user is-active -q cv-robot && { echo "already on"; exit 0; }
    check
    stop_unit cv-teleop
    systemctl --user stop manifest-makerarm
    for _ in $(seq 1 20); do [ "$(can_holders)" = 0 ] && break; sleep 1; done
    [ "$(can_holders)" = 0 ] || { echo "ABORT: something still holds the CAN bus"; exit 1; }
    # Conflicts: starting Manifest's controller later stops this robot first; they never overlap.
    systemd-run -q --user --unit=cv-robot --collect -p KillSignal=SIGINT -p TimeoutStopSec=180 \
      -p Conflicts=manifest-makerarm.service -p After=manifest-makerarm.service \
      --working-directory="$P" "${ROBOT_ENV[@]}" "$P/.venv/bin/robot" --parked
    sleep 8
    journalctl --user -u cv-robot --since "-20s" -o cat --no-pager | tail -6 | cut -c1-170
    systemctl --user is-active -q cv-robot || { echo "ABORT: Portal robot did not stay up; giving the arms back to Manifest"; systemctl --user start manifest-makerarm; exit 1; }
    teleop
    echo "Arms are OFF until you press Take control, then Park / power up, on the page."
    ;;
  off)
    stop_unit cv-teleop
    stop_unit cv-robot   # SIGINT: parks first if powered, at METAL_PARK_DEG_S
    journalctl --user -u cv-robot --since "-3min" -o cat --no-pager | tail -4 | cut -c1-170
    systemctl --user start manifest-makerarm
    sleep 6; check
    ;;
  *) sed -n 2,9p "$0"; exit 2 ;;
esac
