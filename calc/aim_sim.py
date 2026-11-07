"""Does aiming at a bearing (joint angle at frame time + pixel offset) behave under video delay?

Load case: a person walking 1.4 m/s across at 2 m and 1.4 m, then stopping. 30 Hz control, 15 Hz detections.
Speed limit 1 rad/s, acceleration limit 2 rad/s^2 (spec). Delay is what the video really has; `assumed` is what the
controller believes. Not modelled: motor lag, shake, face-detector noise beyond the jitter below, packet loss.
"""
import math
import random

DT = 1 / 30
VMAX, AMAX = 1.0, 2.0
HALF_FRAME = math.radians(69.4) / 2


def run(distance, delay, assumed, deadband_deg=2.0, jitter_deg=0.5, seed=1):
    rng = random.Random(seed)
    deadband = math.radians(deadband_deg)
    n_hist = 400
    start_x, walk_s, stop_s = -2.0, 4.0 / 1.4, 6.0
    first = math.atan2(start_x, distance)  # the camera starts on the person: "follow me" begins with them in frame
    pan_hist = [first] * n_hist
    pan, vel, target = first, 0.0, first
    errs, after_stop, sign_changes, last_sign = [], [], 0, 0
    for i in range(int((walk_s + stop_s) / DT)):
        t = i * DT
        x = start_x + 1.4 * min(t, walk_s)
        bearing = math.atan2(x, distance)
        if i % 2 == 0:  # a detection every other tick, of the world `delay` ago, seen through the camera of then
            k = int(round(delay / DT))
            then = t - delay
            seen = math.atan2(start_x + 1.4 * min(max(then, 0), walk_s), distance)
            pixel = seen - pan_hist[-1 - k] + math.radians(rng.gauss(0, jitter_deg))
            if abs(pixel) < HALF_FRAME:  # only a face in frame can be measured
                j = int(round(assumed / DT))
                target = pan_hist[-1 - j] + pixel
        err = target - pan
        want = 0.0 if abs(err) < deadband else math.copysign(min(VMAX, math.sqrt(2 * AMAX * abs(err))), err)
        vel += max(-AMAX * DT, min(AMAX * DT, want - vel))
        pan += vel * DT
        pan_hist.append(pan)
        pan_hist.pop(0)
        e = bearing - pan
        if t > 0.5:
            errs.append(abs(e))
        if t > walk_s + 1.5:
            after_stop.append(abs(e))
            s = (vel > 0.02) - (vel < -0.02)
            if s and s != last_sign:
                sign_changes += 1
                last_sign = s
    return max(errs), max(after_stop), sign_changes


print(f"half frame {math.degrees(HALF_FRAME):.1f} deg; deadband 2 deg; worst trail while walking / worst error 1.5 s "
      "after stopping / velocity reversals after stopping")
for distance in (2.0, 1.4):
    for delay, assumed in ((0.2, 0.2), (0.3, 0.3), (0.5, 0.5), (0.3, 0.2), (0.3, 0.4), (0.5, 0.3)):
        trail, settled, flips = run(distance, delay, assumed)
        print(f"  at {distance} m, delay {delay:.1f} s, assumed {assumed:.1f} s: trail {math.degrees(trail):5.1f} deg, "
              f"settled {math.degrees(settled):4.1f} deg, reversals {flips}")

print("\nsame walker with no deadband and a pixel-error loop would need the gains in calc/follow_loop.py")
