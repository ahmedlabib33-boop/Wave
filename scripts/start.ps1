param([switch]$Lan)
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
function Invoke-Checked { param([scriptblock]$Command) & $Command; if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE)" } }
if (!(Test-Path '.venv')) { Invoke-Checked { py -3.12 -m venv .venv } }
Invoke-Checked { .\.venv\Scripts\python.exe -m pip install -e '.[vision,sar,test]' }
if (!(Test-Path '.env')) { Copy-Item '.env.example' '.env' }
New-Item -ItemType Directory -Force 'data' | Out-Null
Invoke-Checked { npm --prefix frontend ci --no-audit --no-fund }
Invoke-Checked { npm --prefix frontend run build }
Invoke-Checked { .\.venv\Scripts\alembic.exe upgrade head }
$nileHost = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
if ($Lan) {
  $nileIp = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1 -ExpandProperty IPAddress
  Write-Host "Nile Observer LAN: http://$($nileIp):8000. Share only on a trusted local network."
} else { Write-Host 'Nile Observer: http://127.0.0.1:8000.' }
Write-Host 'Token: data/access-token, unless APP_API_KEY is set.'
Invoke-Checked { .\.venv\Scripts\uvicorn.exe app.main:app --host $nileHost --port 8000 --ws-max-size 262144 }
