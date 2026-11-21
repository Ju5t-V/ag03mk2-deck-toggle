"""Set AG03MK2 channel 1 mute using the two hardware-tested switch 5 frames."""

import argparse
import sys

from ag_reverb import send_captured, toggle_control


MUTE_MASK = 0x20
FRAMES = {
    "on": bytes.fromhex("f0 43 10 3e 1c 78 00 49 00 30 10 05 02 00 f7"),
    "off": bytes.fromhex("f0 43 10 3e 1c 78 00 4a 00 30 10 05 00 00 f7"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", choices=["on", "off", "toggle"])
    parser.add_argument("--preview", action="store_true", help="show the frame without sending")
    args = parser.parse_args()
    if args.state == "toggle":
        toggle_control("Mute", MUTE_MASK, FRAMES.__getitem__, args.preview)
        return
    packet = FRAMES[args.state]
    if args.preview:
        print(packet.hex(" "))
    else:
        send_captured(packet, args.state, control="Mute")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, ImportError) as exc:
        sys.exit(str(exc))
