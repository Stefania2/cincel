$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$url = "http://127.0.0.1:8000/"

function Get-CincelProcess {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -match '^python(\.exe)?$' -and
            $_.CommandLine -match 'server\.py' -and
            $_.CommandLine -match [regex]::Escape($projectDir)
        } |
        Select-Object -First 1
}

try {
    $python = Get-Command python -ErrorAction Stop
} catch {
    Write-Host "No se encontro Python en este equipo. Instala Python o abre Cincel desde un equipo donde ya funcione."
    exit 1
}

$existing = Get-CincelProcess
if (-not $existing) {
    Start-Process $python.Source -ArgumentList "server.py" -WorkingDirectory $projectDir -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 2
}

Start-Process $url
