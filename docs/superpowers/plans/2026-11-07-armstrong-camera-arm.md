# Armstrong Camera Arm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Maker Arm takes a phone off the table with Dream-1, then films people by voice: it looks at them by name, follows them, looks where they point, runs a script, and retakes a shot.

**Architecture:** LiveKit's `uv run robot` stays unchanged and owns the arms. New processes in this repo are a camera operator (Portal operator, aims the phone arm from the phone's video), a Dream-1 wrapper (moves one arm only), a voice director (LiveKit agent, calls both over RPC), and a static phone page (camera, mic, speaker, recording). Decisions live in plain classes tested with fakes, so three of the four tracks need no robot time.

**Tech Stack:** Python 3.12, uv, `portal-makermods` (submodule), `livekit-portal` 0.3.0, `livekit-agents` 1.8.11, `livekit` 1.2.0, OpenCV 4.13 (YuNet, SFace), MediaPipe 1.2, `livekit-client` 2.23.0 in the browser, pytest.

**Spec:** `docs/superpowers/specs/2026-11-07-armstrong-camera-arm-design.md`. Hold and tracking numbers come from `calc/follow_loop.py`, aiming numbers from `calc/aim_sim.py`.

**Assumed, not confirmed:** at least three people, and the arm is available now because teammates are already testing on it. With fewer people, follow the priority order under Timeline. Tasks marked **AT THE ARM** need booked robot time.

**Open: Manifest.** A teammate's tool on `10.103.1.11` is being used to pick up a white box. It hasn't been read, because that machine isn't reachable from this laptop. Before Task 12, find out: does it use Dream-1, does it use Portal, and does it hold the CAN adapter? One process owns each adapter, so it must stop before `uv run robot` starts. If it already picks things up well, its setup and footage can shorten Task 12, but Dream-1 still has to do the visible pick-up in the film.

## Timeline

| When (PT) | Phone and voice | Camera | Arm |
|---|---|---|---|
| Sat now to 2 PM | Task 1, then 2 and 3 | Tasks 5, 6, 7 | Tasks 4, 11, 12 |
| Sat 2 to 6 PM | Tasks 9, 10; LiveKit workshop at 4:00 | Task 8 | Finish Task 12, first fine-tune; Dream-1 workshop at 3:00; second fine-tune by 5:30; pick-up gate at 6:00 |
| Sat 6 to 10 PM | Tasks 13, 14 | Tasks 13, 14 | Tasks 13, 14; last fine-tune by 10:00 |
| Sun 10 AM to 12:30 PM | Task 15, fixes from Task 14 | Same | Same; filming starts at 10:00 with whatever works |
| Sun 12:30 to 2:30 PM | Edit | Support | Support; features stop at 12:30, upload by 2:30 |

Task 1 comes first because everything imports from it. It takes about 20 minutes, and it should be pushed before anyone starts Tasks 2-10.

**If time runs short, keep this order:** look-at and voice, then Dream-1's pick-up, then retake, then following, then script. Dream-1 and a LiveKit voice agent are what the track asks for, so neither can be dropped.

**To buy or borrow:** a phone clamp with a 1/4-20 thread, a rubber mat, painter's tape, cord for a tether, a kitchen scale, and a dummy the same weight and size as the phone. An IR thermometer helps with Task 12.

## Global Constraints

- Demo submission is due Sunday, Nov 8, at 3:00 PM PT. Upload by 2:30 PM.
- `thirdparty/portal-makermods` stays unedited. New code goes in `src/armstrong/`.
- **Every action carries all 14 fields.** Portal fills a missing field with that operator's last sent value, or 0.0 if it never sent one.
- Keep LiveKit's joint limits and step limiter. One process owns each CAN adapter. Close MakerMods Lab first. Set `MAKERMODS_MODEL=makers` on every peer.
- Run hardware and inference off the event loop, using `HardwareThread`. Control is explicit: nothing takes control unless told to.
- The right arm holds the phone. The conversation stays out of the robot's room.
- Filming limits, enforced in code: joint1 and joint4 only, 1 rad/s, 2 rad/s^2, tilt within 30 degrees of the camera pose. Carry: at most 0.3 rad/s.
- Never hold the arm fully stretched with the phone: the margin there is -0.60. The camera pose margin is +1.94 for 0.32 kg, with heat, shake and slip untested.
- Keep people outside a taped line at least 1 m from the arm while it is powered. Someone stays at the emergency stop during every powered test and does nothing else. Reach in only when parked and that person agrees.
- Assume parking drops the phone. Tether the rig, use a mat, and test everything with the dummy first.
- Get MakerMods' OK before changing `METAL_MAX_STEP_RAD`. 1 rad/s needs at least 0.034.
- Film only people who agreed. Face data is taken only when someone is introduced, stays on the laptop, and is deleted after the event. No LiveKit secret reaches the phone. Secrets stay in git-ignored `.env`, and `.env*` files are never printed or committed.
- Never present a pre-recorded path as a live reaction. Label sped-up footage, hand-loaded rigs and outside shots. Only claim what ran.
- Paying for a fine-tune needs approval from whoever's credits or card it uses. Commit to `camera-arm-design`, and push only when the team agrees.

## Review Focus

1. Wi-Fi drops or video stalls during a take: the phone keeps recording, the arm holds still, and the director reports it afterward (Tasks 3, 8, 10).
2. Someone else walks through the shot: the camera stays with its person and never jumps to the stranger (Task 6).
3. Control changes hands in the middle of a move: nothing is sent without control, and when control returns the arm continues from where it is (Task 8).
4. A stale tool call or "continue" arrives while the arm holds the phone: Dream-1 can't move that arm (Tasks 4, 10).
5. The named person isn't there or was never introduced: the search ends, the arm holds, and the director says so (Task 8).

---

### Task 1: Project setup and shared names

**Files:**
- Create: `pyproject.toml`, `src/armstrong/__init__.py`, `src/armstrong/names.py`, `tests/test_setup.py`, `docs/bringup-log.md`
- Modify: `setup.sh:7`, `.gitignore`

**Interfaces:**
- Produces: `armstrong.names` with every constant below. All later tasks import from it.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "armstrong"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = ["portal-makermods", "livekit-agents~=1.8", "livekit-plugins-ai-coustics~=0.3", "mediapipe>=1.2", "qrcode[pil]>=7"]

[project.scripts]
camera-op = "armstrong.camera_op:run"
director = "armstrong.director:run"
dream-one-arm = "armstrong.dream_one_arm:run"
phone-qr = "armstrong.phone_qr:run"

[tool.uv.sources]
portal-makermods = { path = "thirdparty/portal-makermods", editable = true }

[tool.uv]
# Copied from portal-makermods: overrides don't carry over from a dependency, and every OpenCV wheel owns cv2.
override-dependencies = ["opencv-python; python_version < '0'", "opencv-contrib-python; python_version < '0'"]

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]

