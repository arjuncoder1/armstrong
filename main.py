"""Armstrong entry point. Run from the repo root so ./.env is loaded.

    uv run main.py                                   # voice agent, console mode
    uv run main.py voice connect --room portal-voice
    uv run main.py robot --parked                    # any portal-makermods peer, with its own args
    uv run main.py stack [--dream]                   # this Mac: local LiveKit + Manifest bridge + :8787/token
    uv run main.py control status                    # one-shot RPC to the rig (src/armstrong/control.py)

From code: `from armstrong.robot import MakerModsRobot` (see src/armstrong/robot.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from loguru import logger  # noqa: E402

from armstrong.utils import COMMANDS, load_env, run_peer, setup_logging  # noqa: E402


def main() -> None:
    args = sys.argv[1:]
    name = args.pop(0) if args and args[0] in COMMANDS else "voice"
    setup_logging(intercept=name != "voice")
    load_env()
    run_peer(name, args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("stopped")
