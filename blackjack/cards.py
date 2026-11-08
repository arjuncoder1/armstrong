"""Read the table: YOLOv8 card detections, split into the dealer's and the player's side of the table.

The model (koolguy06/playing-cards, trained on the Augmented Startups dataset) boxes card corners, so one card
often gives two boxes with the same label; a label counts once per side. The camera looks down at the table with
the dealer's cards in the top part of the image and the player's cards in the bottom part.
"""
from dataclasses import dataclass
from pathlib import Path

MODEL = Path(__file__).resolve().parent / 'models' / 'playing-cards.pt'


@dataclass(frozen=True)
class Detection:
    label: str
    conf: float
    cx: float  # box centre, as a fraction of image width / height
    cy: float


def split_table(detections: list[Detection], split: float = 0.5, min_conf: float = 0.5) -> dict[str, list[str]]:
    """Unique card labels on each side: dealer above `split` (fraction of image height), player below."""
    sides: dict[str, list[str]] = {'dealer': [], 'player': []}
    for d in sorted(detections, key=lambda d: (d.cx, -d.conf)):
        if d.conf < min_conf:
            continue
        side = sides['dealer' if d.cy < split else 'player']
        if d.label not in side:
            side.append(d.label)
    return sides


def vote(reads: list[dict[str, list[str]]]) -> dict[str, list[str]]:
    """Keep a card on a side when it was seen in more than half the reads (filters one-frame flickers)."""
    out = {}
    for side in ('dealer', 'player'):
        seen: dict[str, int] = {}
        for r in reads:
            for c in r[side]:
                seen[c] = seen.get(c, 0) + 1
        out[side] = [c for c, n in seen.items() if n * 2 > len(reads)]
    return out


class CardReader:
    def __init__(self, model: Path = MODEL):
        from ultralytics import YOLO  # heavy import, only when a camera is really read
        self.model = YOLO(str(model))

    def detect(self, frame) -> list[Detection]:
        h, w = frame.shape[:2]
        result = self.model.predict(frame, imgsz=640, verbose=False)[0]
        out = []
        for box, cls, conf in zip(result.boxes.xywh.tolist(), result.boxes.cls.tolist(), result.boxes.conf.tolist()):
            out.append(Detection(self.model.names[int(cls)], float(conf), box[0] / w, box[1] / h))
        return out
