@echo off
rem oc-monitor P4 startup: opencode serve (4096) + backend (4100) + frontend dev (5173) in 3 windows. Windows stay open with /k.
where opencode >nul 2>nul
if errorlevel 1 (
  echo [WARN] opencode not found in PATH. opencode serve [4096] will not start.
  echo [WARN] backend sync needs it (OPENCODE_BASE_URL=http://localhost:4096^). Install opencode and retry.
) else (
  netstat -ano | findstr /C:":4096 " >nul
  if not errorlevel 1 (
    echo [WARN] port 4096 already in use. opencode serve may already be running - reuse it.
    echo [WARN] Check with: netstat -ano ^| findstr :4096 (then reuse or stop it^)
  ) else (
    start "opencode serve" cmd /k cd /d "%~dp0" ^& opencode serve --port 4096 --hostname 127.0.0.1
  )
)
where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm not found in PATH. Install Node.js LTS and retry.
  echo [ERROR] frontend [5173] cannot start without npm.
  pause
  exit /b 1
)
netstat -ano | findstr /C:":4100 " >nul
if not errorlevel 1 (
  echo [WARN] port 4100 already in use. backend may already be running.
  echo [WARN] Check with: netstat -ano ^| findstr :4100 (then reuse or stop it^)
)
netstat -ano | findstr /C:":5173 " >nul
if not errorlevel 1 (
  echo [WARN] port 5173 already in use. frontend may already be running.
  echo [WARN] Check with: netstat -ano ^| findstr :5173 (then reuse or stop it^)
)
start "oc-monitor backend" cmd /k cd /d "%~dp0backend" ^& call ".venv\Scripts\activate.bat" ^& uvicorn app.main:app --port 4100
start "oc-monitor frontend" cmd /k cd /d "%~dp0frontend" ^& npm run dev -- --port 5173
echo started opencode-serve(4096) + backend(4100) + frontend(5173). Keep all windows open.
