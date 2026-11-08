# manifest_sim

A fake Manifest station backed by a Genesis sim of the Armstrong rig: two Maker Arm v1 arms at the near edge of a
table, five face-up playing cards, a face-down deck, an overhead camera and two wrist cameras. It speaks the same HTTP
API as the real station (the `station_proxy` plugin's `/supervisor/*` routes plus Manifest's built-in `/v1/*` ones), so
`manifest_bridge.py` and everything behind it runs without hardware.

## Run it

```bash
uv run sim/manifest_sim.py                 # headless, http://127.0.0.1:8191 (the default)
uv run sim/manifest_sim.py --viewer        # also opens Genesis's interactive viewer
uv run sim/manifest_sim.py --port 8191 --backend cpu   # if Metal misbehaves
```

The first start compiles Genesis kernels (about 30 s to 3 min); later starts use the cache. It is ready when
`curl -s http://127.0.0.1:8191/v1/health` answers `{"ok": true, "sim": true}`.

Smoke test (saves the three camera JPEGs to `--out`):

```bash
uv run sim/test_sim.py --out /tmp/sim_images
```

## Run the stack against it

The bridge reads `MANIFEST_STATION_URL` from the process environment at import, before it loads any `.env`, so set
it on the command line or in the parent's environment:

```bash
# Set LIVEKIT_API_KEY and LIVEKIT_API_SECRET in your local environment first.
livekit-server --dev --keys "$LIVEKIT_API_KEY: $LIVEKIT_API_SECRET"

cd thirdparty/portal-makermods
MANIFEST_STATION_URL=http://127.0.0.1:8191 MAKERMODS_MODEL=makers \
LIVEKIT_URL=ws://127.0.0.1:7880 LIVEKIT_API_KEY="$LIVEKIT_API_KEY" LIVEKIT_API_SECRET="$LIVEKIT_API_SECRET" LIVEKIT_ROOM=armstrong-local \
  uv run python src/manifest_bridge.py
```

Explicit environment variables win over `thirdparty/portal-makermods/.env` (it loads without override), so the
LiveKit Cloud settings in there stay unused. The Dream-1 node keeps using the halo for inference
(`DREAM_PROXY_URL=http://amd-halo.local:8100`); only the station is simulated.

## What it emulates

| Route | Behaviour |
|---|---|
| `POST /supervisor/observe` | `observation_id`, `status`, `measured` (positions, velocities, gripper 0..1, 7 motor temps, `commanded_rad`, `commanded_gripper`), `enabled_arms`, `lease`, `problem: null`, `mode`, and `images` (`top`, `left`, `right`: 640x480 JPEG, base64, `age_s`), rendered at 5 Hz |
| `POST /supervisor/preview` | the same, without images |
| `POST /supervisor/cv/start` (and `/v1/cv/start`) | `{"lease_id"}`, which replaces any CV lease |
| `POST /supervisor/cv/frame` (and `/v1/cv/frame`) | writes the targets and grippers. A target more than 0.12 rad from the measured joint returns 409 and ends the lease. Empty targets only keep the lease alive. No frame for 2 s ends the lease |
| `POST /supervisor/cv/stop` (and `/v1/cv/stop`), `/supervisor/stop`, `/supervisor/heartbeat` | as the bridge uses them |
| `POST /supervisor/home` | a slow (0.6 rad/s) joint move to zero, the rest pose, with grippers open. It blocks, then returns `lease.reached_home` |
| `POST /supervisor/action` | 409 "not supported in sim" (no Dream-1 on the station side) |
| `GET /v1/robot`, `/v1/health`, `/v1/plugins` | Manifest's built-ins (`plugins: []`) |

Errors are HTTP 409 with `{"error": "..."}`.

## Simulated vs faked

- **Simulated:** joint-position PD (kp/kv per joint) at 60 Hz physics with gravity, so measured joints lag their
  targets realistically. The kinematics are `dream_ik`'s `maker_arm_ik.urdf` (the joints the station reports), and
  the limits come from `robots.makers.JOINTS`, widened only so that zero is reachable. The two-finger prismatic jaw
  has an 80 mm stroke. Cameras are rendered with Genesis's rasterizer.
- **Faked:**
  - The arm links are primitive cylinders, since no Maker Arm meshes exist locally.
  - Arm links have no collision.
  - Cards are kinematic. Grasping is scripted: a jaw that closes below 0.35 within 45 mm of a card carries it, and
    opening above 0.6 drops it flat on the table.
  - Cards are 1.5 mm thick (instead of 0.3 mm) so the face and back do not z-fight.
  - Motor temperatures are a slow 40-45 °C wave.
  - Dream-1 actions are not supported.

Generated assets (the URDF, card GLBs and textures) go to `sim/assets/generated/` and are rebuilt when deleted.
