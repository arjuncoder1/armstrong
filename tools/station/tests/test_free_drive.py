"""Offline checks for free_drive.py: encoder parity, gravity fixtures, and a simulated arm (real MIT frames, the real
gravity model as the load) through engage, hand push, let go, release, trips and a sign error.
Run: python3 tests/test_free_drive.py [path/to/halo/robots/robstride.py]"""
import ast, json, math, sys, threading, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import maker_gravity  # noqa: E402

RS_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent.parent / "halo" / "robstride.py"

# The real encoder/decoder, lifted out of robots/robstride.py without its package imports.
src = RS_PATH.read_text()
tree = ast.parse(src)
want = {"float_to_uint", "uint_to_float", "encode_mit", "decode_feedback", "is_fault_frame", "MotorState"}
rs = types.ModuleType("fake_robstride")
rs.__dict__.update(math=math, dataclasses=__import__("dataclasses"))
body = [n for n in tree.body if (isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in want)
        or (isinstance(n, (ast.Assign, ast.AnnAssign)) and any(
            getattr(t, "id", "") in ("MOTOR_LIMITS", "KP_RANGE", "KD_RANGE", "COMMAND_REPLY_TIMEOUT_S")
            for t in ([n.target] if isinstance(n, ast.AnnAssign) else n.targets)))]
exec(compile(ast.Module(body=body, type_ignores=[]), str(RS_PATH), "exec"), rs.__dict__)
class MotorFault(Exception): pass
rs.MotorFault = MotorFault
sys.modules["fake_robstride"] = rs

import free_drive as fd  # noqa: E402

fails = []
def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
    if not ok:
        fails.append(name)

# 1. encoder parity at tau 0, and tau packs
for model in ("O0", "O1"):
    for kp, kd, p in ((150, 4.5, -82.3), (0, 0, 0), (20, 0.5, 236.1), (499, 4.9, -175.3)):
        check(f"encode parity {model} kp{kp}", fd.encode_mit_ff(rs, model, kp, kd, p, 0.0) == rs.encode_mit(model, kp, kd, p))
f = fd.encode_mit_ff(rs, "O1", 20, 0.6, 10.0, 3.5)
tau = rs.uint_to_float(((f[6] & 0xF) << 8) | f[7], -17.0, 17.0, 12)
check("tau packs", abs(tau - 3.5) < 0.01, f"{tau:.3f}")

# 2. gravity fixtures (the vendored model is the SDK's)
fx = json.loads((HERE / "gravity_fixtures.json").read_text())
fx = fx if isinstance(fx, list) else fx.get("cases", fx.get("fixtures", []))
worst = max(max(abs(a - b) for a, b in zip(maker_gravity.gravity_nm(c["q_deg"]), c["tau_nm"])) for c in fx)
check(f"gravity fixtures x{len(fx)}", worst < 1e-6, f"worst {worst:.2e}")

# 3. simulated arm
NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_yaw", "wrist_roll", "gripper"]
LIM = {"shoulder_pan": (-158.2, 156.1), "shoulder_lift": (-175.3, -3.2), "elbow_flex": (2.8, 236.1),
       "wrist_flex": (-65.2, 104.0), "wrist_yaw": (-97.6, 78.0), "wrist_roll": (-153.2, 152.0), "gripper": (0.0, 90.0)}
GAINS = [(60, 4.0, "O0"), (150, 4.5, "O1"), (90, 3.0, "O1"), (30, 2.0, "O0"), (30, 2.0, "O0"), (30, 2.0, "O0"), (20, 0.5, "O0")]
INERTIA = [0.03, 0.08, 0.04, 0.01, 0.005, 0.003, 0.002]

def fb_bytes(cid, model, q_deg, dq_deg, tau, temp):
    pmax, vmax, tmax = rs.MOTOR_LIMITS[model]
    q = rs.float_to_uint(math.radians(q_deg), -pmax, pmax, 16)
    dq = rs.float_to_uint(math.radians(dq_deg), -vmax, vmax, 12)
    t = rs.float_to_uint(tau, -tmax, tmax, 12)
    tw = int(temp * 10)
    return bytes([cid, q >> 8, q & 0xFF, dq >> 4, ((dq & 0xF) << 4) | (t >> 8), t & 0xFF, (tw >> 8) & 0x0F, tw & 0xFF])

