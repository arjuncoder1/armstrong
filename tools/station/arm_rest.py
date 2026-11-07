"""Rest one MakerArm (torque off) while the other keeps working, so the two can take turns cooling.

Plugs into the Manifest MakerArm station (makerarm_control.py, wired in by patch_arm_rest.py):

    POST /supervisor/arm/rest {"arm": "left"|"right"|"both", "confirm_supported": true}  torque off: the arm goes LIMP
    POST /supervisor/arm/wake {"arm": "left"|"right"|"both"}                            torque on, holding where it is
    /supervisor/preview|observe -> "arm_rest": {...}; enabled_arms drops the resting arm, locked_arms lists it

Resting uses the same driver call as Teach's hand guidance (`_driver.disengage()`); waking reopens the driver at
the measured pose exactly like Teach's hold (never home). While an arm rests the station refuses anything that
would drive it: actions scoped to it or to both arms, native home, reset (it re-homes both), teaching and CV
teleop. Manifest keeps working on the other arm; with both resting, nothing can move until one wakes.

The arms have no brakes: rest an arm only when it is supported or already at its rest pose.
"""

from __future__ import annotations

import time

SIDES = ("left", "right")


class ArmRest:
    def __init__(self, bridge) -> None:
        self.b = bridge
        self.resting: dict[str, float] = {}  # side -> time.time() it went limp

    # -- state ---------------------------------------------------------------------------------------

    def public(self) -> dict:
        now = time.time()
        return {"resting": sorted(self.resting),
                "resting_s": {side: round(now - t) for side, t in self.resting.items()},
                "awake": [s for s in SIDES if s not in self.resting]}

    def blocks(self, arm: str | None) -> str | None:
        """Why a command for `arm` ('left'/'right'/'both'/None = all) can't run now, or None."""
        if not self.resting:
            return None
        hit = sorted(self.resting) if arm in (None, "both") else [arm] if arm in self.resting else []
        if hit:
            return f"the {' and '.join(hit)} arm is resting (torque off); use the other arm or wake it first"
        return None

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
            c._set_state("idle")
        except Exception as exc:
            c._record_error(exc)
            c._set_state("error")
            raise
