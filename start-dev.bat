@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>nul
title GT Dev Launcher

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "BACKEND_DIR=%ROOT_DIR%\backend"
set "FRONTEND_DIR=%ROOT_DIR%\audit-platform\frontend"
set "DSH_DIR=D:\DeepHorness"
set "BACKEND_PORT=9980"
set "FRONTEND_PORT=3030"
set "DSH_PORT=3080"
set "BACKEND_TITLE=GT-Backend-9980"
set "FRONTEND_TITLE=GT-Frontend-3030"
set "DSH_TITLE=GT-DSH-AI-3080"

:: ─── pre-checks ─────────────────────────────────────────────
if not exist "%BACKEND_DIR%\app\main.py" ( echo [ERROR] Backend not found & exit /b 1 )
if not exist "%FRONTEND_DIR%\package.json" ( echo [ERROR] Frontend not found & exit /b 1 )
if not exist "%FRONTEND_DIR%\node_modules" ( echo [ERROR] Run "npm install" first & exit /b 1 )
if not exist "%DSH_DIR%\apps\cli\lib\bin.js" ( echo [WARN] DSH not found at %DSH_DIR%, AI panel will be unavailable. )

set "PY="
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" set "PY=%ROOT_DIR%\.venv\Scripts\python.exe"
if "%PY%"=="" if exist "%BACKEND_DIR%\.venv\Scripts\python.exe" set "PY=%BACKEND_DIR%\.venv\Scripts\python.exe"
if "%PY%"=="" ( where python >nul 2>nul && set "PY=python" )
if "%PY%"=="" ( echo [ERROR] Python not found & exit /b 1 )

REM --- git mode ---
if not defined GIT_MODE set "GIT_MODE=single"
echo [GT] GIT_MODE=%GIT_MODE% (single=单用户快节奏 / multi=多用户严格 PR)
if "%GIT_MODE%"=="multi" echo [GT] 多用户模式：直推 main 拒绝，必走 PR


echo.
echo  ======================================
echo    GT Audit Platform - Dev Launcher
echo  ======================================
echo.

:: ─── [1/5] kill old processes ────────────────────────────────
echo [1/5] Stopping old processes...
taskkill /F /FI "WINDOWTITLE eq %BACKEND_TITLE%*" /T >nul 2>nul
taskkill /F /FI "WINDOWTITLE eq %FRONTEND_TITLE%*" /T >nul 2>nul
taskkill /F /FI "WINDOWTITLE eq %DSH_TITLE%*" /T >nul 2>nul
call :kill_port %BACKEND_PORT%
call :kill_port %FRONTEND_PORT%
call :kill_port %DSH_PORT%
timeout /t 1 /nobreak >nul
REM strictPort: vite exits if port is taken (no drift to 3031).
REM Port may linger after taskkill; wait explicitly.
call :wait_port_free %FRONTEND_PORT%
echo       Done.

:: ─── [2/5] start backend ─────────────────────────────────────
echo [2/5] Starting backend on :%BACKEND_PORT% ...
start "%BACKEND_TITLE%" /min cmd /k "title %BACKEND_TITLE% && cd /d "%BACKEND_DIR%" && "%PY%" run_uvicorn.py app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload --reload-dir app --reload-delay 2.0 --reload-exclude "*.pyc" --reload-exclude "__pycache__" --reload-exclude ".hypothesis" --reload-exclude "*.json" --reload-exclude "tmp_*" --log-level warning"

:: ─── [3/5] wait for backend ──────────────────────────────────
echo [3/5] Waiting for backend health (max 30s, typically 8-15s)...
<nul set /p ".=      "
set "READY=0"
for /L %%i in (1,1,30) do (
  if !READY!==0 (
    powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:%BACKEND_PORT%/api/health' -TimeoutSec 1 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
    if !errorlevel!==0 (
      set "READY=1"
      echo  OK
    ) else (
      <nul set /p ".=."
      timeout /t 1 /nobreak >nul
    )
  )
)
if !READY!==0 (
  echo.
  echo       [WARN] Backend not responding after 30s.
)

