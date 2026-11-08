"""Station passthrough for Portal's manifest_bridge running off the robot (the Mac stack: `uv run main.py stack`).

    POST /v1/station/supervisor/<route>  ->  station POST /supervisor/<route>, JSON in and out, status codes kept

`?omit_images=1` on preview drops its camera JPEGs (~140 KB): the bridge reads images only from observe, so the
Mac stack asks for lean previews and its state rate is not bound by Wi-Fi. Without it, replies are the station's own.

Only the routes manifest_bridge.py posts are allowed; everything else (reset, teaching, settings, ...) answers 404.
Routes that start motion (cv/start, action, home) also need Manifest's execute_allowed, as the direct plugin does.
The station still enforces its own safety: leases, watchdogs, shield, speed and temperature guards.
"""

PREFIX = "/v1/station/supervisor/"
# route -> station timeout (s), matching the bridge's own client timeouts
ROUTES = {
    "observe": 5.0,
    "preview": 5.0,
    "heartbeat": 5.0,
    "stop": 10.0,
    "cv/frame": 5.0,
    "cv/stop": 10.0,
    "cv/start": 120.0,
    "action": 30.0,
    "home": 90.0,
}
MOTION = {"cv/start", "action", "home"}


def handle(req):
    if not req.path.startswith(PREFIX):
        return None
    route = req.path[len(PREFIX):].strip("/")
    if route not in ROUTES:
        return 404, {"error": f"station_proxy: route not allowed: {route}"}
    if req.method != "POST":
        return 405, {"error": "station_proxy: POST only"}
    if route in MOTION and not req.motion_allowed:
        return 409, {"error": "Manifest has motion disabled (settings.execute_allowed)"}
    # StationError from req.station is answered by the loader with the station's own status code and error.
    reply = req.station("/supervisor/" + route, req.body, timeout=ROUTES[route])
    flag = req.query.get("omit_images")
    if route == "preview" and (flag[0] if isinstance(flag, list) and flag else flag) in ("1", "true"):
        reply = {k: v for k, v in reply.items() if k != "images"}
    return 200, reply
