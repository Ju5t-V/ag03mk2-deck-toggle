param(
    [string]$Python = "python",
    [switch]$AppOnly
)

$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    & $Python -c "import sys, struct; sys.exit(0 if sys.platform == 'win32' and sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8 else 1)"
    if ($LASTEXITCODE -ne 0) { throw "Use 64-bit Python 3.12 for Windows." }

    $buildPython = Join-Path $PSScriptRoot ".venv-build\Scripts\python.exe"
    if (!(Test-Path -LiteralPath $buildPython)) {
        & $Python -m venv .venv-build
        if ($LASTEXITCODE -ne 0) { throw "Could not create the build environment." }
    }
    & $buildPython -m pip install --disable-pip-version-check --only-binary=:all: -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw "Could not install the build dependencies." }
    & $buildPython -c "import tkinter; import mido.backends.rtmidi; tkinter.Tcl()"
    if ($LASTEXITCODE -ne 0) { throw "Python needs Tcl/Tk support and the RtMidi backend." }

    $pythonLicense = & $buildPython -c "from pathlib import Path; import sys; print(Path(sys.base_prefix) / 'LICENSE.txt')"
    $bundlerArgs = @(
        "--noconfirm", "--clean", "--onefile", "--windowed", "--noupx", "--name", "AG03Toggle",
        "--specpath", "build", "--workpath", "build\work", "--distpath", "dist",
        "--add-data", "$PSScriptRoot\src\ag_reverb_capture.json;.",
        "--add-data", "${pythonLicense};licenses/Python",
        "--copy-metadata", "mido", "--copy-metadata", "python-rtmidi", "--copy-metadata", "packaging",
        "--hidden-import", "mido.backends.rtmidi", "--exclude-module", "frida",
        "$PSScriptRoot\src\ag03_app.py"
    )
    & $buildPython -m PyInstaller @bundlerArgs
    if ($LASTEXITCODE -ne 0) { throw "Could not build the standalone application." }

    # Exercise the packaged entry point and its embedded profile without a mixer.
    $previewFile = Join-Path $PSScriptRoot "build\preview.txt"
    $preview = Start-Process -FilePath "$PSScriptRoot\dist\AG03Toggle.exe" -PassThru `
        -ArgumentList "reverb", "on", "--preview" -WindowStyle Hidden `
        -RedirectStandardOutput $previewFile -RedirectStandardError "$PSScriptRoot\build\preview-error.txt"
    # Retain the process handle so Windows PowerShell can read the exit code.
    $null = $preview.Handle
    if (!$preview.WaitForExit(30000)) {
        $preview.Kill()
        throw "Packaged application preview timed out."
    }
    $profile = Get-Content -Raw -LiteralPath "src\ag_reverb_capture.json" | ConvertFrom-Json
    if ($preview.ExitCode -ne 0 -or (Get-Content -Raw -LiteralPath $previewFile).Trim() -ne $profile.frames.on) {
        throw "The packaged application failed its Reverb preview check."
    }

    $bundle = New-Item -ItemType Directory -Path "build\portable" -Force
    $names = @("AG03Toggle.exe", "Toggle Mute.exe", "Toggle Reverb.exe")
    $files = foreach ($name in $names) {
        $target = Join-Path $bundle.FullName $name
        Copy-Item -LiteralPath "dist\AG03Toggle.exe" -Destination $target -Force
        $target
    }
    Compress-Archive -LiteralPath $files -DestinationPath "dist\AG03Toggle-Windows-x64.zip" -Force
    if (!$AppOnly) {
        $exePath = (Get-Item -LiteralPath "dist\AG03Toggle.exe").FullName
        $outputDir = (Get-Item -LiteralPath "dist").FullName
        & "$PSScriptRoot\plugins\elgato\package.ps1" -ExePath $exePath -OutputDir $outputDir
        & "$PSScriptRoot\plugins\ulanzi\package.ps1" -ExePath $exePath -OutputDir $outputDir
    }
    Get-ChildItem -LiteralPath "dist" -File | Select-Object Name, Length
}
finally {
    Pop-Location
}