class Sim:
    def __init__(self, q0, sign=1.0, model_err=(0, 0, 0, 0, 0, 0)):
        self.t, self.q, self.dq = 0.0, list(q0), [0.0] * 7
        self.sign, self.err, self.ext = sign, model_err, [0.0] * 7
        self.frame = {i + 1: None for i in range(7)}
        self.tau_out = [0.0] * 7
        self.temp = 40.0
    def load(self):
        g = maker_gravity.gravity_nm(self.q[:6])
        return [self.sign * gi + e for gi, e in zip(g, self.err)] + [0.0]
    def motor_tau(self, i):
        fr = self.frame[i + 1]
        if fr is None:
            return 0.0
        model = GAINS[i][2]; pmax, vmax, tmax = rs.MOTOR_LIMITS[model]
        p = math.degrees(rs.uint_to_float((fr[0] << 8) | fr[1], -pmax, pmax, 16))
        kp = rs.uint_to_float(((fr[3] & 0xF) << 8) | fr[4], 0, 500, 12)
        kd = rs.uint_to_float((fr[5] << 4) | (fr[6] >> 4), 0, 5, 12)
        tau = rs.uint_to_float(((fr[6] & 0xF) << 8) | fr[7], -tmax, tmax, 12)
        return max(-tmax, min(tmax, kp * math.radians(p - self.q[i]) - kd * math.radians(self.dq[i]) + tau))
    def advance(self, dt):
        n = int(round(dt / 0.0005))
        for _ in range(n):
            g = self.load()
            for i in range(7):
                m = self.motor_tau(i); self.tau_out[i] = m
                fric = 0.05 * math.copysign(1, self.dq[i]) if abs(self.dq[i]) > 0.5 else 0.0
                acc = (m - g[i] + self.ext[i] - fric - 0.02 * math.radians(self.dq[i])) / INERTIA[i]
                self.dq[i] += math.degrees(acc) * 0.0005
                self.q[i] += self.dq[i] * 0.0005
            self.t += 0.0005

class Motor:
    def __init__(self, i):
        self.can_id, self.kp, self.kd, self.model = i + 1, GAINS[i][0], GAINS[i][1], GAINS[i][2]
        self.state, self.drops = None, 0

class Bus:
    channel = "sim"
    def __init__(self, sim):
        self.sim, self._lock = sim, threading.RLock()
        self.motors = {n: Motor(i) for i, n in enumerate(NAMES)}
        self.stale = False
    def _clock(self): return self.sim.t
    def _send(self, cid, data): self.sim.frame[cid] = bytes(data)
    def _recv_from(self, cid, timeout):
        if self.stale: return None
        i = cid - 1
        return fb_bytes(cid, GAINS[i][2], self.sim.q[i], self.sim.dq[i], self.sim.tau_out[i], self.sim.temp)
    def refresh(self):
        for i, n in enumerate(NAMES):
            d = self._recv_from(i + 1, 0)
            if d: self.motors[n].state = rs.decode_feedback(d, GAINS[i][2], self.sim.t)
Bus.__module__ = "fake_robstride"

class Chain:
    def __init__(self, bus):
        self.bus, self.names, self.limits_deg = bus, tuple(NAMES), LIM
        self._turn_offset = dict.fromkeys(NAMES, 0.0)
        self.stale_zero, self.enabled, self._last = False, True, None
    def _clock(self): return self.bus.sim.t
    def command(self, goal):
        for n, p in zip(self.names, goal):
            lo, hi = self.limits_deg[n]; m = self.bus.motors[n]
            with self.bus._lock:
                self.bus._send(m.can_id, rs.encode_mit(m.model, m.kp, m.kd, max(lo, min(hi, p))))
                d = self.bus._recv_from(m.can_id, 0)
                if d: m.state = rs.decode_feedback(d, m.model, self.bus.sim.t)
        return self._read()
    def _read(self): return [self.bus.motors[n].state.position_deg for n in self.names]
    def _watch_replies(self): pass

