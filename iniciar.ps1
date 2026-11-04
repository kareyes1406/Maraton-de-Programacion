# Inicia los dos microservicios (Windows PowerShell). Uso: .\iniciar.ps1
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
  python -m venv (Join-Path $PSScriptRoot ".venv")
  & $py -m pip install -r (Join-Path $PSScriptRoot "requirements.txt")
}
Start-Process $py -ArgumentList "-m uvicorn auth_service.main:app --port 8001" -WorkingDirectory $PSScriptRoot
Start-Process $py -ArgumentList "-m uvicorn rutas_service.main:app --port 8000" -WorkingDirectory $PSScriptRoot
Start-Sleep 3
Start-Process "http://localhost:8000/"