[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 2: Change the last line of `setup.sh` to `uv sync`, and add `.venv/`, `__pycache__/`, `.pytest_cache/` and `data/` to `.gitignore`.** The plain install left `portal.yaml` out of reach. Tell the teammate who wrote `setup.sh`.

- [ ] **Step 3: Write `src/armstrong/names.py`**

```python
import math

CAMERA_IDENTITY, PHONE_IDENTITY = "camera-op", "phone"
PHONE_SIDE, OTHER_SIDE = "right", "left"
VOICE_ROOM = "portal-voice"
SCRIPT_TOPIC = "armstrong.script"
CONTEXT_PATH, FACES_PATH = "data/context.json", "data/faces.json"

CAMERA_RPCS = ("status", "take_control", "release", "carry", "hold", "look_at", "follow", "look_pointed",
               "look_around", "go_to", "meet", "mark_start", "end_take", "remember_spot", "set_phone_held")
PHONE_RECORD_START_RPC, PHONE_RECORD_STOP_RPC = "phone.record_start", "phone.record_stop"
DREAM_SET_FREE_ARM_RPC = "dream.set_free_arm"

FILM_SPEED_RAD_S, FILM_ACCEL_RAD_S2 = 1.0, 2.0
CARRY_SPEED_RAD_S = 0.3
SWEEP_SPEED_RAD_S, SWEEP_LIMIT_RAD = 0.3, math.pi / 2
PAN_LIMIT_RAD, TILT_LIMIT_RAD = math.pi / 2, math.radians(30)
DEADBAND_RAD = math.radians(2)
GRIP_SQUEEZE_MM = 5.0
HFOV_DEG = 69.4
CONFIRM_TIMEOUT_S = 60.0
VIDEO_STALE_S, OBS_STALE_S = 1.0, 0.5
# First guess from calc/flip_feasibility.py (upper arm 90, forearm 65, tool 90 degrees). Signs untested; Task 13 replaces it.
CAMERA_POSE_DEG = (0.0, -90.0, 155.0, 25.0, 0.0, 0.0)
```

The RPC method on the wire is `"camera." + name`.

- [ ] **Step 4: Write the test** in `tests/test_setup.py`

```python
def test_portal_config_is_found():
    from utils.common import CONFIG_PATH
    assert CONFIG_PATH.exists()

def test_opencv_has_face_models_and_agents_import():
    import cv2, voice_agent
    assert hasattr(cv2, "FaceDetectorYN") and hasattr(cv2, "FaceRecognizerSF")
    assert voice_agent.STOP_WORDS.search("wait")
```

- [ ] **Step 5: Run** `./setup.sh && uv run --group dev pytest tests/test_setup.py -v`. Expected: PASS. Then run `uv run robot --list-adapters`. Expected: it lists adapters, or none, without an import error.

- [ ] **Step 6: Create `docs/bringup-log.md`** with the heading `# Bring-up log`. Measured values and answers from the venue go here.

- [ ] **Step 7: Commit** `"Set up the armstrong package and shared names"`, including `uv.lock`, then ask the team to approve a push.

### Task 2: Phone spike: stream and record together

Do this before the rest of the phone page. It answers the riskiest question that needs no arm. Time-box it to 30 minutes.

**Files:**
- Create: `phone/index.html`, `phone/app.js`, `phone/watch.html`, `src/armstrong/phone_qr.py`
- Test: `tests/test_phone_qr.py`

**Interfaces:**
- Consumes: `utils.common.mint_token(identity, room, ttl_hours)`, `armstrong.names`
- Produces: `phone_link(page_url: str, livekit_url: str, token: str) -> str`, and the page URL form `<page>#url=<wss>&token=<jwt>`

- [ ] **Step 1: Write the failing test**

```python
from urllib.parse import urlsplit
from armstrong.phone_qr import phone_link

def test_token_stays_out_of_what_the_server_sees():
    link = phone_link("https://page.example/", "wss://x.livekit.cloud", "abc.def")
    parts = urlsplit(link)
    assert parts.query == "" and "abc.def" in parts.fragment and "abc.def" not in parts.path
```

- [ ] **Step 2: Run** `uv run --group dev pytest tests/test_phone_qr.py -v`. Expected: FAIL, module missing.

- [ ] **Step 3: Implement `phone_link` and `run()`.** `run()` mints a token for `PHONE_IDENTITY` in `VOICE_ROOM` with `ttl_hours=12`, reads the page address from `ARMSTRONG_PAGE_URL`, and writes a QR PNG to `data/phone-qr.png`. It never prints the token or the link. `--watch` mints for identity `watch` instead and links to `watch.html`.

- [ ] **Step 4: Run** the test. Expected: PASS.

- [ ] **Step 5: Build the spike page.** `phone/app.js` loads `livekit-client@2.23.0` from jsDelivr, reads `url` and `token` from `location.hash`, and has a Start button (browsers need a tap for sound). It creates local tracks with `facingMode: "environment"`, 1920x1080 at 30 fps, and `echoCancellation: true`, then publishes them. It also runs `MediaRecorder` on `new MediaStream([videoTrack, audioTrack])` using the first supported type of `video/mp4` and `video/webm`. `phone/watch.html` joins with the `watch` identity and shows the phone's video beside a large millisecond clock.

- [ ] **Step 6: Host the page.** Browsers require HTTPS for the camera. Run `vercel --prod --yes` from `phone/` after the team agrees to a public URL. The page holds no secrets.

- [ ] **Step 7: Test on the team's actual phone.** Record for 2 minutes while streaming, then play the file back. Expected: video and sound are intact, and the live stream never froze.

- [ ] **Step 8: Measure video delay.** Film the watch page's clock with the phone and take a laptop screenshot. Delay is the clock minus the clock inside the video. Take five readings on venue Wi-Fi and record the median in `docs/bringup-log.md`.

- [ ] **Step 9: Decide and record.** The phone can't do both: use LiveKit Egress or a small native app. Delay above 0.4 s: try a LiveKit server on the same network, and slow the follow. `calc/aim_sim.py` loses a walker at 1.4 m with 0.5 s of delay, but not at 2 m.

- [ ] **Step 10: Commit** `"Add phone spike and QR link"`.

### Task 3: Phone page

**Files:**
- Modify: `phone/index.html`, `phone/app.js`

**Interfaces:**
- Consumes: the Task 2 URL form and `armstrong.names`
- Produces, on `room.registerRpcMethod`:
  - `phone.record_start` with `{"name": "shot1_take2"}`, answering `{"ok": true}`, or an RPC error if already recording
  - `phone.record_stop` with `{}`, answering `{"name": str, "bytes": int, "seconds": float}`
  - Data on topic `armstrong.script`, reliable, UTF-8 text of the whole script

Browser behavior is verified on the phone, because nothing here runs without a camera.

- [ ] **Step 1: Add recording by RPC.** `MediaRecorder.start(1000)` collects chunks. On stop, join them and save the Blob in IndexedDB under its take name. Show a large red REC state while recording.

- [ ] **Step 2: Add the takes list.** It shows name, length and size, with a Share button (`navigator.share` with files) and a download link. Saved takes survive a page reload.

- [ ] **Step 3: Add the script box.** Saving publishes the text on `armstrong.script` and keeps a draft in `localStorage`, wrapped in try/catch. Republish on every reconnect.

- [ ] **Step 4: Add the rest.** Keep a wake lock and reacquire it on `visibilitychange`. Play the agent's audio with `track.attach()`. Show "turn sideways" in portrait, and a connection indicator.

- [ ] **Step 5: Test each one on the phone.**
  - Fake both RPCs from a small laptop script. Expected: the file appears in the list and plays.
  - Reload the page. Expected: takes are still listed.
  - **Turn on airplane mode for 20 seconds during a recording, then turn it off, then stop.** Expected: one file covers the whole time, and the page reconnects without a tap.
  - Leave the page open for 10 minutes. Expected: the screen stays on.

- [ ] **Step 6: Commit** `"Add phone page: recording, takes and script"`.

### Task 4: One-arm Dream-1

**Files:**
- Create: `src/armstrong/latch.py`, `src/armstrong/dream_one_arm.py`
- Test: `tests/test_latch.py`, `tests/test_dream_one_arm.py`

**Interfaces:**
- Consumes: `utils.metal.arm_fields`, `policies.dream_1_tasks.run`
- Produces:
  - `hold_fields(state: dict[str, float], side: str, squeeze: bool = False) -> dict[str, float]`
  - `merge_action(moving: dict[str, float], held: dict[str, float]) -> dict[str, float]`, raising `ValueError` unless all 14 fields are present
  - `class OneArmOperator` wrapping `livekit.portal.Operator`, with `free_side: str | None`
  - `install() -> None`, `run() -> None`
  - RPC `dream.set_free_arm` with `{"side": "right" | "left" | null}`

Dream-1's loop reaches the arms only through `op.send_action`, so that is the single place to intercept. `policies.dream_1_tasks.run` looks up `Operator` as a module global, so `install()` replaces it. `free_side` starts from `ARMSTRONG_DREAM_FREE_ARM`, defaulting to none, so a restart can't move anything.

- [ ] **Step 1: Write the failing tests**

```python
STATE = {f"{s}_joint{i}.pos": 0.5 for s in ("left", "right") for i in range(1, 7)} | {"left_gripper.pos": 30.0, "right_gripper.pos": 40.0}
DREAM = {k: v + 0.2 for k, v in STATE.items()}

def make(free="right"):
    fake = FakeOperator()                 # records send_action; exposes the callbacks it was given
    op = OneArmOperator(cfg=None, inner=fake, free_side=free)
    op.on_observation(lambda obs: None)
    op.on_active_operator_changed(lambda who: None)
    return op, fake

def test_held_arm_keeps_its_measured_values_and_free_arm_moves():
    op, fake = make("right")
    fake.observe(STATE)
    op.send_action(DREAM, in_reply_to_ts_us=1)
    sent = fake.sent[-1]
    assert len(sent) == 14
    assert sent["left_joint3.pos"] == 0.5 and sent["left_gripper.pos"] == 30.0
    assert sent["right_joint3.pos"] == DREAM["right_joint3.pos"]

def test_latch_is_retaken_when_control_changes():
    op, fake = make("right")
    fake.observe(STATE); op.send_action(DREAM, in_reply_to_ts_us=1)
    moved = STATE | {"left_joint1.pos": 0.9}
    fake.observe(moved); fake.control_changed("policy-dream-1-tasks")
    op.send_action(DREAM, in_reply_to_ts_us=2)
    assert fake.sent[-1]["left_joint1.pos"] == 0.9

def test_free_arm_none_freezes_every_field():
    op, fake = make(None)
    fake.observe(STATE); op.send_action(DREAM, in_reply_to_ts_us=1)
    assert all(abs(fake.sent[-1][k] - STATE[k]) < 1e-6 for k in ("right_joint1.pos", "left_joint1.pos"))

def test_held_phone_arm_keeps_squeezing():
    op, fake = make("left")
    fake.observe(STATE); op.send_action(DREAM, in_reply_to_ts_us=1)
    assert fake.sent[-1]["right_gripper.pos"] == 35.0   # 40 measured, GRIP_SQUEEZE_MM below

def test_nothing_is_sent_before_any_state():
    op, fake = make("right")
    op.send_action(DREAM, in_reply_to_ts_us=1)
    assert fake.sent == []

def test_install_replaces_the_operator_dream_uses():
    import policies.dream_1_tasks.run as loop
    install()
    assert loop.Operator is OneArmOperator
```

- [ ] **Step 2: Run** `uv run --group dev pytest tests/test_dream_one_arm.py tests/test_latch.py -v`. Expected: FAIL, modules missing.

- [ ] **Step 3: Implement.** `OneArmOperator.__init__(self, cfg, inner=None, free_side=<from env>)` delegates everything else through `__getattr__`, and registers the RPC on the inner operator. `hold_fields` with `squeeze=True` sets the gripper to `max(0, measured - GRIP_SQUEEZE_MM)`. The phone arm is held with `squeeze=True`. `run()` calls `install()`, then `policies.dream_1_tasks.run.run()`.

- [ ] **Step 4: Run** the tests. Expected: PASS.

- [ ] **Step 5: Commit** `"Add one-arm Dream-1 wrapper"`.

### Task 5: Aiming

**Files:**
- Create: `src/armstrong/aim.py`
- Test: `tests/test_aim.py`

**Interfaces:**
- Consumes: `armstrong.names`
- Produces:
  - `pixel_to_angles(x: float, y: float, width: int, height: int, hfov_rad: float) -> tuple[float, float]`, positive right and down, using `f = (width / 2) / tan(hfov / 2)` and `atan((x - cx) / f)`
  - `class JointHistory` with `add(t: float, pan: float, tilt: float)` and `at(t: float) -> tuple[float, float]`
  - `class PanTiltAim(pan: float, tilt: float, tilt_center: float, speed_scale: float = 1.0)` with `set_target(pan, tilt)`, `step(dt) -> tuple[float, float]`, and `at_target -> bool`. `speed_scale` multiplies the speed and acceleration limits and must be between 0 and 1, so first tests run slow.

The control law is the one simulated in `calc/aim_sim.py`, per axis: `want = 0` inside `DEADBAND_RAD`, else `sign(e) * min(FILM_SPEED_RAD_S, sqrt(2 * FILM_ACCEL_RAD_S2 * |e|))`; then `v += clamp(want - v, ±FILM_ACCEL_RAD_S2 * dt)` and `pos += v * dt`. Targets are clamped to `PAN_LIMIT_RAD` around pan 0, and `TILT_LIMIT_RAD` around `tilt_center`.

- [ ] **Step 1: Write the failing tests.** `simulate(distance, delay, assumed)` ports `calc/aim_sim.py`: a walker at 1.4 m/s from x = -2 m to +2 m, then stopped for 6 s. The camera starts on the person, with detections at 15 Hz and control at 30 Hz. It returns worst trail, worst error 1.5 s after stopping, and velocity reversals after stopping, with angles in degrees.

```python
@pytest.mark.parametrize("distance,delay,assumed,trail,settled,flips", [
    (2.0, 0.3, 0.3, 20, 2, 2),    # simulated 17.5, 0.7, 1
    (1.4, 0.3, 0.3, 30, 2, 2),    # simulated 27.0, 0.8, 1
    (2.0, 0.5, 0.5, 28, 2, 2),    # simulated 25.0, 1.1, 1
    (2.0, 0.5, 0.3, 25, 6, 3),    # delay misjudged by 0.2 s: simulated 19.9, 4.2, 2
])
def test_follows_a_walker(distance, delay, assumed, trail, settled, flips):
    worst, after, reversals = simulate(distance, delay, assumed)
    assert worst < trail and after < settled and reversals <= flips

def test_speed_and_acceleration_limits_hold():
    aim = PanTiltAim(0, 0, 0); aim.set_target(1.5, 0)
    last_v, last_p = 0.0, 0.0
    for _ in range(300):
        p, _ = aim.step(1 / 30)
        v = (p - last_p) * 30
        assert abs(v) <= 1.0 + 1e-6 and abs(v - last_v) <= 2.0 / 30 + 1e-6
        last_v, last_p = v, p

def test_speed_scale_slows_it_and_cannot_speed_it_up():
    aim = PanTiltAim(0, 0, 0, speed_scale=0.3); aim.set_target(1.5, 0)
    last = 0.0
    for _ in range(300):
        p, _ = aim.step(1 / 30)
        assert abs(p - last) * 30 <= 0.3 + 1e-6
        last = p
    with pytest.raises(ValueError): PanTiltAim(0, 0, 0, speed_scale=1.5)

def test_targets_stay_inside_the_camera_box():
    aim = PanTiltAim(0, 0.4, 0.4); aim.set_target(3.0, 2.0)
    for _ in range(600): pan, tilt = aim.step(1 / 30)
    assert pan <= math.pi / 2 + 1e-3 and abs(tilt - 0.4) <= math.radians(30) + 1e-3

def test_small_errors_do_not_move_it():
    aim = PanTiltAim(0, 0, 0); aim.set_target(math.radians(1), 0)
    assert aim.step(1 / 30)[0] == 0

def test_pixel_at_frame_edge_is_half_the_field_of_view():
    x, _ = pixel_to_angles(1280, 360, 1280, 720, math.radians(69.4))
    assert x == pytest.approx(math.radians(34.7), abs=1e-3)
```

- [ ] **Step 2: Run** `uv run --group dev pytest tests/test_aim.py -v`. Expected: FAIL, module missing.

- [ ] **Step 3: Implement** the signatures above.

- [ ] **Step 4: Run** the tests. Expected: PASS.

- [ ] **Step 5: Commit** `"Add pan-tilt aiming"`.

### Task 6: Faces

**Files:**
- Create: `src/armstrong/faces.py`
- Test: `tests/test_faces.py`

**Interfaces:**
- Consumes: `armstrong.names`
- Produces:
  - `@dataclass SeenFace: box: tuple[float, float, float, float]; embedding: np.ndarray | None; name: str | None`, where box is x, y, w, h in pixels
  - `class FaceEngine` with `detect_and_embed(bgr) -> list[SeenFace]`, wrapping `cv2.FaceDetectorYN` and `cv2.FaceRecognizerSF`, with models fetched once to `~/.cache/armstrong/`: `face_detection_yunet_2023mar.onnx` and `face_recognition_sface_2021dec.onnx` from `opencv/opencv_zoo`
  - `class FaceBook` with `enrol(name, embeddings)`, `identify(embedding) -> str | None`, `names() -> list[str]`, `save(path)`, `load(path)`
  - `class Tracker(name: str, frame_width: int)` with `update(faces: list[SeenFace], now: float) -> SeenFace | None` and `lost_for(now) -> float`

`identify` requires cosine similarity of at least 0.363 (OpenCV's published SFace threshold) and at least 0.05 above the next person. `Tracker` follows the named face if it is recognized. Otherwise it follows the nearest face within 25% of the frame width of its last position. Faces are recognized only when at least 60 px wide (`calc/follow_loop.py`: 56 px at 3 m at 720p), and smaller ones are tracked by position only.

- [ ] **Step 1: Write the failing tests,** using synthetic unit embeddings and no models.

```python
def test_identifies_the_closest_person_and_rejects_strangers(): ...
    # enrol June and Arjun with orthogonal vectors; June's vector returns "June"; a third orthogonal vector returns None
def test_two_people_too_close_to_call_returns_none(): ...
def test_book_only_grows_through_enrol():
    book = FaceBook(); book.identify(unit(3))
    assert book.names() == []
def test_save_and_load_round_trip(tmp_path): ...
def test_tracker_does_not_jump_to_another_face():
    t = Tracker("June", 1280)
    t.update([face(x=200, name="June")], now=0.0)
    assert t.update([face(x=1000, name=None)], now=0.1) is None
    assert t.lost_for(0.6) == pytest.approx(0.5)
def test_tracker_follows_small_unnamed_face_by_position():
    t = Tracker("June", 1280)
    t.update([face(x=200, name="June")], now=0.0)
    assert t.update([face(x=260, name=None)], now=0.1) is not None
def test_named_stranger_is_never_followed():
    t = Tracker("June", 1280)
    t.update([face(x=200, name="June")], now=0.0)
    assert t.update([face(x=230, name="Arjun")], now=0.1) is None
```

- [ ] **Step 2: Run** `uv run --group dev pytest tests/test_faces.py -v`. Expected: FAIL, module missing.

- [ ] **Step 3: Implement** the signatures above.

- [ ] **Step 4: Run** the tests. Expected: PASS.

- [ ] **Step 5: Check the real models** with three teammates who agree, on a laptop webcam. Enrol each at about 1 m. Count correct, wrong and unknown over 20 frames each at 1.5 m and 3 m. Record the counts. **Wrong names above 1 in 20:** fall back to where each person was introduced and last seen, as the spec says.

- [ ] **Step 6: Commit** `"Add face recognition and tracking"`.

### Task 7: Pointing

**Files:**
- Create: `src/armstrong/pointing.py`
- Test: `tests/test_pointing.py`

**Interfaces:**
- Consumes: `armstrong.names`, `hand_teleop.model_path`
- Produces:
  - `pointing_direction(landmarks: np.ndarray) -> int | None`, taking MediaPipe's 21 image points as an array of shape (21, 2), returning +1 for image right and -1 for image left
  - `class PointSweep(start_pan: float, direction: int)` with `step(dt: float, found: bool, stop: bool) -> tuple[float, str | None]`, whose reason is `"found"`, `"stopped"` or `"limit"`
  - `class HandSpotter` with `detect(rgb, ms: int) -> list[np.ndarray]`, using MediaPipe's HandLandmarker in VIDEO mode

Port the finger test from `finger_state` in `~/Developer/arm-control/point_pick.py`: a finger is extended if tip-to-wrist is more than 1.1 times the middle joint-to-wrist, and pointing means index extended with middle and ring not. The ray runs from landmark 5 to 8. Return `None` if the ray's image length is under half the wrist-to-landmark-9 distance (pointing at the lens), or if `|dx| < 0.5 * |dy|` (pointing up or down).

- [ ] **Step 1: Write the failing tests**

```python
def test_index_out_to_the_right_points_right(): assert pointing_direction(hand(dx=+1)) == 1
def test_index_out_to_the_left_points_left(): assert pointing_direction(hand(dx=-1)) == -1
def test_open_palm_is_not_pointing(): assert pointing_direction(open_hand()) is None
def test_pointing_at_the_lens_gives_no_direction(): assert pointing_direction(hand(dx=+1, ray_scale=0.1)) is None
def test_pointing_at_the_ceiling_gives_no_direction(): assert pointing_direction(hand(dx=0, dy=-1)) is None
def test_sweep_runs_at_its_speed_and_stops_at_90_degrees():
    s = PointSweep(0.0, +1); pan, why = 0.0, None
    for i in range(1000):
        pan, why = s.step(1 / 30, found=False, stop=False)
        if why: break
    assert why == "limit" and pan == pytest.approx(math.pi / 2, abs=0.02) and i / 30 == pytest.approx(math.pi / 2 / 0.3, abs=0.2)
def test_sweep_stops_when_told_or_when_found():
    assert PointSweep(0.0, -1).step(1 / 30, found=True, stop=False)[1] == "found"
    assert PointSweep(0.0, -1).step(1 / 30, found=False, stop=True)[1] == "stopped"
```

- [ ] **Step 2: Run** `uv run --group dev pytest tests/test_pointing.py -v`. Expected: FAIL, module missing.

- [ ] **Step 3: Implement** the signatures above.

- [ ] **Step 4: Run** the tests. Expected: PASS.

- [ ] **Step 5: Commit** `"Add pointing direction and sweep"`.

### Task 8: Camera operator

**Files:**
- Create: `src/armstrong/brain.py`, `src/armstrong/camera_op.py`
- Test: `tests/test_brain.py`

**Interfaces:**
- Consumes: `hold_fields`, `merge_action` (Task 4); `PanTiltAim`, `JointHistory`, `pixel_to_angles` (Task 5); `FaceBook`, `Tracker`, `SeenFace`, `FaceEngine` (Task 6); `PointSweep`, `pointing_direction`, `HandSpotter` (Task 7)
- Produces:
  - `@dataclass Vision: taken_at: float; width: int; height: int; faces: list[SeenFace]; hands: list[np.ndarray]`
  - `class CameraBrain(book: FaceBook, delay_s: float, pan_sign: int, tilt_sign: int, speed_scale: float = 1.0)`:
    - `see(vision: Vision)`, `tick(state: dict[str, float], mine: bool, now: float) -> dict[str, float] | None`
    - Commands, each answering a JSON-ready dict with `"ok"`, and `"why"` when false: `hold()`, `carry()`, `look_at(name)`, `follow(name)`, `look_pointed()`, `look_around()`, `go_to(pan=None, tilt=None)`, `meet(name)`, `mark_start()`, `end_take()`, `remember_spot(name)`, `set_phone_held(held)`, `status()`. With no arguments, `go_to` returns to the camera pose. `look_at` accepts a person or a remembered spot.
    - `status()` keys: `mode, mine, phone_held, grip_mm, joints, pan, tilt, arrived, event, event_id, video_age_s, seen`. `event_id` counts up, so a repeated event still counts as new.
  - The program `uv run camera-op [--offline --source <index|file>]`

`joint1` is pan and `joint4` is tilt. A target bearing is the joint angle at the frame's time plus the pixel offset: `JointHistory.at(now - delay_s) + sign * pixel_angle`. The face centre goes 35% down the frame, not 50%, to leave headroom. Modes: `hold`, `carry`, `look`, `follow`, `sweep_point`, `search`, `go_to`.

**Carry** runs two legs at `CARRY_SPEED_RAD_S`: first joint2 and joint3 to the camera pose, lifting the rig clear of the table, then joints 1, 4, 5 and 6. While `phone_held`, the phone arm's gripper target stays at `measured - GRIP_SQUEEZE_MM`, latched when control is taken.

**Search** goes to the last-seen bearing. If the person isn't found, it sweeps pan across the camera box at `SWEEP_SPEED_RAD_S`, then ends with `event = "not_found:<name>"` and holds.

- [ ] **Step 1: Write the failing tests,** with `state()` and `vision()` helpers.

```python
def test_every_action_has_14_fields_and_other_arm_stays_latched(): ...
def test_filming_moves_only_joint1_and_joint4():
    # follow a face moving across the frame for 5 s; assert right joints 2, 3, 5, 6 and the gripper never change
def test_no_control_sends_nothing(): assert brain.tick(state(), mine=False, now=0) is None
def test_regained_control_starts_from_present_state():
    # lose control mid-move while the arm is elsewhere; first action on return equals present state within 1e-3
def test_stale_video_holds_and_reports():
    # follow, then no see() for VIDEO_STALE_S + 0.1: pan stops, status()["event"] == "video_stale"
def test_stale_video_recovers_when_frames_return(): ...
def test_look_at_unknown_person_refused(): assert brain.look_at("Nobody")["ok"] is False
def test_look_at_goes_to_last_seen_bearing(): ...
def test_search_ends_and_reports_not_found():
    # no faces at all: within the sweep time, event == "not_found:June", mode == "hold"
def test_meet_needs_a_face_big_enough():
    # no face or width 40: ok False with why; width 80: ok True, name in book.names()
def test_meet_picks_the_largest_face_only(): ...
def test_look_pointed_without_a_hand_refuses():
    r = brain.look_pointed(); assert r["ok"] is False and "hand" in r["why"]
def test_look_pointed_stops_at_a_remembered_spot(): ...
def test_carry_refused_unless_phone_held(): ...
def test_carry_lifts_before_turning_the_wrist():
    # joint4 stays fixed until joints 2 and 3 arrive; no joint exceeds 0.3 rad/s; ends with arrived True
def test_held_phone_grip_target_stays_below_measured(): ...
def test_mark_start_and_end_take_log_the_path():
    # mark_start returns pan and tilt; after moving, end_take returns the (t, pan, tilt) list
def test_go_to_returns_to_a_start_pose_within_limits(): ...
```

Write each assertion out in full. The comments state what it must check.

- [ ] **Step 2: Run** `uv run --group dev pytest tests/test_brain.py -v`. Expected: FAIL, module missing.

- [ ] **Step 3: Implement `CameraBrain` in `brain.py`,** with no LiveKit imports.

- [ ] **Step 4: Run** the tests. Expected: PASS.

- [ ] **Step 5: Implement `camera_op.py`.**
  - Portal side: follow `hand_teleop.main`: `OperatorConfig.from_yaml_file(CONFIG_PATH, room)`, identity `CAMERA_IDENTITY`, `op.send_action(action, in_reply_to_ts_us=obs.timestamp_us)` from a `pace(fps)` loop, treating observations older than `OBS_STALE_S` as none.
  - RPC: `op.register_rpc_method("camera." + name, handler)` with the JSON and `RpcError.Error(code=1500, ...)` pattern from `TaskControl.register_rpcs`. `take_control` and `release` call `op.set_active_operator`. Handlers answer at once, and moves report through `status()`.
  - Video side: a separate `rtc.Room` joining `VOICE_ROOM` with a token using `api.VideoGrants(room_join=True, room=..., can_subscribe=True, can_publish=False, hidden=True)`. Subscribe only to `PHONE_IDENTITY`'s video through `rtc.VideoStream(track, format=rtc.VideoBufferType.RGB24)`.
  - Vision: detect on a `HardwareThread("vision")`, newest frame only, dropping any that arrive while busy.
  - `FACES_PATH` holds only people introduced through `meet`, their last-seen bearings, and remembered spots.
  - Settings: `ARMSTRONG_VIDEO_DELAY_S` (default 0.3), `ARMSTRONG_PAN_SIGN`, `ARMSTRONG_TILT_SIGN`, `ARMSTRONG_HFOV_DEG`, `ARMSTRONG_SPEED_SCALE` (default 1.0).
  - Keys in this terminal through `utils.hotkeys.Hotkeys(global_tap=False)`: `p` parks through `request_park`, and `x` quits.
  - `--offline`: frames from `cv2.VideoCapture`, simulated joints that follow the commands, no Portal, and a `utils.rerun_view.Preview` showing boxes, names and the target bearing.

- [ ] **Step 6: Run offline.** `uv run camera-op --offline --source 0` with three people who agree, calling commands from a small script. Expected: names are right, the box stays on the same person when someone else crosses, and a pointing hand starts a sweep.

- [ ] **Step 7: Commit** `"Add camera operator"`.

### Task 9: Personal context and script

**Files:**
- Create: `src/armstrong/context.py`
- Test: `tests/test_context.py`

**Interfaces:**
- Produces:
  - `parse_script(text: str) -> list[Shot]`, raising `ScriptError(line: int)` for a non-empty line with no colon
  - `@dataclass Shot: target: str; action: str`
  - `@dataclass Take: shot: int; number: int; name: str; status: str; start_pan: float; start_tilt: float; path: list; directions: list`, with status one of `rolling, kept, rejected, unknown`
  - `class Context(path)` with `load()`, `save()` (write then rename), `add_person(name, role, notes)`, `resolve(words) -> str | None`, `set_script(text)`, `current_shot() -> Shot | None`, `next_shot() -> Shot | None`, `go_to_shot(n) -> Shot`, `new_take(start_pan, start_tilt) -> Take`, `finish_take(status, path)`, `reject_last_take() -> Take | None`, `log_direction(t, text)`, `note(text)`, `add_spot(name)`, `keyterms() -> list[str]`, `prompt_section() -> str`, and fields `takes: list[Take]` and `phone_held: bool`

The director is the only writer of `CONTEXT_PATH`. Face data stays in `FACES_PATH`, written only by the camera operator, so the two processes never write the same file. Named things are remembered spots (a saved pan and tilt) rather than a new object detector.

- [ ] **Step 1: Write the failing tests**

```python
def test_parse_script_reads_target_and_action():
    assert parse_script("June: introduces the project\n\nwide: the room")[1] == Shot("wide", "the room")
def test_script_line_without_a_colon_is_reported():
    with pytest.raises(ScriptError) as e: parse_script("June: hi\nnope")
    assert e.value.line == 2
def test_resolve_by_name_or_role_ignoring_case(ctx):
    ctx.add_person("June", "presenter", "")
    assert ctx.resolve("june") == "June" and ctx.resolve("the presenter") == "June" and ctx.resolve("Bob") is None
def test_takes_are_numbered_per_shot(ctx):
    ctx.set_script("June: a\nArjun: b")
    assert ctx.new_take(0, 0).name == "shot1_take1"
    ctx.finish_take("rejected", [])
    assert ctx.new_take(0, 0).name == "shot1_take2"
    ctx.finish_take("kept", []); ctx.next_shot()
    assert ctx.new_take(0, 0).name == "shot2_take1"
def test_rejected_take_is_kept_in_the_list(ctx): ...
def test_directions_are_logged_with_their_take_for_trimming(ctx): ...
def test_survives_a_restart_including_phone_held(tmp_path): ...
def test_prompt_section_names_people_shot_takes_and_notes(ctx): ...
def test_keyterms_include_cast_and_commands(ctx):
    ctx.add_person("June", "", "")
    assert {"June", "Armstrong", "retake"} <= set(ctx.keyterms())
```

- [ ] **Step 2: Run** `uv run --group dev pytest tests/test_context.py -v`. Expected: FAIL, module missing.

- [ ] **Step 3: Implement** the signatures above.

- [ ] **Step 4: Run** the tests. Expected: PASS.

- [ ] **Step 5: Commit** `"Add personal context, script and takes"`.

### Task 10: Voice director

**Files:**
- Create: `src/armstrong/directing.py`, `src/armstrong/director.py`
- Test: `tests/test_directing.py`, `tests/test_director.py`

**Interfaces:**
- Consumes: `voice_agent.PolicyLink`, `voice_agent.STOP_WORDS`; `Context` (Task 9); the `camera.*`, `phone.*` and `dream.set_free_arm` RPCs
- Produces:
  - `is_direction(text: str) -> bool`, matching `^\W*arm\s?strong\b`; `is_cut(text: str) -> bool`, matching `^\W*cut\b`
  - `class Directing(link, phone, context, say, confirm_timeout_s=CONFIRM_TIMEOUT_S)`, where `link.camera(name, **payload)` and `link.call(method, **payload)` return dicts, `phone.present()` returns a bool, `phone.record_start(name)` and `phone.record_stop()` return dicts, and `say(text)` waits for playout
  - Async methods answering a sentence for the LLM: `take_phone, got_phone, released_phone, meet_person, look_at_person, follow_person, look_where_pointed, hold_still, look_around, start_take, cut, retake, next_shot, go_to_shot, remember, remember_spot, park_arms, status`; plus `on_stop_word()` and field `rolling: bool`
  - `class Director(Agent)` with `__init__(self, directing: Directing, llm=None)`, so tests need no LiveKit credentials; `uv run director connect --room portal-voice`

`Director` extends `Agent`, not `VoiceControl`, so it has no `resume`, `change_task` or teleop tools. A stray "continue" then can't hand the phone arm to Dream-1.

- [ ] **Step 1: Write the failing tests,** with fakes that record every call in one ordered list.

```python
async def test_take_phone_frees_the_arm_then_sets_task_then_resumes(d, calls):
    await d.take_phone()
    assert names(calls) == ["dream.set_free_arm:right", "dream.set_task", "dream.resume"]
async def test_take_phone_refused_when_phone_held(d, calls):
    d.context.phone_held = True
    await d.take_phone()
    assert calls == []
async def test_take_phone_times_out_and_pauses(d, calls):           # confirm_timeout_s set to 0.01
    await d.take_phone(); await asyncio.sleep(0.05)
    assert names(calls)[-1] == "dream.pause"
async def test_got_phone_stops_dream_before_the_camera_moves(d, calls):
    await d.got_phone()
    assert names(calls) == ["camera.status", "dream.pause", "dream.set_free_arm:none", "camera.set_phone_held",
                            "camera.take_control", "camera.carry"]
    assert d.context.phone_held is True
async def test_got_phone_refused_if_jaws_do_not_match_the_handle(d, calls):   # grip 70 mm against a 40 mm handle
    result = await d.got_phone()
    assert "dream.pause" not in names(calls) and "handle" in result
async def test_start_take_counts_down_before_recording(d, calls):
    await d.start_take()
    assert names(calls).index("say") < names(calls).index("phone.record_start") and d.rolling
async def test_start_take_refused_while_rolling(d, calls): ...
async def test_start_take_refused_when_phone_is_gone(d, calls): ...   # phone raises ToolError; not rolling; no camera move
async def test_cut_stops_recording_and_keeps_the_path(d, calls): ...
async def test_cut_when_phone_unreachable_marks_unknown(d, calls):
    # phone.record_stop raises: rolling False, take status "unknown", sentence says to check the phone
async def test_retake_keeps_the_old_file_and_returns_to_the_start_pose(d, calls):
    await d.start_take(); calls.clear(); await d.retake()
    n = names(calls)
    assert n.index("phone.record_stop") < n.index("camera.go_to") < n.index("say") < n.index("phone.record_start")
    assert d.context.takes[0].status == "rejected" and d.context.takes[1].name == "shot1_take2"
async def test_cut_then_retake_rejects_that_take(d, calls):
    await d.start_take(); await d.cut(); assert d.context.takes[0].status == "kept"
    await d.retake(); assert d.context.takes[0].status == "rejected" and d.rolling
async def test_retake_with_no_take_refused(d, calls): ...
async def test_stop_word_holds_the_camera_and_pauses_dream(d, calls):
    await d.on_stop_word()
    assert {"camera.hold", "dream.pause"} <= set(names(calls))
async def test_stop_word_works_when_dream_is_not_running(d, calls): ...   # dream raises ToolError; camera still holds
def test_directions_need_the_wake_word():
    assert is_direction("Armstrong, look at Arjun") and is_direction("arm strong follow me") and not is_direction("look at Arjun")
def test_cut_only_at_the_start_of_a_line():
    assert is_cut("Cut, I want to retake") and not is_cut("we cut the budget")
```

In `tests/test_director.py`:

```python
def test_director_has_no_tool_that_hands_the_arm_to_dream():
    for name in ("resume", "change_task", "switch_to_teleop", "switch_to_hand_teleop", "home_arms"):
        assert not hasattr(Director, name)
def test_agent_stays_silent_while_rolling():
    # run Director.tts_node with rolling True on a text stream; it yields no frames and drains the text
def test_lines_without_the_wake_word_get_no_reply_while_rolling():
    # on_user_turn_completed raises StopResponse for "and then we built it"; returns normally for "Armstrong, cut to June"
```

- [ ] **Step 2: Run** `uv run --group dev pytest tests/test_directing.py tests/test_director.py -v`. Expected: FAIL, modules missing.

- [ ] **Step 3: Implement `directing.py`.** `got_phone` compares `status()["grip_mm"]` with `ARMSTRONG_HANDLE_MM`, within 8 mm. `take_phone` uses the Dream task text from `ARMSTRONG_DREAM_TASK`, set in Task 12. `start_take`: refuse if `phone.present()` is false, then aim at the shot's target (person, spot, or `camera.go_to` with no arguments for `wide`), `camera.mark_start`, `say("Three, two, one")`, `phone.record_start`, then set `rolling`. `cut` marks the take `kept`. `retake` stops any recording, calls `reject_last_take`, `camera.go_to` to that take's start pose, and waits on `camera.status` until `arrived` before the countdown. The old file stays on the phone.

- [ ] **Step 4: Implement `director.py`,** following `voice_agent.py` for session and pipeline.
  - `class ArmstrongLink(PolicyLink)` adds `camera(name, **payload)` using `_rpc(CAMERA_IDENTITY, "The camera operator", "uv run camera-op", "camera." + name, json.dumps(payload))`. Also add one for `dream.set_free_arm`.
  - `class PhoneLink` calls `ctx.room.local_participant.perform_rpc(destination_identity=PHONE_IDENTITY, ...)`, raising `ToolError` if the phone isn't in the room.
  - `Director.llm_node` injects `context.prompt_section()` the way `VoiceControl.llm_node` injects the task monitor line.
  - `Director.tts_node` drains its text and yields nothing while `rolling`. `Director.on_user_turn_completed` raises `StopResponse` while `rolling` unless `is_direction`, and logs directions with `log_direction`.
  - On `user_input_transcribed`: `STOP_WORDS` calls `on_stop_word` at once, repeat-limited as in `voice_agent`. `is_cut` on a final transcript calls `cut`.
  - `@server.rtc_session(agent_name="armstrong-director")`; `room_io.RoomOptions(participant_identity=env_str("ARMSTRONG_MIC_IDENTITY", PHONE_IDENTITY), close_on_disconnect=False, audio_input=<as in voice_agent>)`, so the agent listens only to the phone and survives a page reload.
  - `ctx.room.on("data_received")` on `SCRIPT_TOPIC` calls `set_script`. A `ScriptError` is spoken as the line number when not rolling.
  - `keyterms=context.keyterms()` at session start. New names need a director restart.
  - A task polls `camera.status` every 0.5 s and speaks each new `event` when not rolling.
  - Instructions: plain speech for text-to-speech, one short sentence, spell out numbers, and never claim what a tool result doesn't say.

- [ ] **Step 5: Run** the tests. Expected: PASS.

- [ ] **Step 6: Try it with a fake camera.** Run `uv run director connect --room portal-voice` with a small fake `camera-op`, and the phone joined. Run the walkthrough by voice, and try one line of script with "stop" in it. Expected: no reply while rolling, and "cut" works.

- [ ] **Step 7: Test the phone's mic** at 1.5 m and 3 m in the actual room, with 10 directions at each distance. Count correct transcripts. **Below 8 of 10 at 3 m:** have a teammate's phone with earbuds join as `mic` and set `ARMSTRONG_MIC_IDENTITY=mic`.

- [ ] **Step 8: Commit** `"Add voice director"`.

### Task 11: Phone rig and dummy

The spec leaves the clamp and handle to the builder. These are the numbers the calculation assumed.

**Files:**
- Modify: `docs/bringup-log.md`, and `calc/follow_loop.py` if the rig differs

- [ ] **Step 1: Build the rig.** A phone clamp bolted to a flat-sided handle.
  - The handle is at most 60 mm across the flats, because the jaws open to 80 mm.
  - The rig stands alone on the table with the handle up, so Dream-1 can grip it from above.
  - It has a tether point. Flat sides keep the lens square in the jaws.
  - If you print load-carrying parts, run the `aero-mechatronics` gate first and check layer direction. Printed parts should be filleted, not blocky.

- [ ] **Step 2: Weigh it with the phone and case on a scale, and measure jaws to phone centre.** Expected: at most 0.32 kg and at most 0.08 m.

- [ ] **Step 3: If either is over, change `PHONE` or `HANDLE` in `calc/follow_loop.py` and rerun it.** A negative camera-pose margin stops this task until the rig is changed.

- [ ] **Step 4: Build the dummy** with the same mass and outline, and test it on the rig. All first tests use it.

- [ ] **Step 5: Turn the rig tool-up by hand.** Expected: the phone is landscape and level, its lens faces forward, and the page's video is the right way up. Note the phone's orientation lock setting.

- [ ] **Step 6: Record** mass, lengths and handle width, and set `ARMSTRONG_HANDLE_MM`. Commit `"Add rig measurements"`.

### Task 12: AT THE ARM: bring-up and Dream-1 pick-up

Tape the line and put the emergency-stop holder in place before powering anything. Record every answer and count in `docs/bringup-log.md`.

- [ ] **Step 1: Ask MakerMods and David Chen:** are there two arms and three cameras, what is the emergency stop and does it cut power, which computer and OS, can we plug in our own, how does Dream-1 connect, how do fine-tunes and credits work, is a 1 rad/s step limit OK, how do we read motor temperature (the Portal code doesn't expose it), and what are the Track 2 rubric and submission format? Also settle the Manifest questions at the top of this plan.

- [ ] **Step 2: Start the station.** Set `MAKERMODS_MODEL=makers`, the CAN settings and cameras in `.env`, and close MakerMods Lab. Run `uv run robot --check-arms`. Expected: both arms print joints. Then run `uv run robot --parked`. **One arm only:** the program won't start, so ask David Chen.

- [ ] **Step 3: Dry-run Dream-1.** `ARMSTRONG_DREAM_FREE_ARM=right uv run dream-one-arm --dry-run --task "pick up the black handle with the right gripper"`, then press `c`. Expected: targets print and nothing moves. A dry run prints Dream-1's raw targets for both arms and never reaches `send_action`, so it doesn't test the wrapper. Task 4's tests do that.

- [ ] **Step 4: Run it live with the dummy.** Press `p` in the robot terminal to power up, put the rig inside its marked area, and use the same command without `--dry-run`. Watch the left arm first: **if it moves at all, stop and find out why before anything else.** Film it and time the calls. Try different wording first, because wording is free. Save the best in `ARMSTRONG_DREAM_TASK`. Note whether Dream-1 copes with the left arm sitting still.

- [ ] **Step 5: Count successes from 10 random positions inside the marked area.** Those failures set the fine-tune's focus.

- [ ] **Step 6: Record about 5 minutes of demonstrations** of the right arm picking up the rig, using `uv run teleoperator` and `uv run recorder` and the format the venue specifies. Get approval, then start the first fine-tune. Set `DREAM_CHECKPOINT` when it returns, and rerun the count. Start the second by 5:30 PM and the last by 10:00 PM.

- [ ] **Step 7: Test the grip, low over the mat, with the dummy on its tether.**
  1. Close on the handle with a target 5 mm below the measured width, and shake gently by hand command. Expected: no slip.
  2. Call `home`. It commands the measured width (`src/utils/metal.py:292`). Expected: the jaws don't loosen. If they do, never use `home` with the phone.
  3. Press `p`. Expected: note whether the rig hits the table on the way to rest, and whether the jaws let go when motors switch off. If it hits, restart the robot with the arm resting higher, because the rest pose is wherever it started.

- [ ] **Step 8: Hold the dummy in the camera pose for 10 minutes** with `camera-op`. Read temperatures by the method from Step 1, or with an IR thermometer after parking if there is none. **Hot motors:** lower the holding load, shorten takes, and rest between them.

- [ ] **Step 9: Saturday 6:00 PM gate.** **Below 5 of 10:** make the handle bigger and shrink the area. If that fails, a person loads the clamp while parked, labeled in the film, and Dream-1's visible job moves to "hold this" with the free arm.

- [ ] **Step 10: Commit** `"Log arm bring-up"`.

### Task 13: AT THE ARM: aim the real camera

**Interfaces:**
- Consumes: `uv run camera-op`, `uv run director`, `uv run dream-one-arm`
- Produces: real values for `CAMERA_POSE_DEG`, `ARMSTRONG_PAN_SIGN`, `ARMSTRONG_TILT_SIGN`, `ARMSTRONG_VIDEO_DELAY_S`, `ARMSTRONG_HFOV_DEG`

- [ ] **Step 1: Find the camera pose, dummy on, at low speed.** Move it toward the first guess with `uv run hand-teleop`, then read `joints` from `camera.status`. Check the real wrist sign against the first guess. Expected: tool up, phone landscape. Update `CAMERA_POSE_DEG`, and rerun Task 8's tests.

- [ ] **Step 2: Check clearance.** Set `ARMSTRONG_SPEED_SCALE=0.3`. Pan across ±90 degrees with `go_to` and look for the other arm. If it gets close, reduce `PAN_LIMIT_RAD`.

- [ ] **Step 3: Set the signs,** still at `ARMSTRONG_SPEED_SCALE=0.3`. A person stands to the frame's right, and `look_at` must pan toward them. If it pans away, flip the sign. Do the same for tilt.

- [ ] **Step 4: Go to full speed.** Check `METAL_MAX_STEP_RAD`: the default 0.087 allows 1 rad/s, and the macOS example's 0.02 allows only 0.6. Raise it only with MakerMods' OK. Set `ARMSTRONG_SPEED_SCALE=1`, and film the result to judge shake. **The video shakes:** lower `ARMSTRONG_SPEED_SCALE`.

- [ ] **Step 5: Measure delay and field of view.** Pan at a steady rate with a fixed face in view, and choose the delay that keeps the computed bearing steady. For field of view, stand at a known offset and distance. Record both.

- [ ] **Step 6: Now the real phone, tethered, over the mat, then raised.** Run the follow test: a person walks across at 2 m. Expected: stays in frame with at most about 20 degrees of trail, and settles within about 2 degrees of still without hunting (`calc/aim_sim.py`).

- [ ] **Step 7: Commit** `"Set real camera pose, signs and delay"`.

### Task 14: AT THE ARM: full run

- [ ] **Step 1: Start everything,** each in its own terminal, from the repo root.

```bash
uv run robot
```

```bash
uv run dream-one-arm
```

```bash
uv run camera-op
```

```bash
uv run director connect --room portal-voice
```

```bash
uv run phone-qr
```

- [ ] **Step 2: Run the whole walkthrough with the dummy,** then with the phone, using a script of at least three shots and at least three people: script, "take my phone," "got it," carry, "this is June, she's presenting," "shot one," "Armstrong, look at Arjun," "Armstrong, follow me," "Armstrong, look over there" with a point, "cut, I want to retake," and "next." Expected: every goal in the spec happens in one sitting, and takes are saved on the phone under the right names.

- [ ] **Step 3: Try to break it,** with the emergency-stop holder ready. Say "continue" while holding the phone. Have a stranger who agreed walk through the shot. Ask for someone who isn't there. Reload the phone page during a take. Turn Wi-Fi off for 20 seconds. Expected: what Review Focus says.

- [ ] **Step 4: Fix what failed, and rerun Step 2.** Stop adding features at 12:30 PM Sunday.

- [ ] **Step 5: Commit** `"Fix issues from full run"`.

### Task 15: Film and submit

- [ ] **Step 1: Check the venue's Track 2 rubric and submission format** first.

- [ ] **Step 2: Shoot the film on the arm's phone,** following the spec's one-minute outline: cold open, "this is June," look-at plus pointing plus following in one real-time take, a real flub and retake, and the reveal. Shots showing the arm come from a second camera on a tripod.

- [ ] **Step 3: Edit.** Trim spoken directions using the logged times. Label outside shots, sped-up footage and any hand-loaded rig. Only claim what ran.

- [ ] **Step 4: Upload by 2:30 PM Sunday.** Check that the link opens in a private window.

- [ ] **Step 5: After the event, delete face data.** Run `rm data/faces.json data/context.json`, and confirm with `ls data`. The team should also rotate the LiveKit and Dream keys if they were shared.

### Stretch, only after Task 14 passes

Each one is independent. Test it, film it, and label it the same way.

- **Exact path replay:** `go_to` the start pose, then play a take's logged path at its original timing, within filming limits.
- **Auto-advance:** when a final transcript matches the next shot's action closely, advance as "next" would.
- **"Hold this":** a tool that calls `dream.set_free_arm` with `left`, sets a task, and resumes. The phone stays in the right jaws through the squeeze latch from Task 4. It is also the fallback for the 6:00 PM gate.
- **Reset a prop before a retake:** the same free-arm flow, called from `retake` when asked.
