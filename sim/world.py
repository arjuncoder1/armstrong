"""The Genesis world: a table, two Maker Arm v1 arms, five playing cards and a deck, three cameras.

Every Genesis call happens on the thread that built the world (on macOS, the main thread: OpenGL and the
viewer need it). Other threads talk to it only through `World.command()` and `World.snapshot()`.
"""
from __future__ import annotations

import base64
import io
import math
import threading
import time

import numpy as np
from PIL import Image

import assets

SIDES = ("left", "right")
ARM_Y = {"left": 0.3, "right": -0.3}  # left/right as seen standing behind the arms, facing +x
PHYSICS_HZ = 60
IMAGE_EVERY_S = 0.2  # the station encodes its JPEGs at 5 fps
RES = (640, 480)
KP = np.array([900.0, 1500.0, 1200.0, 400.0, 300.0, 300.0])
KV = np.array([60.0, 90.0, 70.0, 25.0, 20.0, 20.0])
# A card the jaw closes on within this distance of the grasp centre is attached (a scripted grasp).
GRASP_RADIUS_M = 0.045
CARDS = [("A", "S"), ("K", "H"), ("Q", "D"), ("J", "C"), ("10", "H")]


def _quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _quat_inv(q):
    return np.array([q[0], -q[1], -q[2], -q[3]])


def _rotate(q, v):
    return _quat_mul(_quat_mul(q, np.array([0.0, *v])), _quat_inv(q))[1:]


def _yaw_quat(yaw):
    return np.array([math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)])