class Stepper:
    stroke_mm = (0.0, 90.0)
    def __init__(self): self.cmd = None
    def seed(self, m):
        if self.cmd is None: self.cmd = [float(x) for x in m]

class Driver:
    def __init__(self, sim):
        self.bus = Bus(sim); self.chain = Chain(self.bus); self.stepper = Stepper()
        self._lock = threading.Lock(); self._target = None; self._held = None
        self._limp = self._resting = self._parked = False
        self.joints, self.slots = 6, 6
        self.stroke = types.SimpleNamespace(to_mm=lambda deg: deg)
    def is_alive(self): return True
    def tick(self):
        self.bus.refresh()
        meas = [math.radians(self.bus.motors[n].state.position_deg) for n in NAMES[:6]] + [self.bus.motors["gripper"].state.position_deg]
        self.stepper.seed(meas)
        goal = [math.degrees(x) for x in self.stepper.cmd[:6]] + [self.stepper.cmd[6]]
        self.chain.command(goal)

POSE = [5.0, -82.0, 65.0, 20.0, 0.0, 0.0, 30.0]  # an arm raised so lift/elbow carry real weight

def run(drv, sim, seconds, during=None):
    for _ in range(int(seconds * 60)):
        sim.advance(1 / 60)
        if during: during()
        drv.tick()

def make(sign=1.0, err=(0, 0, 0, 0, 0, 0), pose=POSE):
    sim = Sim(pose, sign, err); drv = Driver(sim)
    # gravity sag: start where a stiff hold settles, commanded at pose
    drv.bus.refresh(); drv.stepper.cmd = [math.radians(x) for x in pose[:6]] + [pose[6]]
    run(drv, sim, 1.0)
    return sim, drv

def engage(drv, sim):
    c = fd.ArmZeroG("right", drv)
    c.request(True)
    run(drv, sim, fd.RAMP_IN_S + 0.2)
    return c

sim, drv = make()
held = list(sim.q)
check("hold sags like the real arm (lift < 2 deg, elbow < 4 deg)", abs(held[1] - POSE[1]) < 2 and abs(held[2] - POSE[2]) < 4,
      f"lift {held[1] - POSE[1]:+.2f}, elbow {held[2] - POSE[2]:+.2f}")
c = engage(drv, sim)
check("engages", c.state == "on", c.why)
check("no jump on engage (< 1 deg)", max(abs(a - b) for a, b in zip(sim.q[:6], held[:6])) < 1.0,
      f"{max(abs(a - b) for a, b in zip(sim.q[:6], held[:6])):.3f}")
run(drv, sim, 3.0)
check("weightless: stays put untouched for 3 s (< BAND)", max(abs(a - b) for a, b in zip(sim.q[:6], held[:6])) < fd.BAND_DEG + 0.5)
# hand push on the lift and elbow: 1.2 N.m for 0.6 s, then let go
start = list(sim.q)
sim.ext[1], sim.ext[2] = 1.2, -0.8
run(drv, sim, 0.6)
sim.ext[1] = sim.ext[2] = 0.0
moved = sim.q[1] - start[1]
check("a light push moves it (> 10 deg on lift)", abs(moved) > 10, f"{moved:+.1f} deg")
run(drv, sim, 0.5)
let_go = list(sim.q)
run(drv, sim, 3.0)
drift = max(abs(a - b) for a, b in zip(sim.q[:6], let_go[:6]))
check("holds where let go (drift < 1 deg over 3 s)", drift < 1.0, f"{drift:.3f}")
check("effortless: lift kp in Zero-G", fd.K_SOFT[1] * math.radians(fd.BAND_DEG) < 1.0, f"{fd.K_SOFT[1] * math.radians(fd.BAND_DEG):.2f} N.m max drag")
before = list(sim.q)
c.request(False)
run(drv, sim, fd.RAMP_OUT_S + 0.2)
check("releases to off", c.state == "off", c.why)
run(drv, sim, 2.0)
jump = max(abs(a - b) for a, b in zip(sim.q[:6], before[:6]))
check("release holds stiff where it is (< 1 deg, no snap back)", jump < 1.0, f"{jump:.3f}")
check("stepper reseeded at the new pose", abs(math.degrees(drv.stepper.cmd[1]) - before[1]) < 3.0)

