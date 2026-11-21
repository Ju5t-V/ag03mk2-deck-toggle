# AG03MK2 Deck Toggle

One-button **Mute** and **Reverb** for channel 1 of a Yamaha AG03MK2 on Windows. Works with Stream Deck, Ulanzi, macro pads and hotkeys. AG Controller doesn't need to be open.

## Download

Get the file for your setup from [Releases](https://github.com/Ju5t-V/ag03mk2-deck-toggle/releases/latest).

| I use | File | How |
|---|---|---|
| Elgato Stream Deck | `com.ju5tv.ag03mk2.streamDeckPlugin` | Double-click it, then drag **Toggle Mute** or **Toggle Reverb** onto a key. |
| Ulanzi Studio | `com.ulanzi.ulanzistudio.ag03toggle.ulanziPlugin.zip` | Import the ZIP in Ulanzi Studio, then assign the actions to keys. |
| Macro pad / hotkeys | `AG03Toggle-Windows-x64.zip` | Extract it, then bind **Toggle Mute.exe** or **Toggle Reverb.exe** to a key. |

If your macro tool supports arguments, run `AG03Toggle.exe mute toggle` or `AG03Toggle.exe reverb on`. Each control takes `on`, `off` or `toggle`. Opening `AG03Toggle.exe` without arguments shows a small control window.

> Mute only affects audio sent to the PC when the mixer is set to **INPUT MIX**. In **DRY CH 1-2G** mode it is bypassed.

## Build it yourself

Needs 64-bit Windows, Python 3.12 and Node.js.

```powershell
.\build.ps1
```

The three files are created in `dist/`. Pushing a tag like `v1.0.1` makes GitHub build them and publish a release.

## Disclaimer

Unofficial, not affiliated with Yamaha. Use at your own risk.