class World:
    def __init__(self, viewer: bool = False, backend: str = "metal") -> None:
        import genesis as gs

        self.gs = gs
        gs.init(backend=gs.metal if backend == "metal" else gs.cpu, logging_level="warning", precision="32")
        self.scene = gs.Scene(
            sim_options=gs.options.SimOptions(dt=1.0 / PHYSICS_HZ, substeps=2),
            rigid_options=gs.options.RigidOptions(enable_self_collision=False),
            viewer_options=gs.options.ViewerOptions(camera_pos=(-0.9, 0.0, 0.9), camera_lookat=(0.3, 0.0, 0.0),
                                                    camera_fov=50),
            vis_options=gs.options.VisOptions(show_world_frame=False, ambient_light=(0.35, 0.35, 0.35),
                                              lights=[{"type": "directional", "dir": (0.3, 0.2, -1.0),
                                                       "color": (1.0, 1.0, 1.0), "intensity": 4.0}]),
            renderer=gs.renderers.Rasterizer(),
            show_viewer=viewer,
        )
        s = self.scene
        s.add_entity(gs.morphs.Plane(pos=(0, 0, -0.75)), surface=gs.surfaces.Default(color=(0.35, 0.35, 0.38)))
        # Table top: z = 0 is its surface; the arms sit on its near edge.
        s.add_entity(gs.morphs.Box(pos=(0.35, 0.0, -0.02), size=(0.9, 1.4, 0.04), fixed=True),
                     surface=gs.surfaces.Default(color=(0.62, 0.48, 0.33)))
        urdf = str(assets.arm_urdf())
        self.arms = {side: s.add_entity(gs.morphs.URDF(file=urdf, pos=(0.0, ARM_Y[side], 0.0), fixed=True,
                                                       merge_fixed_links=False))
                     for side in SIDES}
        # Five cards face up in a row in front of the arms, the deck to the right of them.
        self.cards = []
        self.card_rest: list[tuple[np.ndarray, np.ndarray]] = []
        for i, (rank, suit) in enumerate(CARDS):
            pos = np.array([0.32, 0.2 - 0.1 * i, assets.CARD_T / 2 + 0.0005])
            quat = _yaw_quat(-math.pi / 2)  # the card's top (+y) points away from the arms (+x)
            ent = s.add_entity(gs.morphs.Mesh(file=str(assets.card_mesh(rank, suit)), pos=tuple(pos), quat=tuple(quat),
                                              fixed=True, collision=False, file_meshes_are_zup=True))
            self.cards.append(ent)
            self.card_rest.append((pos, quat))
        deck_t = 0.012
        s.add_entity(gs.morphs.Mesh(file=str(assets.card_mesh("A", "S", deck_t)), pos=(0.2, 0.0, deck_t / 2 + 0.0005),
                                    quat=tuple(_quat_mul(_yaw_quat(-math.pi / 2), np.array([0.0, 1.0, 0.0, 0.0]))),
                                    fixed=True, collision=False, file_meshes_are_zup=True))  # back up
        self.cams = {"top": s.add_camera(res=RES, pos=(-0.45, 0.0, 0.85), lookat=(0.33, 0.0, 0.0), fov=58)}
        for side in SIDES:
            self.cams[side] = s.add_camera(res=RES, pos=(0, 0, 1), lookat=(0, 0, 0), fov=75)
        s.build()

        self.joint_dofs = {}
        self.finger_dofs = {}
        for side, arm in self.arms.items():
            jd = [arm.get_joint(n).dofs_idx_local[0] for n in assets.JOINT_NAMES]
            fd = [arm.get_joint(n).dofs_idx_local[0] for n in assets.FINGER_NAMES]
            self.joint_dofs[side], self.finger_dofs[side] = jd, fd
            arm.set_dofs_kp(KP, jd)
            arm.set_dofs_kv(KV, jd)
            arm.set_dofs_kp(np.array([200.0, 200.0]), fd)
            arm.set_dofs_kv(np.array([10.0, 10.0]), fd)
            arm.set_dofs_position(np.zeros(6), jd)
            arm.set_dofs_position(np.full(2, assets.GRIPPER_HALF_STROKE_M), fd)
            # Wrist camera: on the gripper housing, offset along link_007's x, looking down the fingers (-z).
            link = arm.get_link("link_007")
            T = gs.utils.geom.pos_lookat_up_to_T(np.array([0.05, 0.0, -0.03]), np.array([0.0, 0.0, assets.GRASP_Z - 0.06]),
                                                 np.array([1.0, 0.0, 0.0]))
            self.cams[side].attach(link, T)
        self.grasp_link = {side: arm.get_link("link_007") for side, arm in self.arms.items()}

        self.lock = threading.Lock()
        self.targets = {side: np.zeros(6) for side in SIDES}
        self.grippers = {side: 1.0 for side in SIDES}
        self.held: dict[str, tuple[int, np.ndarray, np.ndarray] | None] = {side: None for side in SIDES}
        self.state: dict = {}
        self.images: list[dict] = []
        self.images_at = 0.0
        self.temps = {side: np.array([41.0, 43.0, 42.5, 40.5, 40.0, 40.2, 41.5]) + (0.6 if side == "right" else 0.0)
                      for side in SIDES}
        self.running = True
        self._read_state()

    # ---- thread-safe interface ----------------------------------------------------------------------------------

    def command(self, targets: dict | None = None, grippers: dict | None = None) -> None:
        with self.lock:
            for side, t in (targets or {}).items():
                self.targets[side] = np.clip(np.asarray(t, float), [lo for lo, _ in assets.LIMITS_RAD_SIM],
                                             [hi for _, hi in assets.LIMITS_RAD_SIM])
            for side, g in (grippers or {}).items():
                self.grippers[side] = float(min(max(g, 0.0), 1.0))

    def snapshot(self) -> tuple[dict, list[dict]]:
        with self.lock:
            return {k: dict(v) for k, v in self.state.items()}, list(self.images)

    # ---- the sim thread -----------------------------------------------------------------------------------------

    def _read_state(self) -> None:
        state = {}
        for side, arm in self.arms.items():
            q = arm.get_dofs_position(self.joint_dofs[side]).cpu().numpy().reshape(-1)
            dq = arm.get_dofs_velocity(self.joint_dofs[side]).cpu().numpy().reshape(-1)
            f = arm.get_dofs_position(self.finger_dofs[side]).cpu().numpy().reshape(-1)
            state[side] = {
                "positions_rad": [float(x) for x in q], "velocities_rad_s": [float(x) for x in dq],
                "gripper": float(np.clip(f.mean() / assets.GRIPPER_HALF_STROKE_M, 0.0, 1.0)),
                "motor_temps_c": [round(float(t), 1) for t in self.temps[side]],
                "commanded_rad": [float(x) for x in self.targets[side]],
                "commanded_gripper": float(self.grippers[side]),
            }
        with self.lock:
            self.state = state

    def _grasp_frame(self, side):
        link = self.grasp_link[side]
        pos = link.get_pos().cpu().numpy().reshape(-1)
        quat = link.get_quat().cpu().numpy().reshape(-1)
        return pos + _rotate(quat, (0.0, 0.0, assets.GRASP_Z + 0.02)), quat

    def _update_grasps(self) -> None:
        """Scripted grasp: a closing jaw near a card picks it up; an opening jaw drops it flat on the table."""
        for side in SIDES:
            g = self.grippers[side]
            held = self.held[side]
            if held is None and g < 0.35:
                gp, gq = self._grasp_frame(side)
                taken = {h[0] for h in self.held.values() if h}
                best, best_d = None, GRASP_RADIUS_M
                for i, card in enumerate(self.cards):
                    if i in taken:
                        continue
                    d = np.linalg.norm(card.get_pos().cpu().numpy().reshape(-1) - gp)
                    if d < best_d:
                        best, best_d = i, d
                if best is not None:
                    cp = self.cards[best].get_pos().cpu().numpy().reshape(-1)
                    cq = self.cards[best].get_quat().cpu().numpy().reshape(-1)
                    inv = _quat_inv(gq)
                    self.held[side] = (best, _rotate(inv, cp - gp), _quat_mul(inv, cq))
                    print(f"[sim] {side} gripper picked up card {''.join(CARDS[best])}")
            elif held is not None and g > 0.6:
                i, _, _ = held
                cp = self.cards[i].get_pos().cpu().numpy().reshape(-1)
                cq = self.cards[i].get_quat().cpu().numpy().reshape(-1)
                # Drop flat: keep its yaw and xy, lay it on the table.
                yaw = math.atan2(2 * (cq[0] * cq[3] + cq[1] * cq[2]), 1 - 2 * (cq[2] ** 2 + cq[3] ** 2))
                face_up = _rotate(cq, (0, 0, 1))[2] >= 0
                q = _yaw_quat(yaw) if face_up else _quat_mul(_yaw_quat(yaw), np.array([0.0, 1.0, 0.0, 0.0]))
                self.cards[i].set_pos(np.array([cp[0], cp[1], assets.CARD_T / 2 + 0.0005]))
                self.cards[i].set_quat(q)
                self.held[side] = None
                print(f"[sim] {side} gripper dropped card {''.join(CARDS[i])}")
            if self.held[side] is not None:
                i, off, qoff = self.held[side]
                gp, gq = self._grasp_frame(side)
                self.cards[i].set_pos(gp + _rotate(gq, off))
                self.cards[i].set_quat(_quat_mul(gq, qoff))

    def _render(self) -> None:
        images = []
        for name, cam in self.cams.items():
            if name != "top":
                cam.move_to_attach()
            rgb = cam.render(rgb=True)[0]
            rgb = np.asarray(rgb.cpu().numpy() if hasattr(rgb, "cpu") else rgb)
            if rgb.ndim == 4:
                rgb = rgb[0]
            buf = io.BytesIO()
            Image.fromarray(rgb.astype(np.uint8)).save(buf, "JPEG", quality=80)
            images.append({"camera": name, "jpeg": base64.b64encode(buf.getvalue()).decode(), "at": time.monotonic()})
        with self.lock:
            self.images = images

    def run(self) -> None:
        """Step physics at 60 Hz (real time) and render the cameras at 5 Hz, until `running` goes False."""
        period = 1.0 / PHYSICS_HZ
        next_tick = time.perf_counter()
        next_image = 0.0
        t0 = time.monotonic()
        while self.running:
            with self.lock:
                targets = {s: self.targets[s].copy() for s in SIDES}
                grippers = dict(self.grippers)
            for side, arm in self.arms.items():
                arm.control_dofs_position(targets[side], self.joint_dofs[side])
                arm.control_dofs_position(np.full(2, grippers[side] * assets.GRIPPER_HALF_STROKE_M),
                                          self.finger_dofs[side])
            self.scene.step()
            self._update_grasps()
            # Temperatures drift slowly around 40-45 C.
            t = time.monotonic() - t0
            for k, side in enumerate(SIDES):
                self.temps[side] = (np.array([41.5, 43.4, 43.0, 41.5, 41.0, 41.2, 42.0]) + 0.6 * k
                                    + 0.9 * np.sin(t / 60.0 + np.arange(7)))  # stays within 40-45 C
            self._read_state()
            if time.monotonic() >= next_image:
                next_image = time.monotonic() + IMAGE_EVERY_S
                self._render()
            next_tick += period
            now = time.perf_counter()
            if next_tick > now:
                time.sleep(next_tick - now)
            else:
                next_tick = now
