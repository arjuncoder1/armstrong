# Robot blackjack dealer

A top-down camera reads the cards. The dreamlabs station (`python -m robots.station`, YAM arms) deals them with Dream-1. The dealer gets no hole card, so every card the camera reads is face up. The dealer stands on all 17s.

## Setup

```bash
cd blackjack
uv sync
uv run python -c "from huggingface_hub import hf_hub_download; hf_hub_download('koolguy06/playing-cards','playing-cards.pt',local_dir='models')"
```

The model is [koolguy06/playing-cards](https://huggingface.co/koolguy06/playing-cards) (YOLOv8l, 52 classes, MIT). It is 88 MB, so it is not in git. Its pickle was checked and holds only torch and ultralytics layers.

## Run

```bash
uv run python dealer.py read --camera 0                 # check the camera reads the table
uv run python dealer.py play --camera 0                 # a person deals when told to (no arm moves)
uv run python dealer.py play --camera 0 --station http://127.0.0.1:8091   # Dream-1 deals
```

- Put the dealer's cards in the top half of the image and the player's cards in the bottom half. Use `--split` to move the line.
- After each deal the camera must see exactly one new card. If it doesn't, you can read again or type the card in (for example `10H`).
- The station is only sent `/start`, `/status` and `/stop`. Ctrl-C stops the run, and the arms hold.
- The deal prompts are in `PROMPTS` in `dealer.py`. Change them to whatever Dream-1 does well on the clay gripper: press down, twist, lift.

## Tests

```bash
uv run python -m unittest test_blackjack
```
