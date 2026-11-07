"""Direct robot control without Manifest's agent: Dream-1 actions and grippers straight to the station.

    GET  /v1/direct/state                       state, lease, usable arms, joints, grippers, temps
    POST /v1/direct/act   {"instruction", "arm": "left"|"right"|"both", "seconds": 0.5-12,
                           "gripper_mode": "hold"|"active", "dry_run": false}
         -> fresh observation, /supervisor/action (Dream-1), heartbeats until the lease ends; returns the outcome
    POST /v1/direct/gripper {"arm", "target": 0..1, "dry_run": false}
    POST /v1/direct/stop                        stop any running action now

Motion needs Manifest's execute_allowed. dry_run observes and validates, never moves. The station enforces safety
(shield, speed, temperatures, rest/lock/Zero-G guards); this only removes the LLM from the loop.
"""

import time

SIDES = ("left", "right", "both")


def _summary(d):
    st = d.get("status") or {}
    return {"state": st.get("state"), "problem": d.get("problem"), "enabled_arms": d.get("enabled_arms"),
            "lease": d.get("lease"), "arm_rest": d.get("arm_rest"),
            "arms": {s: {"positions_rad": v.get("positions_rad"), "gripper": v.get("gripper"),
                         "max_temp_c": max(v.get("motor_temps_c") or [0])} for s, v in (d.get("measured") or {}).items()}}


def _check(req, arm):
    if arm not in SIDES:
        return 400, {"error": "arm must be left, right, or both"}
    if not req.motion_allowed:
        return 409, {"error": "Manifest has motion disabled (settings.execute_allowed)"}
    return None


def _run(req, start_body, seconds):
    """Start an action and keep it alive until the station ends its lease."""
    seen = req.station("/supervisor/observe", {}, timeout=10)
    start_body["observation_id"] = seen["observation_id"]
    started = req.station("/supervisor/action", start_body, timeout=30)
    lease = (started.get("lease") or {})
    ident, t0 = lease.get("id"), time.monotonic()
    while lease.get("active") and time.monotonic() - t0 < seconds + 45:  # the station's own start timeout is 45 s
        time.sleep(1.0)
        try:
            lease = req.station("/supervisor/heartbeat", {"lease_id": ident}, timeout=5).get("lease") or {}
        except Exception:  # noqa: BLE001 - lease gone: read why below
            break
    if lease.get("active"):  # never leave Dream-1 running past our budget
        req.station("/supervisor/stop", {"lease_id": ident}, timeout=10)
    after = req.station("/supervisor/preview", {}, timeout=5)
    final = after.get("lease") or lease
    return 200, {"ok": final.get("reason") in ("duration_complete", "action_complete"), "reason": final.get("reason"),
                 "elapsed_s": round(time.monotonic() - t0, 1), "lease": final, "after": _summary(after)}


def handle(req):
    if not req.path.startswith("/v1/direct/"):
        return None
    kind, b = req.path[len("/v1/direct/"):], req.body
    if kind == "state" and req.method == "GET":
        return 200, _summary(req.station("/supervisor/preview"))
    if req.method != "POST":
        return 405, {"error": "POST only"}
    if kind == "stop":
        return 200, req.station("/supervisor/stop", {}, timeout=10)
    if kind == "act":
        arm, text = b.get("arm", "right"), str(b.get("instruction", "")).strip()
        seconds = float(b.get("seconds", 8))
        if not text:
            return 400, {"error": "instruction is required"}
        if not 0.5 <= seconds <= 12:
            return 400, {"error": "seconds must be 0.5-12"}
        if (bad := _check(req, arm)) is not None:
            return bad
        body = {"arm": arm, "gripper_mode": b.get("gripper_mode", "active"), "seconds": seconds, "instruction": text}
        if b.get("dry_run"):
            return 200, {"dry_run": True, "would_send": body, "now": _summary(req.station("/supervisor/preview"))}
        return _run(req, body, seconds)
    if kind == "gripper":
        arm, target = b.get("arm"), b.get("target")
        if arm not in ("left", "right") or not isinstance(target, (int, float)) or not 0 <= target <= 1:
            return 400, {"error": "gripper needs arm left|right and target 0..1"}
        if (bad := _check(req, arm)) is not None:
            return bad
        body = {"arm": arm, "gripper_target": float(target), "seconds": 3}
        if b.get("dry_run"):
            return 200, {"dry_run": True, "would_send": body, "now": _summary(req.station("/supervisor/preview"))}
        return _run(req, body, 3)
    return 404, {"error": f"unknown direct route: {kind}"}
