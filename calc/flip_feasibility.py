#!/usr/bin/env python3
"""Can the Maker Arm throw a bottle flip? Preliminary sizing, not a guarantee.

Planar 3-joint model (shoulder_lift, elbow_flex, wrist_flex) from maker_arm/gravity.py.
Inverse dynamics along a constant-acceleration ramp to release, with point masses.

Load case: 0.2 kg bottle (500 mL, about 1/3 full) held rigidly, side grasp, released at
the end of the ramp. Free flight with constant spin.

NOT analysed: water slosh, gripper slip and release lag, link flex, link self-inertia,
motor current or heat, fatigue or impact on the printed structure, the stop after release.
"""
import itertools, math

G = 9.81
L1, L2 = 0.19, 0.19               # shoulder-elbow, elbow-wrist (m), from CHAIN
WRIST_TO_ROLL = 0.138             # wrist_flex to wrist_roll
GRASP = 0.278                     # wrist_flex to jaws
SHOULDER_Z = 0.089                # shoulder height above base
BOTTLE = 0.2
LANDING_COM = 0.05                # bottle centre of mass height at landing (m)
TAU = (17.0, 17.0, 14.0)          # peak torque (N*m): RS02, RS02, RS00, from protocol.py
INERTIA_MARGIN = 1.15             # stand-in for the link self-inertia the point masses omit
# (link index, distance along link, mass), from LINKS and JAWS
MASSES = [(0, 0.1343, 0.70), (1, 0.1249, 0.9018), (2, 0.0757, 0.466), (2, 0.1324, 0.40775),
          (2, 0.2287, 0.4660), (2, GRASP, BOTTLE)]
LENS = (L1, L2)


def joints_xy(a):
    p0 = (0.0, 0.0)
    p1 = (L1 * math.cos(a[0]), L1 * math.sin(a[0]))
    p2 = (p1[0] + L2 * math.cos(a[1]), p1[1] + L2 * math.sin(a[1]))
    return p0, p1, p2


def point(a, link, d):
    return joints_xy(a)[link][0] + d * math.cos(a[link]), joints_xy(a)[link][1] + d * math.sin(a[link])


def vel_acc(a, w, al, link, d):
    """Velocity and acceleration of a point on `link` at distance d, in absolute link angles."""
    vx = vz = ax = az = 0.0
    for i in range(link + 1):
        r = d if i == link else LENS[i]
        s, c = math.sin(a[i]), math.cos(a[i])
        vx += -r * s * w[i]
        vz += r * c * w[i]
        ax += -r * c * w[i] ** 2 - r * s * al[i]
        az += -r * s * w[i] ** 2 + r * c * al[i]
    return vx, vz, ax, az


def torques(a, w, al):
    """Torque at each joint needed for this motion, gravity included."""
    out = []
    for j in range(3):
        px, pz = joints_xy(a)[j]
        t = 0.0
        for link, d, m in MASSES:
            if link < j:
                continue
            x, z = point(a, link, d)
            _, _, ax, az = vel_acc(a, w, al, link, d)
            t += (x - px) * m * (az + G) - (z - pz) * m * ax
        out.append(t * INERTIA_MARGIN)
    return out


def jac_solve(a, vx, vz, spin):
    """Absolute link rates giving tip velocity (vx, vz) and wrist rate `spin`. Rates are absolute."""
    w2 = spin
    rx = vx + GRASP * math.sin(a[2]) * w2
    rz = vz - GRASP * math.cos(a[2]) * w2
    det = L1 * L2 * (-math.sin(a[0]) * math.cos(a[1]) + math.cos(a[0]) * math.sin(a[1]))
    if abs(det) < 1e-4:
        return None
    w0 = (rx * L2 * math.cos(a[1]) + rz * L2 * math.sin(a[1])) / det
    w1 = (-L1 * math.sin(a[0]) * rz - L1 * math.cos(a[0]) * rx) / det
    return w0, w1, w2


def joint_rates(w):
    """Absolute rates to joint rates: shoulder lift, elbow, wrist flex."""
    return abs(w[0]), abs(w[1] - w[0]), abs(w[2] - w[1])


