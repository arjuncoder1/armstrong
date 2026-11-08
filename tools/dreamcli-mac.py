"""dreamcli on macOS with candleLight USB-CAN adapters (Maker Arm v1 / Metal over `gs_usb:<serial>`).

Dream's `robots` driver only opens Linux SocketCAN links (`can0`), so on a Mac `dreamcli setup` refuses
`gs_usb:<serial>`. This launcher runs the real dreamcli with two in-memory patches (nothing installed is modified):
  1. config: accept `gs_usb:<serial>` as an arm's `can_channel`;
  2. driver: open `gs_usb:` channels with portal-makermods' macOS USB transport (utils/gs_usb_transport.py,
     the same code `uv run main.py robot` uses), everything else as before.

    uv run tools/dreamcli-mac.py setup          # wizard; enter can_channel as gs_usb:<serial>
    uv run tools/dreamcli-mac.py robot up       # any dreamcli command
    uv run main.py robot --list-adapters        # find the serials (no motor contact)

Close MakerMods Lab first: only one program can hold an adapter.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "thirdparty" / "portal-makermods" / "src"))  # utils.gs_usb_transport

import robots.config as config  # noqa: E402
import robots.robstride as robstride  # noqa: E402
from robots.cli import main  # noqa: E402

PREFIX = "gs_usb:"


def _read_can_channel(section, key):
    return config._read_str(section, "can_channel", key)  # gs_usb:<serial> allowed: opened by the transport below


_open_driver_bus = robstride.open_can_bus


def clean(channel):
    """`gs_usb:<serial>` with stray paste junk removed (trailing ')', quotes, spaces)."""
    if not channel.startswith(PREFIX):
        return channel
    serial = "".join(c for c in channel[len(PREFIX):] if c.isalnum())
    return PREFIX + serial


def open_can_bus(channel):
    channel = clean(channel)
    if channel.startswith(PREFIX):
        from utils.gs_usb_transport import open_gs_usb

        return open_gs_usb(channel)
    return _open_driver_bus(channel)


config._read_can_channel = _read_can_channel
robstride.open_can_bus = open_can_bus

if __name__ == "__main__":
    sys.exit(main())
