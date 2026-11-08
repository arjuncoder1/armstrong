"""Generated sim assets: the Maker Arm v1 URDF (primitives on dream_ik's kinematics) and textured card meshes.

Everything is written to sim/assets/generated/ on first use (cheap, deterministic, so it is not checked in).
"""
from __future__ import annotations

import math
import pathlib

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial.transform import Rotation

OUT = pathlib.Path(__file__).resolve().parent / "assets" / "generated"

# Soft limits in degrees from robots.makers.JOINTS (shoulder_pan .. wrist_roll). Zero is the folded rest pose.
LIMITS_DEG = ((-158.2, 156.1), (-175.3, -3.2), (2.8, 236.1), (-65.2, 104.0), (-97.6, 78.0), (-153.2, 152.0))
LIMITS_RAD = [(math.radians(lo), math.radians(hi)) for lo, hi in LIMITS_DEG]
LIMITS_RAD_SIM = [(min(lo, 0.0), max(hi, 0.0)) for lo, hi in LIMITS_RAD]  # zero (rest) reachable
GRIPPER_HALF_STROKE_M = 0.04  # 80 mm stroke: each finger moves 40 mm

# dream_ik maker_arm_ik.urdf, verbatim joint origins/axes (z-up, x forward, y left base frame).
CHAIN = [
    # name, parent, child, xyz, rpy, axis
    ("link_002_joint", "base_link", "link_002", (0, 0.030799999, 0), (-1.5707963, 0, 0), (0, 0, -1)),
    ("link_003_joint", "link_002", "link_003", (0, 0, 0.0583), (1.5707963, 0, 0), (0, 0, -1)),
    ("link_004_joint", "link_003", "link_004", (0.19, 0, 0), (0, 0, 0), (0, 0, -1)),
    ("link_005_joint", "link_004", "link_005", (-0.174, 0.076315136, 0), (0, 0, 0), (0, 0, -1)),
    ("link_006_joint", "link_005", "link_006", (-0.084967787, 0.032692166, 0), (1.5707963, 0, 0.17453293), (0, 0, -1)),
    ("link_007_joint", "link_006", "link_007", (-0.00025000013, 0, 0.04695), (0, 1.5707963, 0), (0, 0, 1)),
]
GRASP_Z = -0.169638704618  # grasp_center in link_007's frame: the gripper points along link_007's -z
JOINT_NAMES = [c[0] for c in CHAIN]
FINGER_NAMES = ["finger_a_joint", "finger_b_joint"]

COLORS = {"dark": "0.15 0.15 0.17 1", "orange": "0.95 0.45 0.1 1", "grey": "0.6 0.62 0.65 1", "black": "0.05 0.05 0.05 1"}


def _inertial(mass: float = 0.2) -> str:
    i = 1e-4 * mass / 0.2
    return (f'<inertial><origin xyz="0 0 0"/><mass value="{mass}"/>'
            f'<inertia ixx="{i}" ixy="0" ixz="0" iyy="{i}" iyz="0" izz="{i}"/></inertial>')


def _rpy(m: np.ndarray) -> str:
    r, p, y = Rotation.from_matrix(m).as_euler("xyz")
    return f"{r:.6f} {p:.6f} {y:.6f}"


def _segment(v, radius: float, color: str) -> str:
    """A cylinder from the link origin to point v (in the link frame), plus a joint ball at each end."""
    v = np.asarray(v, float)
    length = float(np.linalg.norm(v))
    if length < 1e-4:
        return ""
    z = v / length
    rot = Rotation.align_vectors([z], [[0, 0, 1]])[0].as_matrix()
    c = v / 2
    return (f'<visual><origin xyz="{c[0]:.6f} {c[1]:.6f} {c[2]:.6f}" rpy="{_rpy(rot)}"/>'
            f'<geometry><cylinder radius="{radius}" length="{length:.6f}"/></geometry>'
            f'<material name="m{color}"><color rgba="{COLORS[color]}"/></material></visual>'
            f'<visual><origin xyz="0 0 0"/><geometry><sphere radius="{radius * 1.25}"/></geometry>'
            f'<material name="mgrey"><color rgba="{COLORS["grey"]}"/></material></visual>')