def limits_ok(a):
    d = [math.degrees(x) for x in a]
    elbow = d[1] - d[0] + 180
    return 5 <= d[0] <= 176 and 3 <= elbow <= 236 and -65 <= d[2] - d[1] <= 65


def tip_clear(a):
    return all(point(a, 2, d)[1] + SHOULDER_Z > 0.06 for d in (0.0, GRASP))


def best(theta_deg, cap, torque_frac, step=10, min_land=0.15):
    """Fastest ramp, over a pose grid, for a throw needing theta_deg of free rotation."""
    result = None
    degs = range(10, 176, step)
    for spin_dps in (400, 500, 600, 700, 800, 900, 1000, 1200):
        spin = math.radians(spin_dps)
        t = math.radians(theta_deg) / spin
        for a1, a2, a3, vx in itertools.product(degs, range(-60, 136, step), range(-30, 136, step), (-0.4, -0.2, 0.0, 0.2, 0.4)):
            a = tuple(math.radians(x) for x in (a1, a2, a3))
            if not limits_ok(a):
                continue
            x, z = point(a, 2, GRASP)
            z += SHOULDER_Z
            if not 0.15 <= x <= 0.5 or z < 0.15:
                continue
            vz = (0.5 * G * t * t - (z - LANDING_COM)) / t
            land = x + vx * t
            if not min_land <= land <= 0.45:
                continue
            w = jac_solve(a, vx, vz, spin)
            if w is None or max(joint_rates(w)) > cap:
                continue
            for T in (0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6):
                al = tuple(x / T for x in w)
                ok = True
                peak = [0.0, 0.0, 0.0]
                for k in range(11):
                    s = k / 10 * T
                    back = T - s
                    ang = tuple(a[i] - w[i] * back + 0.5 * al[i] * back ** 2 for i in range(3))
                    rate = tuple(w[i] - al[i] * back for i in range(3))
                    if not limits_ok(ang) or not tip_clear(ang):
                        ok = False
                        break
                    tq = torques(ang, rate, al)
                    peak = [max(peak[i], abs(tq[i])) for i in range(3)]
                    if any(abs(tq[i]) > torque_frac * TAU[i] for i in range(3)):
                        ok = False
                        break
                if ok:
                    margin = min(TAU[i] / peak[i] - 1 for i in range(3))
                    cand = dict(theta=theta_deg, spin=spin_dps, flight=t, vz=vz, vx=vx, T=T, rel_h=z, x=x, land=land,
                                pose=(a1, a2, a3), rates=[round(r, 2) for r in joint_rates(w)], peak=[round(p, 1) for p in peak], margin=round(margin, 2))
                    key = (max(cand["rates"]), T)
                    if result is None or key < result[0]:
                        result = (key, cand)
                    break
    return result[1] if result else None


if __name__ == "__main__":
    for cap, frac in ((5.0, 0.8), (5.0, 1.0), (8.0, 0.8), (10.0, 0.8)):
        print(f"--- joint speed cap {cap} rad/s, torque allowed {int(frac * 100)}% of peak")
        for theta in (360, 270, 180):
            r = best(theta, cap, frac)
            print(f"{theta} deg:", r if r else "NO FEASIBLE THROW in this grid")
    print("--- finer 5 deg grid, 80% of peak torque, landing at least 0.25 m from the shoulder axis")
    for cap, theta in ((5.0, 180), (5.0, 270), (5.0, 360), (6.0, 360), (7.0, 360), (8.0, 360)):
        r = best(theta, cap, 0.8, step=5, min_land=0.25)
        print(f"cap {cap}, {theta} deg:", r if r else "NO FEASIBLE THROW in this grid")
    print("--- one control tick at release")
    for hz in (25, 200):
        for spin, v in ((500, 2.0), (800, 2.0)):
            print(f"{hz} Hz, {spin} deg/s, {v} m/s: {spin / hz:.1f} deg, {v / hz * 100:.1f} cm")
