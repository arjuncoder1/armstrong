"""Rest one MakerArm (torque off) while the other keeps working, so the two can take turns cooling.

Plugs into the Manifest MakerArm station (makerarm_control.py, wired in by patch_arm_rest.py):

    POST /supervisor/arm/rest {"arm": "left"|"right"|"both", "confirm_supported": true}  torque off: the arm goes LIMP
    POST /supervisor/arm/wake {"arm": "left"|"right"|"both"}                            torque on, holding where it is
    POST /supervisor/arm/lock {"arm": ...}     Manifest may not use it; torque stays ON, it holds where it is
    POST /supervisor/arm/unlock {"arm": ...}   Manifest may use it again
    POST /supervisor/arm/use {"arm": "left"|"right"|"both"}   lock the other arm (or unlock both): pick Manifest's arm
    /supervisor/preview|observe -> "arm_rest": {...}; enabled_arms drops the resting arm, locked_arms lists it

Resting uses the same driver call as Teach's hand guidance (`_driver.disengage()`); waking reopens the driver at
the measured pose exactly like Teach's hold (never home). While an arm rests the station refuses anything that
would drive it: actions scoped to it or to both arms, native home, reset (it re-homes both), teaching and CV
teleop. Manifest keeps working on the other arm; with both resting, nothing can move until one wakes.

The arms have no brakes: rest an arm only when it is supported or already at its rest pose.

Auto-rest (ARM_AUTO_REST_S idle seconds, default 60; 0 turns it off): an awake arm that has been idle that long AND
sits at its rest pose (every joint within ARM_AUTO_REST_TOL_RAD of zero, default 0.15) goes torque-off by itself, since
it rests on its own support there. An idle arm away from the rest pose stays powered and gets a notice instead.
An action that needs an auto-rested arm wakes it first.
"""

from __future__ import annotations

import os
import threading
import time

SIDES = ("left", "right")


