"""Windows desktop and deck entry point for the Yamaha AG03MK2."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
from pathlib import Path
import sys

from ag_mute import FRAMES, MUTE_MASK
from ag_reverb import REVERB_MASK, live_switches, load_packet, send_captured, toggle_control, toggle_lock


TITLE = "AG03MK2 Deck Toggle"
CONTROLS = {
    "mute": ("Mute", MUTE_MASK, FRAMES.__getitem__),
    "reverb": ("Reverb", REVERB_MASK, load_packet),
}


def read_switches():
    with live_switches() as (_, _, flags):
        return flags


def run_action(control, action, preview):
    label, mask, get_packet = CONTROLS[control]
    if action == "toggle":
        return toggle_control(label, mask, get_packet, preview)
    packet = get_packet(action)
    if preview:
        print(packet.hex(" "))
    else:
        with toggle_lock():
            send_captured(packet, action, control=label)


def desktop():
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title(TITLE)
    root.minsize(370, 210)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    panel = ttk.Frame(root, padding=(20, 16))
    panel.grid(sticky="nsew")
    panel.columnconfigure((0, 1), weight=1, uniform="control")
    ttk.Label(panel, text="AG03MK2  ·  Channel 1", font=("Segoe UI", 13, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
    status = tk.StringVar(value="Reading mixer…")
    states = {}
    buttons = []

    def show_result(future):
        if not future.done():
            root.after(60, show_result, future)
            return
        try:
            flags = future.result()
        except Exception as exc:
            for indicator in states.values():
                indicator.set("Unknown")
            status.set(str(exc) or type(exc).__name__)
        else:
            for key, (_, mask, _) in CONTROLS.items():
                states[key].set("ON" if flags & mask else "OFF")
            status.set("Last checked " + datetime.now().strftime("%H:%M:%S"))
        for button in buttons:
            button.state(["!disabled"])

    def start(control=None):
        for button in buttons:
            button.state(["disabled"])
        if control is None:
            status.set("Reading mixer…")
            future = worker.submit(read_switches)
        else:
            status.set(f"Switching {CONTROLS[control][0].lower()}…")
            future = worker.submit(run_action, control, "toggle", False)
        root.after(60, show_result, future)

    for column, (key, (label, _, _)) in enumerate(CONTROLS.items()):
        card = ttk.LabelFrame(panel, text=label, padding=(10, 5, 10, 10))
        card.grid(row=1, column=column, sticky="nsew", padx=(0, 4) if column == 0 else (4, 0))
        card.columnconfigure(0, weight=1)
        states[key] = tk.StringVar(value="…")
        ttk.Label(card, textvariable=states[key], font=("Segoe UI", 16, "bold")).grid(pady=(2, 7))
        button = ttk.Button(card, text=f"Toggle {label.lower()}", command=lambda k=key: start(k))
        button.grid(sticky="ew")
        buttons.append(button)
    ttk.Label(panel, textvariable=status, wraplength=245).grid(row=2, column=0, columnspan=2,
                                                               sticky="w", padx=(0, 85), pady=(14, 0))
    refresh = ttk.Button(panel, text="Refresh", command=start)
    refresh.grid(row=2, column=1, sticky="e", pady=(14, 0))
    buttons.append(refresh)
    # Closing the window lets an in-flight command finish releasing its MIDI ports.
    with ThreadPoolExecutor(max_workers=1) as worker:
        start()
        root.mainloop()


def connect_cli_output():
    """Recover redirected output or the calling terminal for a windowed Windows EXE."""
    if os.name != "nt" or sys.stdout is not None and sys.stderr is not None:
        return
    import ctypes as c
    from ctypes import wintypes
    import msvcrt
    import _winapi

    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetFileType.argtypes = [wintypes.HANDLE]
    for name, number in (("stdout", -11), ("stderr", -12)):
        if getattr(sys, name) is not None:
            continue
        handle = kernel.GetStdHandle(number)
        if handle and kernel.GetFileType(handle) in (1, 3):  # Disk file or pipe.
            process = _winapi.GetCurrentProcess()
            duplicate = _winapi.DuplicateHandle(process, handle, process, 0, False, 2)
            fd = msvcrt.open_osfhandle(duplicate, os.O_WRONLY)
            setattr(sys, name, os.fdopen(fd, "w", encoding="utf-8", errors="replace", line_buffering=True))
    if (sys.stdout is None or sys.stderr is None) and kernel.AttachConsole(-1):
        for name in ("stdout", "stderr"):
            if getattr(sys, name) is None:
                setattr(sys, name, open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1))


def notify(text, error=False):
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        print(text, file=stream)
    else:
        from ctypes import windll
        windll.user32.MessageBoxW(None, text, TITLE, 0x10 if error else 0x40)


class CommandParser(argparse.ArgumentParser):
    def print_help(self, file=None):
        notify(self.format_help().rstrip())

    def error(self, message):
        notify(f"{message}\n\n{self.format_usage().strip()}", error=True)
        raise SystemExit(2)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    filename = Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).stem.lower()
    aliases = {"toggle mute": "mute", "toggle reverb": "reverb"}
    if filename in aliases and args in ([], ["--preview"]):
        args[:0] = [aliases[filename], "toggle"]
    if not args:
        desktop()
        return 0

    connect_cli_output()
    parser = CommandParser(prog="AG03Toggle", description=__doc__)
    parser.add_argument("control", choices=CONTROLS)
    parser.add_argument("action", choices=("toggle", "on", "off"))
    parser.add_argument("--preview", action="store_true", help="preview the action without changing the setting")
    parser.add_argument("--quiet", action="store_true", help="return errors to the deck host without showing a dialog")
    command = parser.parse_args(args)
    try:
        if command.preview and sys.stdout is None:
            from contextlib import redirect_stdout
            from io import StringIO
            with redirect_stdout(StringIO()) as output:
                run_action(command.control, command.action, True)
            notify(output.getvalue().strip())
        else:
            run_action(command.control, command.action, command.preview)
    except (OSError, RuntimeError, ValueError, KeyError, ImportError) as exc:
        if not command.quiet or sys.stderr is not None:
            notify(str(exc), error=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
