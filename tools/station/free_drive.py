"""Zero-G: weightless hand guiding for the MakerArm station. Gravity-compensated free drive that holds where you let go.

    POST /supervisor/arm/freedrive {"arm": "left"|"right"|"both", "on": true|false}
    /supervisor/preview|observe -> "free_drive": {"active": [...], "why": {...}}
    Teach's hand guidance uses it instead of going limp (patch_free_drive.py).

Each tick, every motor of a Zero-G arm gets one MIT frame:
  - feed-forward torque = the arm's own weight at the measured pose (maker_gravity, vendored from the SDK; on this
    station the right arm's holding torque matched it: lift 3.54 vs 3.51 N.m, elbow 3.97 vs 4.22 N.m),
  - a weak spring to an anchor the hand drags along (so it stays where it is let go), and light damping,
  - a stiffer spring near each soft limit.
Engage checks the model's sign against the holding torque, then ramps over RAMP_IN_S and refuses if the arm moves.
Every exit hands back to the normal stiff position hold at the measured pose: never limp, never home.
Trips (stale feedback, too fast, a motor at the stop temperature, non-finite numbers) exit at once to that hold.
"""

import math
import sys
import threading

import maker_gravity

FREE_DRIVE_MARK = "free_drive"
RAMP_IN_S = 0.5            # hold -> weightless
RAMP_OUT_S = 0.3           # weightless -> hold
ENGAGE_DRIFT_DEG = 2.0     # the arm may not move more than this while engaging
BAND_DEG = 2.0             # the anchor trails the hand by at most this
K_SOFT = (5.0, 20.0, 15.0, 6.0, 3.0, 3.0, 1.0)     # N.m/rad, pan .. wrist_roll, gripper: k * band = the hold on release
KD_FREE = (0.3, 0.6, 0.5, 0.15, 0.08, 0.08, 0.1)   # N.m s/rad
WALL_DEG = 8.0             # a stiffer spring starts this far inside each soft limit
WALL_GAIN = 0.5            # times the joint's hold kp
FRESH_S = 0.15             # every motor must have answered within this
MAX_SPEED_DEG_S = 150.0    # faster than a hand moves it: trip
ENGAGE_SPEED_DEG_S = 10.0  # the arm must be still to engage
NO_ENGAGE_C = 55.0         # Manifest's warn / no-energize temperature
STOP_C = 65.0              # Manifest's stop temperature
SIGN_MIN_NM = (9.9, 1.0, 1.0, 0.5, 9.9, 9.9)  # check the sign where both model and holding torque exceed this
LIMIT_NM = maker_gravity.LIMIT_NM


def encode_mit_ff(rs, model: str, kp: float, kd: float, position_deg: float, tau_nm: float) -> bytes:
    """robots.robstride.encode_mit with a feed-forward torque; identical bytes when tau_nm is 0."""
    pmax, vmax, tmax = rs.MOTOR_LIMITS[model]
    q = rs.float_to_uint(math.radians(position_deg), -pmax, pmax, 16)
    dq = rs.float_to_uint(0.0, -vmax, vmax, 12)
    kp_u = rs.float_to_uint(kp, *rs.KP_RANGE, 12)
    kd_u = rs.float_to_uint(kd, *rs.KD_RANGE, 12)
    tau = rs.float_to_uint(max(-tmax, min(tmax, tau_nm)), -tmax, tmax, 12)
    return bytes([(q >> 8) & 0xFF, q & 0xFF, dq >> 4, ((dq & 0xF) << 4) | ((kp_u >> 8) & 0xF), kp_u & 0xFF,
                  kd_u >> 4, ((kd_u & 0xF) << 4) | ((tau >> 8) & 0xF), tau & 0xFF])


def gravity(q_deg, scale: float) -> list[float]:
    """Six holding torques (motor sign), clamped to the SDK's per-joint caps."""
    g = maker_gravity.gravity_nm(q_deg[:6], scale)
    return [max(-c, min(c, x)) for x, c in zip(g, LIMIT_NM)]


