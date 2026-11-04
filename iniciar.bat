@echo off
REM Inicia los dos microservicios. Doble clic o ejecutar: iniciar.bat
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno virtual e instalando dependencias...
  python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
start "auth-service :8001" ".venv\Scripts\python.exe" -m uvicorn auth_service.main:app --port 8001
start "rutas-service :8000" ".venv\Scripts\python.exe" -m uvicorn rutas_service.main:app --port 8000
timeout /t 4 /nobreak >nul
start "" "http://localhost:8000/"
