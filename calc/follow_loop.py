"""Can the phone follow a person, and can it recognise them, from where it stands?

Load case for the hold: phone, case and clamp (0.32 kg, assumed), held still at the jaws with the
phone's centre 0.08 m past them on a handle, tool up. Arm model and gains are from the bottle flip
work (flip_feasibility.py, copied here) and the Maker Arm SDK profile.
Not analyzed: motor heat, video shake, link flex, the handle slipping in the jaws, Wi-Fi jitter.

Run: PYTHONDONTWRITEBYTECODE=1 python3 calc/follow_loop.py
Continuous torque ratings (6, 6, 5 N*m) are from reseller listings, not RobStride's datasheet.
"""
import math

import flip_feasibility as ff

PHONE, HANDLE = 0.32, 0.08
RATED = (6.0, 6.0, 5.0)
ZERO = (0.0, 0.0, 0.0)
WALK = 1.4                      # m/s
FACE = 0.16                     # m, face width
LONG_FOV = math.radians(69.4)   # 26 mm equivalent main camera, long side of the frame
SHORT_FOV = math.radians(42.6)  # short side of a 16:9 frame


def hold(name, a):
    t = ff.torques(a, ZERO, ZERO)
    margin = min(r / max(abs(x), 1e-9) for r, x in zip(RATED, t)) - 1
    print(f"  {name}: torque {[round(abs(v), 2) for v in t]} N*m, margin {margin:+.2f}")


ff.MASSES[-1] = (2, ff.GRASP + HANDLE, PHONE)
r = math.radians
print("holding still against continuous ratings")
hold("tool level, upper arm up, forearm 65 deg", (r(90), r(65), 0.0))
hold("tool up, same arm pose", (r(90), r(65), r(90)))
hold("tool tilted 30 deg forward", (r(90), r(65), r(60)))
hold("tool tilted 30 deg back", (r(90), r(65), r(120)))
hold("fully stretched", ZERO)
weight = PHONE * ff.G
print(f"  moment on the handle in the jaws at 30 deg tilt: {weight * HANDLE * math.sin(r(30)):.3f} N*m")

print("\npan with the base, tilt with wrist flex (arm near the pan axis)")
for tilt in (0, 30):
    a = (r(90), r(65), r(90 - tilt))
    iz = sum(m * ff.point(a, link, d)[0] ** 2 for link, d, m in ff.MASSES)
    print(f"  tilt {tilt} deg: phone {ff.point(a, 2, ff.GRASP + HANDLE)[0]:.2f} m from the axis, "
          f"inertia {iz:.3f} kg*m^2, 2 rad/s^2 needs {iz * 2:.2f} N*m (base motor rated 5)")

print("\nhow fast the view must turn for a walker crossing the frame")
for d in (1.4, 2.0, 3.0):
    print(f"  {d:.1f} m from the phone: {WALK / d:.2f} rad/s")

print("\nvideo delay against a simple pixel-error loop (gain below pi / 2 / delay, then a third of that)")
for tau in (0.2, 0.3, 0.5):
    k_max = math.pi / (2 * tau)
    k = k_max / 3
    err = math.degrees(WALK / 2.0 / k)
    print(f"  delay {tau:.1f} s: gain limit {k_max:.1f}/s, using {k:.1f}/s, walker at 2 m trails by {err:.0f} deg")
print(f"  half frame: {math.degrees(LONG_FOV) / 2:.1f} deg across a landscape frame, "
      f"{math.degrees(SHORT_FOV) / 2:.1f} deg across a portrait one")

print("\nface width in pixels, landscape")
for d in (1.5, 3.0, 5.0):
    angle = 2 * math.atan(FACE / 2 / d)
    print(f"  {d:.1f} m: {angle / LONG_FOV * 1280:.0f} px at 720p, {angle / LONG_FOV * 1920:.0f} px at 1080p")