class ArmZeroG:
    """One arm's Zero-G. Wraps its chain's command(); runs in the arm's own motor thread."""

    def __init__(self, side: str, driver) -> None:
        self.side, self.driver, self.chain = side, driver, driver.chain
        self.bus = self.chain.bus
        self.rs = sys.modules[type(self.bus).__module__]
        self.names = list(self.chain.names)
        if len(self.names) != 7 or not maker_gravity.model_applies(self.names):
            raise ValueError(f"Zero-G needs the Maker arm's six joints and a gripper, got {self.names}")
        self.lock = threading.Lock()
        self.changed = threading.Condition(self.lock)
        self.want, self.scale, self.state, self.why = False, 1.0, "off", ""
        self.goal = None
        self._orig = self.chain.command
        self.chain.command = self._command
        self.chain._zero_g = self

    # ---- requests (HTTP thread) ----
    def request(self, on: bool, scale: float = 1.0) -> None:
        with self.lock:
            self.want = on
            if on:
                self.scale, self.why = scale, ""

    def wait(self, on: bool, timeout: float) -> None:
        with self.lock:
            if on:
                self.changed.wait_for(lambda: self.state == "on" or (self.state == "off" and not self.want), timeout)
            else:
                self.changed.wait_for(lambda: self.state == "off", timeout)

    # ---- motor thread ----
    def _command(self, goal_deg):
        with self.lock:
            want, state = self.want, self.state
        if state == "off" and (not want or self.goal is None):  # first wrapped tick records the hold command
            reading = self._orig(goal_deg)
            self.goal = list(goal_deg)
            return reading
        try:
            if state == "off":
                refused = self._engage_check()
                if refused:
                    self._finish("off", refused, want=False)
                    reading = self._orig(goal_deg)
                    self.goal = list(goal_deg)
                    return reading
            return self._step(want)
        except Exception as exc:
            if self.state != "off":
                try:  # best effort: stiff hold where it is, and the stepper reseeded there, never back to the old pose
                    _, q, _, _, _ = self._read()
                    self._hand_back(q, gravity(q, self.scale) + [0.0], f"{type(exc).__name__}: {exc}")
                except Exception:
                    self._reseed_last()
            self._finish("off", f"{type(exc).__name__}: {exc}", want=False)
            raise

    def _finish(self, state: str, why: str = "", want: bool | None = None) -> None:
        with self.lock:
            self.state, self.why = state, why or self.why
            if want is not None:
                self.want = want
            self.changed.notify_all()

    def _read(self):
        now = self.chain._clock()
        q, dq, age, temp = [], [], [], []
        for n in self.names:
            st = self.bus.motors[n].state
            if st is None:
                raise RuntimeError(f"arm '{self.side}': {n} has no state")
            q.append(st.position_deg + self.chain._turn_offset[n])
            dq.append(st.velocity_deg_s)
            age.append(now - st.t)
            temp.append(st.temp_c)
        return now, q, dq, age, temp

    def _hold_gains(self, i: int):
        m = self.bus.motors[self.names[i]]
        return m.kp, m.kd

    def _engage_check(self) -> str:
        d, c = self.driver, self.chain
        if getattr(d, "_limp", False) or getattr(d, "_resting", False) or getattr(d, "_parked", False):
            return "the arm is limp, parking or parked"
        if c.stale_zero or not c.enabled:
            return "the arm is not energized"
        if self.goal is None:
            return "no hold command yet"
        now, q, dq, age, temp = self._read()
        if max(age) > FRESH_S:
            return f"stale motor feedback ({max(age) * 1000:.0f} ms)"
        if max(temp) >= NO_ENGAGE_C:
            return f"a motor is at {max(temp):.0f} C (no Zero-G at {NO_ENGAGE_C:.0f} C or more); let it cool"
        if max(abs(v) for v in dq[:6]) > ENGAGE_SPEED_DEG_S:
            return "the arm is moving; hold it still"
        hold = []
        for i, n in enumerate(self.names):
            low, high = c.limits_deg[n]
            kp, _ = self._hold_gains(i)
            hold.append(kp * math.radians(max(min(low, high), min(max(low, high), self.goal[i])) - q[i]))
        g = gravity(q, self.scale)
        if not all(math.isfinite(x) for x in g):
            return "gravity model gave a non-finite torque"
        for i in range(6):
            if abs(g[i]) >= SIGN_MIN_NM[i] and abs(hold[i]) >= SIGN_MIN_NM[i] and g[i] * hold[i] < 0:
                return (f"{self.names[i]}: holding {hold[i]:+.2f} N.m but the model says {g[i]:+.2f} N.m; "
                        "sign or calibration is off, refusing")
        self.t0, self.q0, self.tau0 = now, q, hold
        self.anchor = list(q)
        self._finish("ramp_in")
        return ""

    def _trip_reason(self, q, dq, age, temp) -> str:
        d = self.driver
        if getattr(d, "_resting", False) or getattr(d, "_parked", False):
            return "the arm was parked"
        if max(age) > FRESH_S:
            return f"stale motor feedback ({max(age) * 1000:.0f} ms)"
        if not all(math.isfinite(x) for x in (*q, *dq)):
            return "non-finite motor feedback"
        if max(abs(v) for v in dq[:6]) > MAX_SPEED_DEG_S:
            return f"moving faster than {MAX_SPEED_DEG_S:.0f} deg/s"
        if max(temp) >= STOP_C:
            return f"a motor reached {max(temp):.0f} C"
        return ""

    def _send(self, i: int, p_deg: float, kp: float, kd: float, tau: float) -> None:
        n, rs, bus = self.names[i], self.rs, self.bus
        low, high = self.chain.limits_deg[n]
        p_deg = max(min(low, high), min(max(low, high), p_deg)) - self.chain._turn_offset[n]
        with bus._lock:
            m = bus.motors[n]
            bus._send(m.can_id, encode_mit_ff(rs, m.model, kp, kd, p_deg, tau))
            data = bus._recv_from(m.can_id, rs.COMMAND_REPLY_TIMEOUT_S)
            if data is None:
                m.drops += 1
                return
            if rs.is_fault_frame(data):
                raise rs.MotorFault(f"{bus.channel}: {n} fault word 0x{int.from_bytes(data[1:5], 'little'):08X}")
            m.state = rs.decode_feedback(data, m.model, bus._clock())

    def _wall(self, i: int, q: float) -> float:
        low, high = self.chain.limits_deg[self.names[i]]
        kp, _ = self._hold_gains(i)
        k = WALL_GAIN * kp
        if q < low + WALL_DEG:
            return k * math.radians(low + WALL_DEG - q)
        if q > high - WALL_DEG:
            return -k * math.radians(q - (high - WALL_DEG))
        return 0.0

    def _step(self, want: bool):
        now, q, dq, age, temp = self._read()
        g = gravity(q, self.scale) + [0.0]
        trip = self._trip_reason(q, dq, age, temp)
        if not trip and not all(math.isfinite(x) for x in g):
            trip = "gravity model gave a non-finite torque"
        state = self.state
        if not trip and state == "ramp_in" and max(abs(a - b) for a, b in zip(q[:6], self.q0[:6])) > ENGAGE_DRIFT_DEG:
            trip = "the arm moved while engaging (gravity model does not match); refused"
        if trip:
            self._hand_back(q, g, trip)
            return self._reading()
        if not want and state != "ramp_out":
            state, self.t0, self.qx, self.gx = "ramp_out", now, list(self.anchor), g
            self._finish("ramp_out")
        if state == "ramp_in":
            s = min(1.0, (now - self.t0) / RAMP_IN_S)
            for i in range(7):
                kph, kdh = self._hold_gains(i)
                kp, kd = kph * (1 - s) + K_SOFT[i] * s, kdh * (1 - s) + KD_FREE[i] * s
                self._send(i, self.q0[i] + math.degrees(self.tau0[i] * (1 - s) / kp), kp, kd, g[i] * s)
            if s >= 1.0:
                self._finish("on")
        elif state == "on":
            for i in range(7):
                err = q[i] - self.anchor[i]
                if abs(err) > BAND_DEG:
                    self.anchor[i] = q[i] - math.copysign(BAND_DEG, err)
                wall = self._wall(i, q[i]) if i < 6 else 0.0
                tmax = self.rs.MOTOR_LIMITS[self.bus.motors[self.names[i]].model][2] * 0.9
                self._send(i, self.anchor[i], K_SOFT[i], KD_FREE[i], max(-tmax, min(tmax, g[i] + wall)))
        else:  # ramp_out: to the stiff hold at the anchor, which then carries the weight itself
            s = min(1.0, (now - self.t0) / RAMP_OUT_S)
            for i in range(7):
                kph, kdh = self._hold_gains(i)
                kp, kd = K_SOFT[i] * (1 - s) + kph * s, KD_FREE[i] * (1 - s) + kdh * s
                self._send(i, self.qx[i] + math.degrees(self.gx[i] * s / kp), kp, kd, g[i] * (1 - s))
            if s >= 1.0:
                self._hand_back(self.qx, self.gx, "")
        return self._reading()

    def _reading(self):
        self.chain._last = self.chain._read()
        self.chain._watch_replies()
        return self.chain._last

    def _reseed_last(self) -> None:
        q = [self.bus.motors[n].state.position_deg + self.chain._turn_offset[n] for n in self.names]
        self._reseed(q, [0.0] * 7)

    def _hand_back(self, q, g, why: str) -> None:
        """Stiff hold at q, carrying g, and the arm thread's stepper reseeded there so its next tick holds it."""
        try:
            for i in range(7):
                kph, kdh = self._hold_gains(i)
                self._send(i, q[i] + math.degrees(g[i] / kph), kph, kdh, 0.0)
        finally:
            self._reseed(q, g)
        self._finish("off", why, want=False)

    def _reseed(self, q, g) -> None:
        d = self.driver
        loop = [0.0] * (d.slots + 1)
        for i in range(d.joints):
            loop[i] = math.radians(q[i] + max(-5.0, min(5.0, math.degrees(g[i] / self._hold_gains(i)[0]))))
        loop[d.slots] = d.stroke.to_mm(q[d.joints])
        with d._lock:
            d._target = None
            d._held = None
            d.stepper.cmd = None
            d.stepper.seed(loop)
        self.goal = None


