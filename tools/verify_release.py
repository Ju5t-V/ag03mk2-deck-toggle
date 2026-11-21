"""Check the three public downloads against the Windows app built alongside them."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from zipfile import ZipFile


def digest(stream):
    return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(dist):
    with (dist / "AG03Toggle.exe").open("rb") as stream:
        expected = digest(stream)
    macro = "AG03Toggle-Windows-x64.zip"
    elgato = "com.ju5tv.ag03mk2.streamDeckPlugin"
    ulanzi = "com.ulanzi.ulanzistudio.ag03toggle.ulanziPlugin.zip"
    for name in (macro, elgato, ulanzi):
        with ZipFile(dist / name) as archive:
            paths = archive.namelist()
            if len(set(paths)) != len(paths) or any(
                "\\" in p or PurePosixPath(p).is_absolute() or ".." in PurePosixPath(p).parts
                for p in paths
            ):
                raise ValueError(f"{name} contains ambiguous archive paths")
            if name == macro:
                launchers = ["AG03Toggle.exe", "Toggle Mute.exe", "Toggle Reverb.exe"]
            else:
                roots = [p for p in paths if len(PurePosixPath(p).parts) == 2
                         and p.endswith("/manifest.json")]
                if len(roots) != 1:
                    raise ValueError(f"{name} must have exactly one plugin manifest at the package root")
                manifest = json.loads(archive.read(roots[0]).decode("utf-8-sig"))
                folder = roots[0].split("/")[0]
                suffix = ".sdPlugin" if name == elgato else ".ulanziPlugin"
                if folder != manifest["UUID"] + suffix or folder + "/" + manifest["CodePath"] not in paths:
                    raise ValueError(f"{name} has a broken plugin entry point")
                if {a["Name"] for a in manifest["Actions"]} != {"Toggle Mute", "Toggle Reverb"}:
                    raise ValueError(f"{name} is missing a mixer action")
                launchers = [p for p in paths if PurePosixPath(p).name == "AG03Toggle.exe"]
                if len(launchers) != 1:
                    raise ValueError(f"{name} must bundle one copy of the mixer application")
            for launcher in launchers:
                with archive.open(launcher) as stream:
                    if digest(stream) != expected:
                        raise ValueError(f"{name}: {launcher} differs from the tested Windows app")
            bad_member = archive.testzip()
            if bad_member:
                raise ValueError(f"{name}: damaged archive member {bad_member}")
            print(f"Verified {name}")


if __name__ == "__main__":
    verify(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "dist")