def _box(xyz, size, color: str, collision: bool = False) -> str:
    g = f'<origin xyz="{xyz[0]} {xyz[1]} {xyz[2]}"/><geometry><box size="{size[0]} {size[1]} {size[2]}"/></geometry>'
    out = f'<visual>{g}<material name="m{color}"><color rgba="{COLORS[color]}"/></material></visual>'
    return out + (f"<collision>{g}</collision>" if collision else "")


def arm_urdf() -> pathlib.Path:
    """Maker Arm v1: dream_ik's chain with capsule-ish links and a two-finger jaw on link_007 (visual-only arm)."""
    path = OUT / "maker_arm_v1.urdf"
    links: dict[str, str] = {"ik_base": "", "base_link": "", "fingers": ""}
    # Base pedestal (in ik_base frame, z up): a box from the table to the shoulder.
    links["ik_base"] = _box((0, 0, 0.0154), (0.09, 0.09, 0.0308), "dark")
    seg_of = {"base_link": CHAIN[0][3]}
    for i, (_, _, child, *_rest) in enumerate(CHAIN):
        seg_of[child] = CHAIN[i + 1][3] if i + 1 < len(CHAIN) else None
    for name, v in seg_of.items():
        if v is not None:
            links[name] = _segment(v, 0.022 if name in ("link_003", "link_004") else 0.018,
                                   "orange" if name in ("link_003", "link_004") else "dark")
    # Gripper housing along link_007's -z, then two fingers.
    links["link_007"] = _box((0, 0, -0.05), (0.05, 0.07, 0.08), "dark")
    body = ['<?xml version="1.0"?>', '<robot name="maker_arm_v1">']
    for name in ["ik_base", "base_link", "link_002", "link_003", "link_004", "link_005", "link_006", "link_007"]:
        body.append(f'<link name="{name}">{_inertial()}{links.get(name, "")}</link>')
    for side, sign in (("a", 1), ("b", -1)):
        # A finger: 15 x 20 x 60 mm, from 90 to 150 mm down link_007's -z; it slides along y.
        finger = _box((0, sign * 0.008, GRASP_Z + 0.04), (0.02, 0.012, 0.07), "black", collision=False)
        body.append(f'<link name="finger_{side}">{_inertial(0.02)}{finger}</link>')
    body.append('<joint name="ik_base_joint" type="fixed"><origin xyz="0 0 0" rpy="1.5707963267948966 0 3.141592653589793"/>'
                '<parent link="ik_base"/><child link="base_link"/></joint>')
    for (name, parent, child, xyz, rpy, axis), (lo, hi) in zip(CHAIN, LIMITS_RAD):
        lo, hi = min(lo, 0.0), max(hi, 0.0)  # zero (the folded rest) must be reachable
        body.append(f'<joint name="{name}" type="revolute"><origin xyz="{xyz[0]} {xyz[1]} {xyz[2]}" '
                    f'rpy="{rpy[0]} {rpy[1]} {rpy[2]}"/><parent link="{parent}"/><child link="{child}"/>'
                    f'<axis xyz="{axis[0]} {axis[1]} {axis[2]}"/><limit lower="{lo}" upper="{hi}" effort="50" velocity="5"/>'
                    f'<dynamics damping="0.5"/></joint>')
    for side, sign in (("a", 1), ("b", -1)):
        body.append(f'<joint name="finger_{side}_joint" type="prismatic"><origin xyz="0 0 0"/>'
                    f'<parent link="link_007"/><child link="finger_{side}"/><axis xyz="0 {sign} 0"/>'
                    f'<limit lower="0" upper="{GRIPPER_HALF_STROKE_M}" effort="20" velocity="0.5"/></joint>')
    body.append("</robot>")
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body))
    return path


