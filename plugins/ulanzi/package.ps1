param(
    [Parameter(Mandatory)][string]$ExePath,
    [Parameter(Mandatory)][string]$OutputDir
)

$ErrorActionPreference = 'Stop'
$executable = (Get-Item -LiteralPath $ExePath).FullName
$output = (New-Item -ItemType Directory -Force -Path $OutputDir).FullName
$manifest = Get-Content -LiteralPath "$PSScriptRoot/manifest.json" -Raw | ConvertFrom-Json
$pluginName = "$($manifest.UUID).ulanziPlugin"
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$staging = Join-Path $tempRoot ([Guid]::NewGuid().ToString('N'))
$plugin = Join-Path $staging $pluginName
$npmCache = Join-Path $PSScriptRoot '../../build/npm-cache'
try {
    $bin = (New-Item -ItemType Directory -Path "$plugin/bin" -Force).FullName
    Copy-Item -LiteralPath @(
        "$PSScriptRoot/manifest.json", "$PSScriptRoot/package.json", "$PSScriptRoot/package-lock.json"
    ) -Destination $plugin
    Copy-Item -LiteralPath @("$PSScriptRoot/plugin", "$PSScriptRoot/images") -Destination $plugin -Recurse
    Copy-Item -LiteralPath $executable -Destination "$bin/AG03Toggle.exe"

    & npm.cmd ci --prefix $plugin --cache $npmCache --omit=dev --ignore-scripts --no-audit --no-fund --prefer-offline --fetch-retries=0
    if ($LASTEXITCODE -ne 0) { throw 'Could not bundle the WebSocket dependency for Ulanzi Studio.' }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = Join-Path $staging "$pluginName.zip"
    [IO.Compression.ZipFile]::CreateFromDirectory($plugin, $archive, [IO.Compression.CompressionLevel]::Optimal, $true)
    Copy-Item -LiteralPath $archive -Destination (Join-Path $output "$pluginName.zip") -Force
}
finally {
    if ((Split-Path -Parent $staging) -eq $tempRoot.TrimEnd('\','/') -and
        (Split-Path -Leaf $staging) -match '^[0-9a-f]{32}$' -and (Test-Path -LiteralPath $staging)) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}
