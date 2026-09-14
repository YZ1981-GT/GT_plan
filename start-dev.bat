@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>nul
title GT Dev Launcher

REM ============================================================
REM  ASCII-ONLY FILE. DO NOT ADD CJK / EMOJI / BOX-DRAWING CHARS.
REM  Reason: with `chcp 65001`, cmd.exe seeks back into this file
REM  by CHARACTER count while the file is stored in BYTES. Any
REM  multi-byte char inside a `( ... )` block desyncs the file
REM  pointer on every loop iteration, so cmd resumes mid-line and
REM  executes comment fragments as commands. Symptom:
REM      '<garbage>' is not recognized as an internal or external command
REM  printed between the [n/5] step banners.
REM  Rationale in Chinese: docs/runbooks/start-dev-launcher-notes.md
REM  A guard test enforces ASCII: backend/tests/test_start_dev_bat_ascii.py
REM ============================================================

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

REM --- pre-checks ---------------------------------------------
if not exist "%BACKEND_DIR%\app\main.py" ( echo [ERROR] Backend not found & exit /b 1 )
if not exist "%FRONTEND_DIR%\package.json" ( echo [ERROR] Frontend not found & exit /b 1 )
if not exist "%FRONTEND_DIR%\node_modules" ( echo [ERROR] Run "npm install" first & exit /b 1 )
if not exist "%DSH_DIR%\apps\cli\lib\bin.js" ( echo [WARN] DSH not found at %DSH_DIR%, AI panel will be unavailable. )

set "PY="
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" set "PY=%ROOT_DIR%\.venv\Scripts\python.exe"
if "%PY%"=="" if exist "%BACKEND_DIR%\.venv\Scripts\python.exe" set "PY=%BACKEND_DIR%\.venv\Scripts\python.exe"
if "%PY%"=="" ( where python >nul 2>nul && set "PY=python" )
if "%PY%"=="" ( echo [ERROR] Python not found & exit /b 1 )

REM --- git mode -----------------------------------------------
if not defined GIT_MODE set "GIT_MODE=single"
echo [GT] GIT_MODE=%GIT_MODE% ^(single=solo fast lane / multi=strict PR^)
if "%GIT_MODE%"=="multi" echo [GT] multi mode: direct push to main is rejected, PR required.


echo.
echo  ======================================
echo    GT Audit Platform - Dev Launcher
echo  ======================================
echo.

REM --- [1/5] kill old processes -------------------------------
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

REM --- [2/5] start backend ------------------------------------
REM NOTE on the --reload-exclude globs below: the quotes around them do NOT
REM survive this `start ... cmd /k "..."` nesting. They reach uvicorn bare, and
REM uvicorn's CLI is a click command that expands argv globs against the CWD on
REM Windows (click's windows_expand_args, on by default). `tmp_*` then becomes
REM 69 filenames from backend/ and the backend dies with:
REM     Error: Got unexpected extra arguments (tmp_check_resolve.py tmp_...)
REM Fixed on the Python side once, for every caller:
REM     backend/run_uvicorn.py -> main(windows_expand_args=False)
REM Guard: backend/tests/test_run_uvicorn_argv_glob_guard.py
REM Do NOT "fix" this by deleting tmp_* files; *.json would trip it next.
echo [2/5] Starting backend on :%BACKEND_PORT% ...
start "%BACKEND_TITLE%" /min cmd /k "title %BACKEND_TITLE% && cd /d "%BACKEND_DIR%" && "%PY%" run_uvicorn.py app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload --reload-dir app --reload-delay 2.0 --reload-exclude "*.pyc" --reload-exclude "__pycache__" --reload-exclude ".hypothesis" --reload-exclude "*.json" --reload-exclude "tmp_*" --log-level warning"

REM --- [3/5] wait for backend ---------------------------------
REM 60s not 30s: MigrationRunner runs every V*.sql on boot (153+ files)
REM plus a schema drift check. Cold start measured above 30s, and a 30s
REM cap prints a misleading [WARN] Backend not responding while
REM /api/health actually returns 200 a moment later.
echo [3/5] Waiting for backend health (max 60s, migrations may take 20-40s)...
<nul set /p ".=      "
set "READY=0"
for /L %%i in (1,1,60) do (
  if !READY!==0 (
    REM Health probe MUST use 127.0.0.1, never localhost. See notes doc.
    REM uvicorn binds 0.0.0.0 = IPv4 only, nothing on ::1. On Windows
    REM localhost resolves ::1 first, so with -TimeoutSec 1 the probe
    REM always times out in the IPv6 phase regardless of backend health.
    REM Measured: localhost 2053ms / 127.0.0.1 16ms / [::1] refused.
    powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%BACKEND_PORT%/api/health' -TimeoutSec 1 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
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
  echo       [WARN] Backend not responding after 60s. Check the %BACKEND_TITLE% window.
)

REM --- [3.5] DSH SDK runtime check ----------------------------
REM dsh-agent-panel-integration Task 30: launcher no longer starts DSH Web UI for iframe.
REM DSH Agent runs via platform backend DshEngine (per-run subprocess), no standalone Web UI needed.
REM Only check SDK vendor dir existence as a dev hint.
REM Parens inside an if-block echo MUST be escaped as ^( ^) - a bare `)`
REM closes the block early, leaving a stray `.` token, and cmd aborts the
REM whole script with `. was unexpected at this time.` (exit 255). That
REM happens at PARSE time, so [4/5] never runs: backend up, frontend dead.
if exist "%DSH_DIR%\python\sdk-runtime" (
  echo [3.5] DSH SDK runtime detected at %DSH_DIR% ^(vendor read-only^).
  echo       DSH Agent runs via platform backend DshEngine ^(per-run subprocess^).
) else (
  echo [3.5] DSH SDK not found at %DSH_DIR% - DSH Agent unavailable ^(native engine only^).
)

REM --- [4/5] start frontend -----------------------------------
echo [4/5] Starting frontend on :%FRONTEND_PORT% ...
REM Use 127.0.0.1 for the API base: backend listens IPv4 only.
start "%FRONTEND_TITLE%" /min cmd /k "title %FRONTEND_TITLE% && cd /d "%FRONTEND_DIR%" && set VITE_API_BASE_URL=http://127.0.0.1:%BACKEND_PORT% && set VITE_DSH_URL=http://127.0.0.1:%DSH_PORT% && set VITE_DEV_PORT=%FRONTEND_PORT% && npm run dev"

REM --- [5/5] wait for frontend --------------------------------
echo [5/5] Waiting for frontend (max 15s)...
<nul set /p ".=      "
set "FE_READY=0"
for /L %%i in (1,1,15) do (
  if !FE_READY!==0 (
    REM This one MUST stay localhost. Do NOT "fix" it to 127.0.0.1 for
    REM symmetry with [3/5] - the two sides use opposite address families
    REM on purpose: backend uvicorn 0.0.0.0 is IPv4-only, while vite's
    REM default host resolves localhost to ::1 and listens IPv6-only.
    REM Measured: localhost 49ms / 127.0.0.1:3030 cannot connect.
    REM Known limit: open the UI via localhost:3030, not 127.0.0.1:3030.
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

REM --- done ---------------------------------------------------
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
