"""Smoke test for a running manifest_sim: uv run sim/test_sim.py [--url http://127.0.0.1:8191] [--out DIR]

Saves the three camera JPEGs, drives one joint through a CV lease in small steps, checks a 0.2 rad jump is
refused and that silence ends the lease.
"""
from __future__ import annotations

import argparse
import base64
import json
import pathlib
import time
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8191"


def call(route: str, body: dict | None = None, method: str = "POST") -> tuple[int, dict]:
    data = json.dumps(body or {}).encode() if method == "POST" else None
    req = urllib.request.Request(URL + route, data, {"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def main() -> None:
    global URL
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=URL)
    ap.add_argument("--out", default="sim_images")
    args = ap.parse_args()
    URL = args.url
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    code, obs = call("/supervisor/observe")
    assert code == 200, obs
    cams = [i["camera"] for i in obs["images"]]
    print("observe:", code, "cameras", cams, "ages", [i["age_s"] for i in obs["images"]])
    assert sorted(cams) == ["left", "right", "top"]
    for img in obs["images"]:
        (out / f"{img['camera']}.jpg").write_bytes(base64.b64decode(img["jpeg"]))
    left = obs["measured"]["left"]
    assert len(left["positions_rad"]) == 6 and len(left["motor_temps_c"]) == 7
    print("left arm:", {k: v for k, v in left.items()})
    code, prev = call("/supervisor/preview")
    assert code == 200 and "images" not in prev
    for route in ("/v1/robot", "/v1/health", "/v1/plugins"):
        print(route, call(route, method="GET"))

    # A CV lease: joint1 (pan) of the left arm in 0.05 rad steps up to 0.5 rad.
    code, start = call("/supervisor/cv/start")
    lease = start["lease_id"]
    print("cv/start:", code, lease)
    base = {s: obs["measured"][s]["positions_rad"] for s in ("left", "right")}
    target = list(base["left"])
    for step in range(10):
        target[0] = base["left"][0] + 0.05 * (step + 1)
        for _ in range(6):  # ~0.2 s per step at 30 Hz
            code, r = call("/supervisor/cv/frame", {"lease_id": lease, "targets": {"left": target, "right": base["right"]},
                                                     "grippers": {"left": 1.0, "right": 1.0}})
            assert code == 200, r
            time.sleep(1 / 30)
    time.sleep(0.5)
    call("/supervisor/cv/frame", {"lease_id": lease, "targets": {}, "grippers": {}})
    m = call("/supervisor/preview")[1]["measured"]["left"]["positions_rad"]
    print(f"joint1 target {target[0]:.3f}, measured {m[0]:.3f}")
    assert abs(m[0] - target[0]) < 0.03, "measured did not follow"

    # A 0.2 rad jump is refused and ends the lease.
    jump = list(m)
    jump[0] += 0.2
    code, r = call("/supervisor/cv/frame", {"lease_id": lease, "targets": {"left": jump}, "grippers": {}})
    print("0.2 rad jump:", code, r)
    assert code == 409
    code, r = call("/supervisor/cv/frame", {"lease_id": lease, "targets": {}, "grippers": {}})
    print("frame after refusal:", code, r)
    assert code == 409

    # Silence ends a lease.
    lease = call("/supervisor/cv/start")[1]["lease_id"]
    call("/supervisor/cv/frame", {"lease_id": lease, "targets": {}, "grippers": {}})
    time.sleep(2.6)
    code, r = call("/supervisor/cv/frame", {"lease_id": lease, "targets": {}, "grippers": {}})
    print("frame after 2.6 s silence:", code, r)
    assert code == 409

    # Home: back to zero.
    code, r = call("/supervisor/home", {"observation_id": "x", "grippers_empty": True})
    print("home:", code, r)
    print("ALL OK")


if __name__ == "__main__":
    main()
