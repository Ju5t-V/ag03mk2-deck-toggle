"""Observe the AG03MK2 MIDI input, Windows capture mute flag and audio level."""
import audioop
import collections
import ctypes as c
from ctypes import wintypes as w
import math
import re
import statistics
import subprocess
import sys
import threading
import time
import uuid
import winreg

import mido


def guid(value):
    return (c.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le)


def checked(hr):
    if hr < 0:
        raise OSError("Core Audio HRESULT 0x%08x" % (hr & 0xffffffff))


def call(obj, slot, *argtypes):
    table = c.cast(obj, c.POINTER(c.POINTER(c.c_void_p))).contents
    return c.WINFUNCTYPE(c.c_long, c.c_void_p, *argtypes)(table[slot])


def capture_endpoint_id():
    keys = []
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture") as root:
        for index in range(winreg.QueryInfoKey(root)[0]):
            key = winreg.EnumKey(root, index)
            with winreg.OpenKey(root, key) as dev:
                if winreg.QueryValueEx(dev, "DeviceState")[0] != 1:
                    continue
                with winreg.OpenKey(dev, "Properties") as props:
                    if any(winreg.EnumValue(props, j)[1] == "Yamaha AG03MK2" for j in range(winreg.QueryInfoKey(props)[1])):
                        keys.append(key)
    if len(keys) != 1:
        raise ValueError("Expected one active Yamaha AG03MK2 audio endpoint")
    return "{0.0.1.00000000}." + keys[0]


def windows_mute_changes(changes, elapsed, stop):
    ptr = c.c_void_p
    try:
        ole = c.OleDLL("ole32")
        ole.CoInitializeEx(None, 0)
        enum, dev, vol = ptr(), ptr(), ptr()
        checked(ole.CoCreateInstance(c.byref(guid("BCDE0395-E52F-467C-8E3D-C4579291692E")), None, 1, c.byref(guid("A95664D2-9614-4F35-A746-DE8DB63617E6")), c.byref(enum)))
        checked(call(enum, 5, w.LPCWSTR, c.POINTER(ptr))(enum, capture_endpoint_id(), c.byref(dev)))
        checked(call(dev, 3, ptr, w.DWORD, ptr, c.POINTER(ptr))(dev, c.byref(guid("5CDF2C82-841E-4546-9722-0CF74078229A")), 23, None, c.byref(vol)))
        get = call(vol, 15, c.POINTER(w.BOOL))
        while not stop.is_set():
            value = w.BOOL()
            checked(get(vol, c.byref(value)))
            if not changes or changes[-1][1] != value.value:
                changes.append((elapsed(), value.value))
            stop.wait(0.1)
    except Exception as err:
        print("Windows mute flag unavailable:", err, flush=True)


def main():
    clock = time.monotonic()
    elapsed = lambda: round(time.monotonic() - clock, 2)
    levels, flags, events = collections.defaultdict(list), [], []
    stop = threading.Event()
    inputs = [p for p in mido.get_input_names() if re.fullmatch(r"Yamaha AG03MK2-1(?: \d+)?", p)]
    if len(inputs) != 1:
        sys.exit("Expected one Yamaha MIDI input.")
    devices = subprocess.run(["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"], capture_output=True).stderr.decode(errors="replace")
    names = re.findall(r'"([^"]*Yamaha AG03MK2[^"]*)" \(audio\)', devices, re.I)
    if len(names) != 1:
        sys.exit("Expected one Yamaha DirectShow audio input.")
    def audio(proc):
        while data := proc.stdout.read(3200):
            levels[int(elapsed())].append(audioop.rms(data, 2))
    def summary():
        groups = []
        for second, vals in sorted(levels.copy().items()):
            db = round(20 * math.log10(max(1, statistics.median(vals)) / 32768), 1)
            if groups and groups[-1][1] == second-1 and (groups[-1][2][0] <= -85) == (db <= -85):
                groups[-1][1] = second
                groups[-1][2].append(db)
            else:
                groups.append([second,second,[db]])
        print("Elapsed", elapsed(), "Windows mute changes", flags)
        print("Levels (start, end, median dBFS)", [(a,b,round(statistics.median(v),1)) for a,b,v in groups][-40:])
        print("Recent levels (second, dBFS)", [(k,round(20*math.log10(max(1,statistics.median(v))/32768),1)) for k,v in sorted(levels.copy().items())[-35:]])
        midi = collections.defaultdict(list)
        for t, b in events.copy():
            midi[(len(b), b[:7] if b[0] == 240 else b[:1], b[9:11])].append((t,b))
        print("MIDI events:", len(events))
        for (length, header, op), rows in sorted(midi.items(), key=lambda item:-len(item[1]))[:30]:
            bodies = collections.Counter(b[11:-1] if b[0]==240 else b for t,b in rows)
            print("MIDI group", length, header.hex(), op.hex(), "count", len(rows), "variants",len(bodies), "times", [t for t,b in rows] if len(rows)<=16 else [rows[0][0],rows[-1][0]], "common data", [(b[:12].hex(),n) for b,n in bodies.most_common(4)])
            if (length,header,op) == (42, bytes.fromhex("f0 43 10 3e 1c 78 00"), bytes.fromhex("41 60")):
                changes = collections.defaultdict(list)
                for t, packet in rows:
                    packed = sum(value << (i*7) for i,value in enumerate(packet[11:-1]))
                    decoded = packed.to_bytes(27,"little")[:26]
                    if decoded[0] != 10:
                        continue
                    for i in (1,22,23,24,25):
                        if not changes[i] or changes[i][-1][1] != decoded[i]:
                            changes[i].append((t, decoded[i]))
                for i, history in changes.items():
                    print("Decoded byte", i, "transitions", len(history)-1, "time/value",history[:24])
        print("END SUMMARY", flush=True)
    with mido.open_input(inputs[0], callback=lambda msg: events.append((elapsed(),bytes(msg.bytes())))):
        cmd = ["ffmpeg","-hide_banner","-nostdin","-loglevel","error","-f","dshow","-audio_buffer_size","100","-i","audio="+names[0],"-vn","-ar","16000","-ac","1","-f","s16le","pipe:1"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            threading.Thread(target=audio,args=(proc,),daemon=True).start()
            threading.Thread(target=windows_mute_changes,args=(flags,elapsed,stop),daemon=True).start()
            time.sleep(2)
            if proc.poll() is not None:
                sys.exit(proc.stderr.read().decode(errors="replace"))
            print("READY", names[0], inputs[0], "audio blocks",sum(map(len,levels.values())), "Windows mute flag",flags,flush=True)
            for command in sys.stdin:
                summary()
                if command.strip()=="end":
                    break
        finally:
            stop.set()
            proc.terminate()
            proc.wait()


if __name__ == "__main__":
    main()