# ---- cards -----------------------------------------------------------------------------------------------------

CARD_W, CARD_L, CARD_T = 0.063, 0.088, 0.0015  # real cards are 0.3 mm; thicker so face and back do not z-fight
SUITS = {"S": ("♠", (0, 0, 0)), "H": ("♥", (200, 0, 0)), "D": ("♦", (200, 0, 0)), "C": ("♣", (0, 0, 0))}
FONTS = ["/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/System/Library/Fonts/Apple Symbols.ttf",
         "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Unicode.ttf"]


def _font(size: int, text: str):
    for f in FONTS:
        try:
            font = ImageFont.truetype(f, size)
            if font.getbbox(text)[2] > 0:
                return font
        except OSError:
            continue
    return ImageFont.load_default(size)


def _texture(rank: str, suit: str) -> Image.Image:
    """Atlas 1024 x 704: left half the face, right half the back (each 512 x 704, a 63 x 88 card)."""
    w, h = 512, 704
    img = Image.new("RGB", (2 * w, h), "white")
    d = ImageDraw.Draw(img)
    sym, color = SUITS[suit]
    d.rounded_rectangle((4, 4, w - 4, h - 4), 30, outline=(120, 120, 120), width=6)
    big = _font(260 if len(rank) == 1 else 190, rank)
    d.text((w / 2, h * 0.30), rank, font=big, fill=color, anchor="mm")
    d.text((w / 2, h * 0.70), sym, font=_font(300, sym), fill=color, anchor="mm")
    small = _font(70, rank)
    d.text((50, 60), rank, font=small, fill=color, anchor="mm")
    d.text((w - 50, h - 60), rank, font=small, fill=color, anchor="mm")
    # Back: red with a white diamond lattice.
    d.rectangle((w, 0, 2 * w, h), fill=(185, 20, 30))
    for k in range(-h, w + h, 48):
        d.line((w + k, 0, w + k + h, h), fill=(240, 200, 200), width=5)
        d.line((w + k + h, 0, w + k, h), fill=(240, 200, 200), width=5)
    d.rectangle((w + 6, 6, 2 * w - 6, h - 6), outline="white", width=20)
    return img


def card_mesh(rank: str, suit: str, thickness: float = CARD_T) -> pathlib.Path:
    """A thin box (x = 63 mm, y = 88 mm, z = thickness) as a GLB, face on +z, back on -z."""
    import trimesh

    path = OUT / f"card_{rank}{suit}_{round(thickness * 1e4)}.glb"
    if path.exists():
        return path
    OUT.mkdir(parents=True, exist_ok=True)
    hx, hy, hz = CARD_W / 2, CARD_L / 2, thickness / 2
    verts, uvs, faces = [], [], []

    def quad(corners, uv):
        base = len(verts)
        verts.extend(corners)
        uvs.extend(uv)
        faces.extend([[base, base + 1, base + 2], [base, base + 2, base + 3]])

    # Face (+z): u in [0, 0.5]. The card's top (rank) is at +y... image top is v=1.
    quad([(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)], [(0, 0), (0.5, 0), (0.5, 1), (0, 1)])
    # Back (-z): u in [0.5, 1].
    quad([(-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz), (hx, -hy, -hz)], [(0.5, 0), (0.5, 1), (1, 1), (1, 0)])
    white = [(0.25, 0.5)] * 4  # a white spot on the face
    quad([(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)], white)
    quad([(hx, hy, -hz), (-hx, hy, -hz), (-hx, hy, hz), (hx, hy, hz)], white)
    quad([(hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz), (hx, -hy, hz)], white)
    quad([(-hx, hy, -hz), (-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz)], white)
    tex = _texture(rank, suit)
    mesh = trimesh.Trimesh(np.array(verts), np.array(faces), process=False,
                           visual=trimesh.visual.TextureVisuals(uv=np.array(uvs), image=tex))
    mesh.export(path)
    tex.save(OUT / f"card_{rank}{suit}.png")
    return path
