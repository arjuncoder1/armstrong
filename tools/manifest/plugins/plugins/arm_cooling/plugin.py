"""Arm cooling: torque off/on per arm, Manifest's arm choice, and auto-rest status, for the Torque menu (ui.js).

    GET  /v1/arms/state                        state, usable arms, rest/lock/auto info, per-motor temps
    POST /v1/arms/rest   {"arm", "confirm_supported": true}   torque off (limp: support it)
    POST /v1/arms/wake   {"arm"}                              torque on, holds where it is
    POST /v1/arms/use|lock|unlock {"arm"}                     Manifest's arm choice (torque stays on)

Forwards to the station add-on tools/station/arm_rest.py (/supervisor/arm/*).
"""

ACTIONS = ("rest", "wake", "use", "lock", "unlock")


def handle(req):
    if not req.path.startswith("/v1/arms/"):
        return None
    kind = req.path[len("/v1/arms/"):]
    if kind == "state" and req.method == "GET":
        d = req.station("/supervisor/preview")
        return 200, {"state": (d.get("status") or {}).get("state"), "enabled_arms": d.get("enabled_arms") or [],
                     "arm_rest": d.get("arm_rest"), "problem": d.get("problem"),
                     "temps": {s: (v or {}).get("motor_temps_c") or [] for s, v in (d.get("measured") or {}).items()}}
    if kind in ACTIONS and req.method == "POST":
        return 200, req.station("/supervisor/arm/" + kind, req.body, timeout=30)
    return 404, {"error": f"unknown arms route: {req.method} {req.path}"}
