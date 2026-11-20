# AG03MK2 Deck Toggle

One-click control of the **Yamaha AG03MK2** mixer's channel 1 **Mute** and **Reverb** from a Stream Deck, Ulanzi deck, macro keypad, AutoHotkey, or anything else that can run a program.

The scripts send the same MIDI SysEx frames that Yamaha AG Controller sends, then wait for the mixer to acknowledge them. Toggle actions also read the mixer's live status first, so a button always flips the real state, even if you changed it on the hardware or in AG Controller.

> Windows only. Tested with AG Controller build `356033dc…` (SHA-256 checked by `ag_reverb.py`).

## Folder layout

```
AG03Toggle/
├── launchers/                 ← point your deck buttons at these
│   ├── Toggle Mute.cmd
│   ├── Mute ON.cmd
│   ├── Mute OFF.cmd
│   ├── Toggle Reverb.cmd
│   ├── Reverb ON.cmd
│   ├── Reverb OFF.cmd
│   └── _python.cmd            (helper: picks the Python interpreter)
├── src/
│   ├── ag_mute.py             CH1 mute on / off / toggle
│   ├── ag_reverb.py           CH1 reverb on / off / toggle / learn / ports
│   └── ag_reverb_capture.json captured reverb frames (made by "learn")
├── tools/
│   └── ag03_physical_mute_probe.py   research tool, not needed for normal use
└── requirements.txt
```

## Setup (once)

1. Install Python 3.10–3.12 from python.org (tick "Add to PATH").
2. Open PowerShell in this folder and create a virtual environment:

   ```powershell
   py -3.12 -m venv .venv
   ```

   ```powershell
   .\.venv\Scripts\python.exe -m pip install mido python-rtmidi
   ```

   Add `frida` only if you want to re-capture the reverb frames with `learn`.
3. Plug in the AG03MK2 and check the scripts can see it:

   ```powershell
   .\.venv\Scripts\python.exe src\ag_reverb.py ports
   ```

   You should see `Yamaha AG03MK2-1` for both input and output.
4. Try a dry run (prints the frame, sends nothing):

   ```powershell
   .\launchers\"Mute ON.cmd" --preview
   ```

### Which Python do the launchers use?

`launchers\_python.cmd` picks the first one it finds:

1. the `AG03_PYTHON` environment variable (full path to `python.exe`)
2. `.venv\Scripts\python.exe` inside this folder
3. `C:\ag03mk2-re\.venv\Scripts\python.exe`
4. `py -3` (the Windows Python launcher)

## What each launcher does

| Launcher | Effect | Needs AG Controller open? |
|---|---|---|
| `Toggle Mute.cmd` | Flips CH1 mute, confirms the new state | Yes, for live status |
| `Mute ON.cmd` / `Mute OFF.cmd` | Forces CH1 mute on / off | No |
| `Toggle Reverb.cmd` | Flips CH1 reverb, confirms the new state | Yes, for live status |
| `Reverb ON.cmd` / `Reverb OFF.cmd` | Forces CH1 reverb on / off | No |

The toggles read the mixer's status reports. If none arrive within 2 seconds you get `No live mixer status`. Open AG Controller (it can stay minimised) and try again. If you would rather not run AG Controller, use separate ON and OFF buttons, or a two-state button (see below).

Every launcher exits with code 0 on success and non-zero on failure, so deck software that shows an alert on failure will do so.

## Stream Deck (Elgato)

**Simple button (one action):**

1. In the Stream Deck app, open **System** and drag **Open** onto a key.
2. In **App / File**, browse to the launcher, e.g. `…\AG03Toggle\launchers\Toggle Mute.cmd`.
3. Give the key a title and icon. Done.

A console window flashes for a split second on each press. To hide it, point the key at a hidden launch instead:

- App / File: `C:\Windows\System32\conhost.exe`
- Arguments (via a plugin that supports them, such as **Advanced Launcher** or **BarRaider Windows Utils → Run**): `--headless "D:\path\to\AG03Toggle\launchers\Toggle Mute.cmd"`

**Two-state key (icon shows on/off):**

1. Install **Multi Action Switch** (built in) or BarRaider's **Advanced Launcher**.
2. State 1 action: `Mute ON.cmd`, red "MUTED" icon.
3. State 2 action: `Mute OFF.cmd`, green "LIVE" icon.

This does not need AG Controller, but the icon can drift if you also mute from the hardware button. Press once more to resync.

