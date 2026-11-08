"""Robot blackjack dealer: a top-down camera reads the cards, the dreamlabs station's Dream-1 deals them.

    uv run python dealer.py read --image table.jpg       # read one photo, print both hands
    uv run python dealer.py read --camera 0              # read the live camera once
    uv run python dealer.py play --camera 0              # a person deals when told to (no arm moves)
    uv run python dealer.py play --camera 0 --station http://127.0.0.1:8091   # Dream-1 deals

No hole card: the dealer gets one card up front and draws the rest after the player stands, so every card the
camera has to read is face up. The dealer stands on all 17s. Dealer cards go in the top half of the camera
image, player cards in the bottom half (--split moves the line).
"""
import argparse
import sys
import time

import cv2

import hand
from cards import CardReader, split_table, vote

PROMPTS = {
    'player': 'pick up the top card from the deck and place it face up in front of the player',
    'dealer': 'pick up the top card from the deck and place it face up in front of the dealer',
}


class Table:
    def __init__(self, args):
        self.reader = CardReader()
        self.split = args.split
        self.image = args.image
        self.cap = None if args.image else cv2.VideoCapture(args.camera)
        if self.cap is not None and not self.cap.isOpened():
            sys.exit(f'camera {args.camera} did not open')

    def read(self, frames: int = 5) -> dict[str, list[str]]:
        reads = []
        for _ in range(1 if self.image else frames):
            if self.image:
                frame = cv2.imread(self.image)
                if frame is None:
                    sys.exit(f'cannot read {self.image}')
            else:
                for _ in range(3):  # drop buffered frames so the read shows the table now
                    self.cap.grab()
                ok, frame = self.cap.read()
                if not ok:
                    sys.exit('camera returned no frame')
            reads.append(split_table(self.reader.detect(frame), self.split))
        return vote(reads)


def show(sides: dict[str, list[str]]) -> None:
    for side in ('dealer', 'player'):
        t, soft = hand.total(sides[side]) if sides[side] else (0, False)
        print(f'  {side:6}: {" ".join(sides[side]) or "-":20} {"soft " if soft else ""}{t}')


class Game:
    def __init__(self, table: Table, station):
        self.table, self.station = table, station
        self.sides = {'dealer': [], 'player': []}

    def deal(self, to: str) -> None:
        if self.station is None:
            input(f'Deal one card face up to the {to}, then press Enter ')
        else:
            print(f'Dream-1: "{PROMPTS[to]}"')
            self.station.run(PROMPTS[to])
        want = len(self.sides[to]) + 1
        while True:
            seen = self.table.read()
            if len(seen[to]) == want and all(c in seen[to] for c in self.sides[to]):
                new = next(c for c in seen[to] if c not in self.sides[to])
                self.sides[to].append(new)
                print(f'  {to} got {new}')
                return
            print(f'  expected {want} {to} card(s), camera sees {seen[to] or "none"}')
            fix = input('  Enter to read again, or type the card (e.g. 10H): ').strip().upper()
            if fix:
                self.sides[to].append(fix)
                return

    def play(self) -> str:
        self.deal('player')
        self.deal('dealer')
        self.deal('player')
        show(self.sides)
        p = self.sides['player']
        if not hand.is_blackjack(p):
            while not hand.is_bust(p) and input('Hit or stand? [h/s] ').strip().lower().startswith('h'):
                self.deal('player')
                show(self.sides)
        if not hand.is_bust(p):
            while hand.dealer_hits(self.sides['dealer']):
                self.deal('dealer')
                show(self.sides)
        result = hand.outcome(p, self.sides['dealer'])
        print({'player': 'You win!', 'dealer': 'Dealer wins.', 'push': 'Push.'}[result])
        return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=('read', 'play'))
    ap.add_argument('--camera', type=int, default=0, help='OpenCV camera index of the top-down camera')
    ap.add_argument('--image', help='read this photo instead of a camera (read mode)')
    ap.add_argument('--split', type=float, default=0.5, help='dealer/player line, fraction of image height')
    ap.add_argument('--station', help='dreamlabs station URL; without it a person deals')
    args = ap.parse_args()
    table = Table(args)
    if args.mode == 'read':
        show(table.read())
        return
    from station import Station
    station = Station(args.station) if args.station else None
    if station is not None:
        print('station:', station.status()['state'])
    try:
        Game(table, station).play()
    except KeyboardInterrupt:
        if station is not None:
            station.stop()
            time.sleep(0.2)
        print('\nstopped')


if __name__ == '__main__':
    main()
