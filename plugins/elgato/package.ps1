param(
    [Parameter(Mandatory)][string]$ExePath,
    [Parameter(Mandatory)][string]$OutputDir
)
$ErrorActionPreference = 'Stop'
$executable = (Get-Item -LiteralPath $ExePath).FullName
$output = (New-Item -ItemType Directory -Force -Path $OutputDir).FullName
$manifest = Get-Content -LiteralPath "$PSScriptRoot/manifest.json" -Raw | ConvertFrom-Json
$staging = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString('N'))
$plugin = Join-Path $staging "$($manifest.UUID).sdPlugin"
try {
    $bin = (New-Item -ItemType Directory -Force -Path "$plugin/bin").FullName
    Copy-Item -LiteralPath "$PSScriptRoot/manifest.json" -Destination $plugin
    Copy-Item -LiteralPath "$PSScriptRoot/images" -Destination $plugin -Recurse
    Copy-Item -LiteralPath $executable -Destination "$bin/AG03Toggle.exe"
    $compiler = Join-Path $env:SystemRoot 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    $hostSource = Join-Path $PSScriptRoot 'DeckHost.cs'
    $hostExe = Join-Path $bin 'DeckHost.exe'
    & $compiler /nologo /optimize+ /target:winexe /platform:x64 /r:System.Web.Extensions.dll "/out:$hostExe" $hostSource
    if ($LASTEXITCODE -ne 0) { throw "Could not compile the Stream Deck host." }
    & npx.cmd --yes --package=@elgato/cli@1.10.5 streamdeck pack $plugin --output $staging --no-update-check --no-file-list
    if ($LASTEXITCODE -ne 0) { throw "Elgato validation or packaging failed." }
    $name = "$($manifest.UUID).streamDeckPlugin"
    Copy-Item -LiteralPath (Join-Path $staging $name) -Destination (Join-Path $output $name) -Force
}
finally {
    if ((Split-Path -Parent $staging) -eq ([IO.Path]::GetTempPath()).TrimEnd('\','/') -and
        (Split-Path -Leaf $staging) -match '^[0-9a-f]{32}$' -and (Test-Path -LiteralPath $staging)) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}
