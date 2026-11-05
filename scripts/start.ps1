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
Write-Host 'Nile Observer: http://127.0.0.1:8000. Token: data/access-token, unless APP_API_KEY is set.'
Invoke-Checked { .\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --ws-max-size 262144 }