class ArmRest:
    def __init__(self, bridge) -> None:
        self.b = bridge
        self.resting: dict[str, float] = {}  # side -> time.time() it went limp (torque off)
        self.locked: dict[str, float] = {}  # side -> time.time() it was locked (torque on, Manifest may not use it)
        self.auto_rested: set[str] = set()  # resting arms that auto-rest turned off (an action may wake them)
        self.auto_idle_s = float(os.environ.get("ARM_AUTO_REST_S", "60"))
        self.auto_tol = float(os.environ.get("ARM_AUTO_REST_TOL_RAD", "0.15"))
        self.notices: dict[str, str] = {}  # side -> why auto-rest left it powered
        self._active = {s: time.monotonic() for s in SIDES}  # last time each arm was busy or moving
        self._last_pos: dict[str, list[float]] = {}
        if self.auto_idle_s > 0:
            threading.Thread(target=self._auto_loop, name="arm-auto-rest", daemon=True).start()

    # -- state ---------------------------------------------------------------------------------------

    def held(self) -> list[str]:
        """Arms Manifest may not drive: resting (limp) or locked (holding)."""
        return sorted(set(self.resting) | set(self.locked))

    def public(self) -> dict:
        now = time.time()
        return {"resting": sorted(self.resting),
                "resting_s": {side: round(now - t) for side, t in self.resting.items()},
                "locked": sorted(self.locked),
                "auto": {"idle_s": self.auto_idle_s, "tol_rad": self.auto_tol, "rested": sorted(self.auto_rested),
                         "notices": dict(self.notices)},
                "awake": [s for s in SIDES if s not in self.resting],
                "usable": [s for s in SIDES if s not in self.held()]}

    def blocks(self, arm: str | None) -> str | None:
        """Why a command for `arm` ('left'/'right'/'both'/None = all) can't run now, or None."""
        wake = [s for s in self.auto_rested if s in self.resting and (arm in (None, "both") or arm == s)]
        for side in wake:  # it went off only because it sat idle at rest: bring it back for this action
            self._wake(side)
        held = self.held()
        if not held:
            return None
        hit = held if arm in (None, "both") else [arm] if arm in held else []
        if not hit:
            return None
        why = [f"the {s} arm is {'resting (torque off)' if s in self.resting else 'locked'}" for s in hit]
        return "; ".join(why) + ": use the other arm, or wake/unlock it first"

    # -- commands ------------------------------------------------------------------------------------

    def _check_quiet(self) -> None:
        b = self.b
        if b.cv.busy or (b.lease and b.lease.get("active")):
            raise ValueError("Stop active control first")
        if b.teaching.active:
            raise ValueError("Finish teaching first")
        if b.native_task and not b.native_task.done():
            raise ValueError("A native move is still running")
        if b.c.state not in ("idle", "error"):
            raise ValueError("Station must be idle: " + b.c.state)

    @staticmethod
    def _sides(body: dict) -> tuple[str, ...]:
        side = body.get("arm")
        if side == "both":
            return SIDES
        if side not in SIDES:
            raise ValueError("Specify arm: left, right, or both")
        return (side,)

    async def rest(self, body: dict) -> dict:
        sides = [s for s in self._sides(body) if s not in self.resting]
        if not sides:
            return self.public()
        if body.get("confirm_supported") is not True:
            raise ValueError("Resting turns torque off and the arm goes limp: confirm it is supported or at rest")
        self._check_quiet()
        for side in sides:
            self.b.c._arms[side]._driver.disengage()  # Teach's hand-guidance call: torque off, feedback stays on
            self.resting[side] = time.time()
            self.auto_rested.discard(side)  # an operator's rest is not auto: actions won't wake it
        return self.public()

    async def lock(self, body: dict) -> dict:
        for side in self._sides(body):
            self.locked.setdefault(side, time.time())
        return self.public()

    async def unlock(self, body: dict) -> dict:
        for side in self._sides(body):
            self.locked.pop(side, None)
        return self.public()

    async def use(self, body: dict) -> dict:
        """Pick the arm(s) Manifest may use: the others are locked (torque stays on)."""
        keep = set(self._sides(body))
        for side in SIDES:
            if side in keep:
                self.locked.pop(side, None)
            else:
                self.locked.setdefault(side, time.time())
        return self.public()

    async def wake(self, body: dict) -> dict:
        for side in self._sides(body):
            if side in self.resting:
                self._wake(side)
        return self.public()

    def _wake(self, side: str) -> None:
        self._check_quiet()
        # Teach's hold: native MakerArm drivers resume by reopening at the measured pose, never home.
        import makerarm_teaching
        from robots import bodies, config

        cfg = config.load(makerarm_teaching.HERE / "makerarm-station.yaml")
        arm_cfg = cfg.follower_l if side == "left" else cfg.follower_r
        c = self.b.c
        c._set_state("resetting")
        try:
            c._arms[side]._driver.close()
            c._arms[side] = bodies.for_config(cfg).open_arm(arm_cfg, side)
            self.b.install_scopes()
            self.b.teaching.hook_arms()
            self.resting.pop(side, None)
            self.auto_rested.discard(side)
            self._active[side] = time.monotonic()
            c._set_state("idle")
        except Exception as exc:
            c._record_error(exc)
            c._set_state("error")
            raise

    # -- auto-rest -------------------------------------------------------------------------------------

    def _busy(self) -> bool:
        b = self.b
        return bool(b.cv.busy or (b.lease and b.lease.get("active")) or b.teaching.active
                    or (b.native_task and not b.native_task.done()) or b.c.state not in ("idle",))

    def _auto_loop(self) -> None:
        while True:
            time.sleep(2)
            try:
                self.b.api.call(self._auto_tick())
            except Exception as exc:  # noqa: BLE001 - never kill the station over auto-rest
                self.notices["_"] = f"auto-rest paused: {exc}"

    async def _auto_tick(self) -> None:
        self.notices.pop("_", None)
        now = time.monotonic()
        if self._busy():
            for side in SIDES:
                self._active[side] = now
            return
        measured = self.b.measured()
        for side in SIDES:
            pos = list((measured.get(side) or {}).get("positions_rad") or [])
            last = self._last_pos.get(side)
            self._last_pos[side] = pos
            if side in self.resting:
                self.notices.pop(side, None)
                continue
            if not pos or last is None or max(abs(a - b) for a, b in zip(pos, last)) > 0.01:
                self._active[side] = now
                self.notices.pop(side, None)
                continue
            idle = now - self._active[side]
            if idle < self.auto_idle_s:
                continue
            off = max(abs(x) for x in pos[:6])
            if off <= self.auto_tol:
                self.b.c._arms[side]._driver.disengage()
                self.resting[side] = time.time()
                self.auto_rested.add(side)
                self.notices.pop(side, None)
            else:
                self.notices[side] = (f"idle {idle / 60:.0f} min but not at the rest pose (a joint is {off:.2f} rad off): "
                                      "kept powered; home it or turn torque off by hand")