## Ulanzi Stream Deck (D200 / Ulanzi Studio)

1. Open **Ulanzi Studio**.
2. From the action list, drag **System → Open** (called "Open Application" or "Run Program" in some versions) onto a key.
3. Browse to the launcher, e.g. `launchers\Toggle Reverb.cmd`.
4. Set a title and icon and save.

For an on/off key, use Ulanzi's **Multi Action / Toggle** action with `Reverb ON.cmd` as state 1 and `Reverb OFF.cmd` as state 2.

If your Ulanzi Studio version can load Elgato plugins, the Stream Deck instructions above also apply.

## Macro keyboards and other decks

Anything that can "run a program" or "open a file" works. Point it at the `.cmd` file.

| Tool | How |
|---|---|
| **Razer Synapse** | Macro → Launch Program → pick the `.cmd` |
| **Logitech G HUB** | Assignments → System → Launch Application |
| **Corsair iCUE** | Actions → Launch Application |
| **SteelSeries GG** | Key binding → Launch Application |
| **VIA / QMK / ZMK keypads** | Bind the key to an unused combo (e.g. `Ctrl+Alt+F13`), then catch it with AutoHotkey below |
| **Loupedeck / Razer Stream Controller** | Actions → System → Run Application |
| **Touch Portal** | Action "Run Application", file = the `.cmd` |
| **Windows shortcut key** | Right-click the `.cmd` → Create shortcut → shortcut Properties → set **Shortcut key** |
| **Bitfocus Companion** | Use the "Generic: shell" or Vicreo Listener module to run the `.cmd` on this PC |

### AutoHotkey v2 example

```ahk
#Requires AutoHotkey v2
dir := "D:\path\to\AG03Toggle\launchers\"
^!F13::Run('"' dir 'Toggle Mute.cmd"',   , "Hide")   ; Ctrl+Alt+F13
^!F14::Run('"' dir 'Toggle Reverb.cmd"', , "Hide")   ; Ctrl+Alt+F14
```

### From a terminal or another script

```powershell
.\.venv\Scripts\python.exe src\ag_mute.py toggle
```

```powershell
.\.venv\Scripts\python.exe src\ag_reverb.py on
```

Add `--preview` to any `on`, `off` or `toggle` command to see what it would send without sending it.

## Re-capturing the reverb frames (`learn`)

`src\ag_reverb_capture.json` already holds the frames for the supported AG Controller build. You only need to re-learn them if they stop working:

1. `.\.venv\Scripts\python.exe -m pip install frida`
2. Open AG Controller and connect the mixer.
3. `.\.venv\Scripts\python.exe src\ag_reverb.py learn`
4. Click CH1 **Reverb** in AG Controller twice, a second apart.

The script attaches to AG Controller, records the two SysEx frames it sends, and saves them. It refuses to run if the installed AG Controller differs from the analysed build.

## Troubleshooting

| Message | Fix |
|---|---|
| `Expected one AG03MK2 port in this direction` | Mixer unplugged, or another app holds the MIDI port exclusively. Replug, close other MIDI apps. |
| `No live mixer status` | Toggle needs status reports. Open AG Controller, or use the ON / OFF launchers. |
| `Another mixer toggle is busy` | Two presses overlapped. Wait a second. |
| `No matching acknowledgement received` | The frame was sent once but the mixer didn't confirm. Check the mixer state, then press again. |
| `No module named mido` | The launcher picked a Python without the packages. Set `AG03_PYTHON` or create `.venv` as in Setup. |

## How it works (short version)

- Mute and reverb are switches on CH1, sent as 15-byte Yamaha SysEx frames (`F0 43 10 3E 1C 78 00 …`) to MIDI port `Yamaha AG03MK2-1`.
- The mixer answers each write with a 14-byte acknowledgement, which the scripts check.
- While AG Controller is running, the mixer streams 42-byte meter reports. Decoded byte 23 holds the switch flags (bit 0 = reverb, bit 5 = mute). Toggles read these to decide which way to flip, then wait for a report confirming the change.
- A named Windows mutex keeps rapid presses in order.

`tools\ag03_physical_mute_probe.py` was used to work this out. It logs MIDI traffic, the Windows capture mute flag and the input level side by side. It needs `ffmpeg` on PATH and Python 3.12 or older (it uses `audioop`).

## Disclaimer

Unofficial and not affiliated with Yamaha. Use at your own risk.