# the left arm at rest (2026-11-07): the hold sags the elbow 3 deg past its soft limit (2.8) and the lift sits 0.9 deg from
# its limit (-3.2). Zero-G must engage there without a kick, stay put, and lift out of rest with a light push.
REST = [-1.5, -4.0, 2.8, 2.6, 5.7, -5.8, 30.0]
sim, drv = make(pose=REST)
held = list(sim.q)
check("rest pose sags past the elbow limit like the real arm", held[2] < 0.5, f"elbow {held[2]:+.2f}")
c = engage(drv, sim)
check("engages at rest", c.state == "on", c.why)
run(drv, sim, 2.0)
kick = max(abs(a - b) for a, b in zip(sim.q[:6], held[:6]))
check("no kick at rest: stays put, no trip (< 1 deg over 2 s)", c.state == "on" and kick < 1.0, f"{kick:.2f} deg, {c.why}")
sim.ext[1] = -1.0; run(drv, sim, 0.6); sim.ext[1] = 0.0
run(drv, sim, 0.5); let_go = list(sim.q); run(drv, sim, 2.0)
check("a light push lifts it out of rest and it holds there", c.state == "on" and abs(let_go[1] - held[1]) > 5
      and max(abs(a - b) for a, b in zip(sim.q[:6], let_go[:6])) < 1.0, f"lift {let_go[1] - held[1]:+.1f}, {c.why}")

# model error inside the drag band: still holds
sim, drv = make(err=(0, 0.0, 0.25, 0.1, 0, 0))
c = engage(drv, sim); g0 = list(sim.q)
run(drv, sim, 3.0)
check("elbow model error 0.25 N.m: holds (< BAND+0.5)", c.state == "on" and abs(sim.q[2] - g0[2]) < fd.BAND_DEG + 0.5, f"{sim.q[2] - g0[2]:+.2f}")

# sign error: the model fights gravity -> refused at engage, arm stays held
sim, drv = make(sign=-1.0)
held = list(sim.q)
c = fd.ArmZeroG("right", drv); c.request(True); run(drv, sim, 1.0)
check("sign error refused", c.state == "off" and "refusing" in c.why, c.why)
check("sign error: arm did not move", max(abs(a - b) for a, b in zip(sim.q[:6], held[:6])) < 0.5)

# stale feedback trips to stiff hold
sim, drv = make(); c = engage(drv, sim)
drv.bus.stale = True
for _ in range(15):
    sim.advance(1 / 60)
    try: drv.chain.command([0] * 7)
    except Exception: pass
drv.bus.stale = False
run(drv, sim, 1.0)
check("stale feedback trips off", c.state == "off" and "stale" in c.why, c.why)

# hot motor refuses engage
sim, drv = make(); sim.temp = 56.0; drv.bus.refresh()
c = fd.ArmZeroG("right", drv); c.request(True); run(drv, sim, 0.5)
check("56 C refuses", c.state == "off" and "cool" in c.why, c.why)

# flung arm trips
sim, drv = make(); c = engage(drv, sim)
sim.ext[0] = 3.0; run(drv, sim, 1.5); sim.ext[0] = 0
check("too fast trips off", c.state == "off" and "faster" in c.why, c.why)

# Zero-G on an arm whose torque is off: Torque ON (arm_rest wake) first, then weightless
import asyncio
sim, drv = make()
class Rest:
    def __init__(self): self.resting = {"right": 1.0}
    async def wake(self, body): self.resting.pop(body["arm"], None); return {}
class Api:
    def call(self, coro): return asyncio.run(coro)
bridge = types.SimpleNamespace(c=types.SimpleNamespace(_arms={"right": types.SimpleNamespace(_driver=drv)}), rest=Rest(),
                               api=Api(), cv=types.SimpleNamespace(busy=False), lease=None,
                               teaching=types.SimpleNamespace(active=False))
F = fd.FreeDrive(bridge)
ticker = threading.Thread(target=lambda: run(drv, sim, 2.0)); ticker.start()
out = F.route({"arm": "right", "on": True}); ticker.join()
check("Zero-G on a torque-off arm wakes it, then engages", bridge.rest.resting == {} and out["free_drive"]["active"] == ["right"], str(out))

print("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