:: ─── [3.5] DSH SDK runtime check ───
REM dsh-agent-panel-integration Task 30: launcher no longer starts DSH Web UI for iframe.
REM DSH Agent runs via platform backend DshEngine (per-run subprocess), no standalone Web UI needed.
REM Only check SDK vendor dir existence as a dev hint.
if exist "%DSH_DIR%\python\sdk-runtime" (
  echo [3.5] DSH SDK runtime detected at %DSH_DIR% (vendor read-only).
  echo       DSH Agent runs via platform backend DshEngine (per-run subprocess).
) else (
  echo [3.5] DSH SDK not found at %DSH_DIR% — DSH Agent unavailable (native engine only).
)

:: ─── [4/5] start frontend ────────────────────────────────────
echo [4/5] Starting frontend on :%FRONTEND_PORT% ...
REM Use 127.0.0.1 instead of localhost: backend listens IPv4 only, localhost may try IPv6 first
start "%FRONTEND_TITLE%" /min cmd /k "title %FRONTEND_TITLE% && cd /d "%FRONTEND_DIR%" && set VITE_API_BASE_URL=http://127.0.0.1:%BACKEND_PORT% && set VITE_DSH_URL=http://127.0.0.1:%DSH_PORT% && set VITE_DEV_PORT=%FRONTEND_PORT% && npm run dev"

:: ─── [5/5] wait for frontend ─────────────────────────────────
echo [5/5] Waiting for frontend (max 15s)...
<nul set /p ".=      "
set "FE_READY=0"
for /L %%i in (1,1,15) do (
  if !FE_READY!==0 (
    powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:%FRONTEND_PORT%' -TimeoutSec 1 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
    if !errorlevel!==0 (
      set "FE_READY=1"
      echo  OK
    ) else (
      <nul set /p ".=."
      timeout /t 1 /nobreak >nul
    )
  )
)
if !FE_READY!==0 (
  echo.
  echo       [WARN] Frontend not responding.
)

:: ─── done ────────────────────────────────────────────────────
echo.
if !READY!==1 if !FE_READY!==1 (
  echo  +-------------------------------------+
  echo  ^|  [OK] ALL SERVICES STARTED          ^|
  echo  ^|                                     ^|
  echo  ^|  Backend:  http://localhost:%BACKEND_PORT%   ^|
  echo  ^|  Frontend: http://localhost:%FRONTEND_PORT%   ^|
  echo  ^|  DSH AI:   http://localhost:%DSH_PORT%   ^|
  echo  +-------------------------------------+
) else (
  echo  +-------------------------------------+
  echo  ^|  [WARN] SOME SERVICES NOT READY     ^|
  echo  ^|  Check minimized windows for errors.^|
  echo  ^|                                     ^|
  echo  ^|  Backend:  http://localhost:%BACKEND_PORT%   ^|
  echo  ^|  Frontend: http://localhost:%FRONTEND_PORT%   ^|
  echo  ^|  DSH AI:   http://localhost:%DSH_PORT%   ^|
  echo  +-------------------------------------+
)
echo.
exit /b 0

:kill_port
for /f %%P in ('powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; Get-NetTCPConnection -LocalPort %~1 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { $_ }"') do (
  taskkill /PID %%P /F >nul 2>nul
)
exit /b 0

:wait_port_free
REM Wait until the specified port has no listener (max ~4s).
REM After taskkill the socket may not release immediately;
REM vite with strictPort will exit if the port is still occupied.
REM Perf constraints:
REM   1. Polling must stay in one powershell invocation (bat for-loop restarts PS each iter ~2s)
REM   2. Cannot use Get-NetTCPConnection (CIM query, ~1.2s per call)
REM   3. Cannot use TcpListener bind (only binds one address family, may give false result)
REM GetActiveTcpListeners() is a pure .NET call (ms-level) returning all address families.
powershell -NoProfile -Command "$p=[System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties(); for ($i=0; $i -lt 20; $i++) { if (-not ($p.GetActiveTcpListeners() | Where-Object { $_.Port -eq %~1 })) { exit 0 }; Start-Sleep -Milliseconds 200 }; exit 1" >nul 2>nul
if not "!errorlevel!"=="0" echo       [WARN] Port %~1 still occupied, frontend may fail to start.
exit /b 0
