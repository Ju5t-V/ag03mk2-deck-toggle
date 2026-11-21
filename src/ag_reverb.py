"""Learn the AG03MK2 CH1 Reverb messages from Yamaha AG Controller and reuse them."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import sys
import tempfile
import time


PROFILE = Path(__file__).with_name("ag_reverb_capture.json")
APP = Path(r"C:\Program Files\Yamaha\AGController\AGController.exe")
APP_SHA256 = "356033dc70b59b198ffab96209ecc21ec82719ec8d266aad54bba8c379e68bc9"
PORT = "Yamaha AG03MK2-1"
REVERB_MASK = 0x01


def reverb_state(packet):
    if (len(packet) != 15 or packet[:2] != b"\xf0\x43"
            or packet[2] >> 4 != 1 or packet[3:7] != b"\x3e\x1c\x78\x00"
            or packet[7] > 127 or packet[8] > 63
            or packet[9:12] != b"\x30\x10\x00" or packet[13:] != b"\x00\xf7"):
        return None
    return {0: "off", 2: "on"}.get(packet[12])


# Read the resolved import of the running application. Querying the existing
# WinMM output handle identifies the port without opening it or issuing MIDI.
HOOK = r"""
'use strict';
const app = Process.mainModule;
const imp = app.enumerateImports().find(i => i.name === 'midiOutLongMsg');
if (!imp || !imp.slot) throw new Error('Cannot locate the application MIDI output import');
const dll = Process.getModuleByName('winmm.dll');
const getId = new NativeFunction(dll.getExportByName('midiOutGetID'),
                                 'uint', ['pointer', 'pointer']);
const getCaps = new NativeFunction(dll.getExportByName('midiOutGetDevCapsW'),
                                   'uint', ['size_t', 'pointer', 'uint']);