class FreeDrive:
    """The station's Zero-G helper (one per Bridge)."""

    def __init__(self, bridge) -> None:
        self.b = bridge
        self.teach_sides: set[str] = set()

    def _driver(self, side: str):
        arms = self.b.c._arms
        if side not in arms:
            raise ValueError(f"no {side!r} arm")
        return arms[side]._driver

    def _ctl(self, side: str, create: bool = False):
        d = self._driver(side)
        c = getattr(d.chain, "_zero_g", None)
        if c is None and create:
            c = ArmZeroG(side, d)
        return c

    def active(self, side: str) -> bool:
        try:
            c, d = self._ctl(side), self._driver(side)
        except Exception:
            return False
        return bool(c and c.state != "off" and d.is_alive() and not getattr(d, "_limp", False))

    def on(self) -> list[str]:
        return [s for s in ("left", "right") if self.active(s)]

    def why(self, side: str) -> str:
        try:
            c = self._ctl(side)
        except Exception as exc:
            return str(exc)
        return (c.why if c else "") or "it was turned off"

    def blocks(self, arm) -> str | None:
        hit = [s for s in self.on() if arm in (s, "both", None)]
        return f"the {' and '.join(hit)} arm is in Zero-G: turn Zero-G off first" if hit else None

    def engage(self, side: str, scale: float = 1.0, teach: bool = False) -> dict:
        b = self.b
        if not teach:
            if getattr(b, "cv", None) is not None and b.cv.busy:
                raise ValueError("Stop CV teleop before Zero-G")
            if b.lease and b.lease.get("active"):
                raise ValueError("Stop the running action before Zero-G")
            if b.teaching.active:
                raise ValueError("Teaching runs Zero-G itself; stop teaching first")
            rest = getattr(b, "rest", None)
            if rest is not None and side in rest.resting:  # torque is off: Torque ON first (reopens holding where it is)
                b.api.call(rest.wake({"arm": side}))
                if side in rest.resting:
                    raise ValueError(f"The {side} arm's torque did not come back on")
        if not 0.0 < scale <= 1.0:
            raise ValueError("scale must be in (0, 1]")
        d = self._driver(side)
        if not d.is_alive():
            raise ValueError(f"The {side} arm's motor thread is not running")
        c = self._ctl(side, create=True)
        if c.state != "off":
            return {"ok": True, "arm": side, "zero_g": True}
        c.request(True, scale)
        c.wait(True, RAMP_IN_S + 2.0)
        if c.state == "on":
            if teach:
                self.teach_sides.add(side)
            return {"ok": True, "arm": side, "zero_g": True}
        c.request(False)
        c.wait(False, RAMP_OUT_S + 1.0)
        raise ValueError(f"Zero-G refused on the {side} arm: {c.why or 'no motor tick in time'}")

    def release(self, side: str) -> dict:
        self.teach_sides.discard(side)
        c = self._ctl(side)
        if c is None or c.state == "off":
            return {"ok": True, "arm": side, "zero_g": False}
        c.request(False)
        c.wait(False, RAMP_OUT_S + 1.0)
        if c.state != "off":
            raise ValueError(f"The {side} arm did not leave Zero-G in time")
        return {"ok": True, "arm": side, "zero_g": False}

    def route(self, body: dict) -> dict:
        arm = body.get("arm")
        sides = ("left", "right") if arm == "both" else (arm,)
        if not all(s in ("left", "right") for s in sides):
            raise ValueError('arm must be "left", "right" or "both"')
        on = bool(body.get("on", True))
        out = [self.engage(s, float(body.get("scale", 1.0))) if on else self.release(s) for s in sides]
        return {"ok": True, "arms": out, "free_drive": self.public()}

    def public(self) -> dict:
        why = {}
        for s in ("left", "right"):
            try:
                c = self._ctl(s)
                if c and c.why:
                    why[s] = c.why
            except Exception:
                pass
        return {"active": self.on(), "teach": sorted(self.teach_sides), "why": why}