const destination = imp.slot.readPointer();
Interceptor.attach(destination, {
    onEnter(args) {
        const header = args[1];
        if (header.isNull() || header.add(Process.pointerSize).readU32() !== 15) return;
        const data = header.readPointer();
        if (data.isNull()) return;
        const packet = Array.from(new Uint8Array(data.readByteArray(15)));
        if (packet[0] !== 0xf0 || packet[1] !== 0x43) return;
        const id = Memory.alloc(4), caps = Memory.alloc(84);
        if (getId(args[0], id) || getCaps(id.readU32(), caps, 84)) return;
        this.record = {port: caps.add(8).readUtf16String(), packet: packet};
    },
    onLeave(ret) {
        if (this.record && ret.toUInt32() === 0) send(this.record);
    }
});
send({ready: true, path: app.path});
"""


def save_profile(packets):
    profile = {"application_sha256": APP_SHA256, "port": PORT,
               "frames": {state: packet.hex(" ") for state, packet in packets.items()}}
    with tempfile.NamedTemporaryFile("w", dir=PROFILE.parent, delete=False,
                                     encoding="utf-8") as output:
        tmp = Path(output.name)
        json.dump(profile, output, indent=2)
        output.write("\n")
    try:
        os.replace(tmp, PROFILE)
    finally:
        tmp.unlink(missing_ok=True)


def learn():
    import frida

    if hashlib.sha256(APP.read_bytes()).hexdigest() != APP_SHA256:
        raise ValueError("The installed controller differs from the version analyzed.")
    device = frida.get_local_device()
    matches = [p for p in device.enumerate_processes() if p.name.lower() == APP.name.lower()]
    if len(matches) != 1:
        raise ValueError("Open one copy of Yamaha AG Controller and connect it to the mixer.")
    # Verify the process image before attaching, including when names collide.
    from ctypes import WinDLL, byref, create_unicode_buffer, wintypes
    kernel = WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, wintypes.LPDWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, matches[0].pid)
    if not handle:
        raise OSError("Cannot inspect the controller process.")
    try:
        path = create_unicode_buffer(32768)
        size = wintypes.DWORD(len(path))
        if not kernel.QueryFullProcessImageNameW(handle, 0, path, byref(size)) or Path(path.value) != APP:
            raise ValueError("The running program is not the expected Yamaha AG Controller.")
    finally:
        kernel.CloseHandle(handle)
    events = queue.Queue()
    session = device.attach(matches[0].pid)
    try:
        session.on("detached", lambda *args: events.put({"error": "AG Controller disconnected."}))
        script = session.create_script(HOOK)
        def receive(message, data):
            events.put(message["payload"] if message["type"] == "send"
                       else {"error": message.get("description", "MIDI observer error")})
        script.on("message", receive)
        script.load()
        packets = {}
        deadline = time.monotonic() + 180
        while len(packets) < 2:
            try:
                event = events.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                raise ValueError("Timed out waiting for both Reverb states. Check the controller is online.") from None
            if "error" in event:
                raise ValueError(event["error"])
            if event.get("ready"):
                print("Listening. Click CH1 Reverb in AG Controller twice, a second apart.", flush=True)
                continue
            if event.get("port") == PORT:
                packet = bytes(event["packet"])
                state = reverb_state(packet)
                if state and state not in packets:
                    packets[state] = packet
                    print("Captured Reverb " + state.upper(), flush=True)
        if packets["on"][2] != packets["off"][2]:
            raise ValueError("Two device numbers observed. Profile was not saved.")
        save_profile(packets)
        print("Saved both exact controller frames to", PROFILE)
    finally:
        session.detach()


def load_packet(state):
    if not PROFILE.is_file():
        raise ValueError("No learned frames. Run learn while AG Controller is connected.")
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    if profile.get("port") != PORT or profile.get("application_sha256") != APP_SHA256:
        raise ValueError("The capture profile does not match this controller and MIDI port.")
    packet = bytes.fromhex(profile["frames"][state])
    if reverb_state(packet) != state:
        raise ValueError("The captured frame does not encode the requested Reverb state.")
    return packet


def port_name(names):
    matches = [name for name in names if re.fullmatch(re.escape(PORT) + r"(?: \d+)?", name)]
    if len(matches) != 1:
        raise ValueError("Expected one AG03MK2 port in this direction. Available: " + ", ".join(names))
    return matches[0]


def ack_status(reply, request):
    if (len(reply) != 14 or reply[:2] != request[:2]
            or reply[2] != (0x30 | (request[2] & 15)) or reply[3:10] != request[3:10]
            or reply[10] not in (0x10, 0x50) or reply[11] >= 128
            or reply[12] > 1 or reply[13] != 0xf7):
        return None
    return reply[11] | (reply[12] << 7)


def switch_flags(frame):
    if (len(frame) != 42 or frame[:7] != bytes.fromhex("f0 43 10 3e 1c 78 00")
            or frame[9:11] != b"\x41\x60" or frame[-1] != 0xf7):
        return None
    # Ten-meter reports pack the switch flags at decoded byte 23, LSB first.
    packed = sum(value << (7 * index) for index, value in enumerate(frame[11:-1]))
    if packed & 0xff != 10:
        return None
    return (packed >> (23 * 8)) & 0xff


@contextmanager
def toggle_lock():
    """Serialize deck presses so the next toggle reads the previous result."""
    import ctypes
    from ctypes import wintypes

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    api.CreateMutexW.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.ReleaseMutex.argtypes = api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.CreateMutexW(None, False, r"Local\YamahaAG03MK2DeckToggle")
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if api.WaitForSingleObject(handle, 5000) not in (0, 0x80):
            raise RuntimeError("Another mixer toggle is busy.")
        try:
            yield
        finally:
            api.ReleaseMutex(handle)
    finally:
        api.CloseHandle(handle)


def incoming_frames(inbox, since, timeout=2):
    deadline = since + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            stamp, frame = inbox.get(timeout=remaining)
        except queue.Empty:
            return
        if stamp >= since:
            yield frame


@contextmanager
def switch_reports(port, inbox):
    import mido

    # Preserve an existing stream, including one requested by AG Controller.
    for frame in incoming_frames(inbox, time.monotonic(), 0.35):
        flags = switch_flags(frame)
        if flags is not None:
            yield flags
            return

    start = bytes.fromhex("f0 43 10 3e 1c 78 00 4b 00 40 10 01 00 f7")
    stop = bytes.fromhex("f0 43 10 3e 1c 78 00 4c 00 40 10 00 00 f7")
    since = time.monotonic()
    port.send(mido.Message.from_bytes(start))
    try:
        flags = None
        acknowledged = False
        for frame in incoming_frames(inbox, since):
            status = ack_status(frame, start)
            if status not in (None, 0):
                raise ValueError(f"Mixer rejected the status request (status {status}).")
            if status == 0:
                acknowledged = True
            observed = switch_flags(frame)
            if observed is not None:
                flags = observed
            if acknowledged and flags is not None:
                yield flags
                return
        raise ValueError("No confirmed live mixer status received from the AG03MK2.")
    finally:
        cleanup_started = time.monotonic()
        try:
            port.send(mido.Message.from_bytes(stop))
            for frame in incoming_frames(inbox, cleanup_started, 0.75):
                if ack_status(frame, stop) == 0:
                    break
            else:
                print("Status-report stop was not confirmed.", file=sys.stderr)
        except (OSError, RuntimeError) as exc:
            print(f"Could not stop status reports: {exc}", file=sys.stderr)


@contextmanager
def live_switches():
    """Hold a single mixer session while reading or changing the CH1 controls."""
    import mido

    inbox = queue.Queue()
    def receive(message):
        inbox.put((time.monotonic(), bytes(message.bytes())))

    with (toggle_lock(),
          mido.open_input(port_name(mido.get_input_names()), callback=receive),
          mido.open_output(port_name(mido.get_output_names()), autoreset=False) as port,
          switch_reports(port, inbox) as flags):
        yield port, inbox, flags


def toggle_control(control, mask, get_packet, preview):
    import mido

    with live_switches() as (port, inbox, flags):
        turn_on = not bool(flags & mask)
        state = "on" if turn_on else "off"
        packet = get_packet(state)
        if preview:
            print(f"CH1 {control} would turn {state.upper()}.")
            return

        sent_at = time.monotonic()
        port.send(mido.Message.from_bytes(packet))
        acknowledged = False
        confirmed = False
        for frame in incoming_frames(inbox, sent_at):
            status = ack_status(frame, packet)
            if status is not None:
                if status != 0:
                    raise ValueError(f"Mixer returned status {status} for {control}.")
                acknowledged = True
            observed = switch_flags(frame)
            if observed is not None:
                flags = observed
                confirmed = bool(flags & mask) == turn_on
            if acknowledged and confirmed:
                print(f"CH1 {control} {state.upper()} confirmed.")
                return flags
        raise ValueError(f"Sent {control} {state.upper()} once. Mixer confirmation timed out.")


def send_captured(packet, state, control="Reverb"):
    import mido

    incoming = queue.Queue()
    input_port = port_name(mido.get_input_names())
    output_port = port_name(mido.get_output_names())
    with mido.open_input(input_port, callback=incoming.put):
        with mido.open_output(output_port, autoreset=False) as port:
            port.send(mido.Message.from_bytes(packet))
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                try:
                    msg = incoming.get(timeout=max(0.001, deadline - time.monotonic()))
                except queue.Empty:
                    break
                status = ack_status(bytes(msg.bytes()), packet)
                if status == 0:
                    print(f"Mixer acknowledged CH1 {control} {state.upper()}.")
                    return
                if status is not None:
                    raise ValueError(f"Mixer returned status {status} for {control} {state.upper()}.")
    raise ValueError("Frame sent once. No matching acknowledgement received; mixer state unconfirmed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["learn", "ports", "on", "off", "toggle"])
    parser.add_argument("--preview", action="store_true", help="print the learned frame without sending")
    args = parser.parse_args()
    if args.preview and args.action not in ("on", "off", "toggle"):
        parser.error("--preview applies to on, off or toggle")
    if args.action == "toggle":
        toggle_control("Reverb", REVERB_MASK, load_packet, args.preview)
        return
    if args.action == "learn":
        learn()
        return
    if args.action == "ports":
        import mido
        print("Input:", port_name(mido.get_input_names()))
        print("Output:", port_name(mido.get_output_names()))
        return
    packet = load_packet(args.action)
    if args.preview:
        print(packet.hex(" "))
        return
    send_captured(packet, args.action)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Stopped.")
    except (OSError, RuntimeError, ValueError, KeyError, ImportError) as exc:
        sys.exit(str(exc))
