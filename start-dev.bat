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
REM  A guard test enforces ASCII: backend/tests/test_start_dev_bat_ascii_guard.py
REM ============================================================

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "BACKEND_DIR=%ROOT_DIR%\backend"
set "FRONTEND_DIR=%ROOT_DIR%\audit-platform\frontend"
set "BACKEND_PORT=9980"
set "FRONTEND_PORT=3030"
set "BACKEND_TITLE=GT-Backend-9980"
set "FRONTEND_TITLE=GT-Frontend-3030"

REM --- runtime mode -------------------------------------------
REM dev    = backend overlap reload + Vite HMR
REM stable = backend without reload + immutable built frontend
if not defined GT_RUNTIME_MODE (
  if "%GT_BACKEND_NO_RELOAD%"=="1" (
    set "GT_RUNTIME_MODE=stable"
  ) else (
    set "GT_RUNTIME_MODE=dev"
  )
)
if /I "%GT_RUNTIME_MODE%"=="dev" goto runtime_mode_ok
if /I "%GT_RUNTIME_MODE%"=="stable" goto runtime_mode_ok
echo [ERROR] GT_RUNTIME_MODE must be dev or stable, got "%GT_RUNTIME_MODE%".
exit /b 1
:runtime_mode_ok
echo [GT] GT_RUNTIME_MODE=%GT_RUNTIME_MODE%

REM --- pre-checks ---------------------------------------------
if not exist "%BACKEND_DIR%\app\main.py" ( echo [ERROR] Backend not found & exit /b 1 )
if not exist "%FRONTEND_DIR%\package.json" ( echo [ERROR] Frontend not found & exit /b 1 )
if not exist "%FRONTEND_DIR%\node_modules" ( echo [ERROR] Run "npm install" first & exit /b 1 )
where node >nul 2>nul
if errorlevel 1 ( echo [ERROR] Node.js not found in PATH & exit /b 1 )
where npm >nul 2>nul
if errorlevel 1 ( echo [ERROR] npm not found in PATH & exit /b 1 )

set "PY="
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" set "PY=%ROOT_DIR%\.venv\Scripts\python.exe"
if "%PY%"=="" if exist "%BACKEND_DIR%\.venv\Scripts\python.exe" set "PY=%BACKEND_DIR%\.venv\Scripts\python.exe"
if "%PY%"=="" (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
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

REM Stable mode builds before stopping the currently working snapshot.
set "VITE_API_BASE_URL=http://127.0.0.1:%BACKEND_PORT%"
set "VITE_DEV_PORT=%FRONTEND_PORT%"
if /I "%GT_RUNTIME_MODE%"=="stable" (
  echo [0/5] Building immutable frontend snapshot...
  call npm --prefix "%FRONTEND_DIR%" run build:runtime
  if errorlevel 1 (
    echo       [ERROR] Stable frontend build failed; existing services were not stopped.
    exit /b 1
  )
  echo       Done.
)

REM --- [1/5] kill old processes -------------------------------
echo [1/5] Stopping old processes...
call :kill_named_tree %BACKEND_TITLE%
call :kill_named_tree %FRONTEND_TITLE%
taskkill /F /FI "WINDOWTITLE eq %BACKEND_TITLE%*" /T >nul 2>nul
taskkill /F /FI "WINDOWTITLE eq %FRONTEND_TITLE%*" /T >nul 2>nul
call :kill_port %BACKEND_PORT%
call :kill_port %FRONTEND_PORT%
timeout /t 1 /nobreak >nul
REM Ports may linger after taskkill. Never start beside an unknown listener.
call :wait_port_free %BACKEND_PORT%
if errorlevel 1 exit /b 1
call :wait_port_free %FRONTEND_PORT%
if errorlevel 1 exit /b 1
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
REM GT_BACKEND_NO_RELOAD=1 starts the backend WITHOUT --reload (default unchanged).
REM Use it for online-edit acceptance and timing: every hot reload throws away the
REM in-process registration / parse caches, so the next OnlyOffice save pays the
REM cold cost again (measured 51s callback right after a reload).
REM Usage: in a cmd window run  set GT_BACKEND_NO_RELOAD=1  then run start-dev.bat
set "BACKEND_RELOAD_ARGS=--reload --reload-dir app --reload-delay 2.0 --reload-exclude "*.pyc" --reload-exclude "__pycache__" --reload-exclude ".hypothesis" --reload-exclude "*.json" --reload-exclude "tmp_*""
if "%GT_BACKEND_NO_RELOAD%"=="1" set "BACKEND_RELOAD_ARGS="
if /I "%GT_RUNTIME_MODE%"=="stable" set "BACKEND_RELOAD_ARGS="
if "%GT_BACKEND_NO_RELOAD%"=="1" echo       Hot reload OFF ^(GT_BACKEND_NO_RELOAD=1^): restart to pick up code changes.
if /I "%GT_RUNTIME_MODE%"=="stable" echo       Stable backend snapshot: restart to pick up code changes.
start "%BACKEND_TITLE%" /min cmd /k "title %BACKEND_TITLE% && cd /d "%BACKEND_DIR%" && "%PY%" run_uvicorn.py app.main:app --host 0.0.0.0 --port %BACKEND_PORT% %BACKEND_RELOAD_ARGS% --log-level warning"

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
    REM A 200 response can still be degraded. Only healthy is ready.
    powershell -NoProfile -NonInteractive -Command "$ProgressPreference='SilentlyContinue'; try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:%BACKEND_PORT%/api/health' -TimeoutSec 1; $s = if ($null -ne $r.data -and $null -ne $r.data.status) { [string]$r.data.status } else { [string]$r.status }; if ($s -eq 'healthy') { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>nul
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
  echo       [ERROR] Backend did not become healthy after 60s. Check the %BACKEND_TITLE% window.
)

REM --- [3.5] backend-managed DSH runtime --------------------
echo [3.5] DSH Agent is managed by the backend runtime.

REM --- [4/5] start frontend -----------------------------------
echo [4/5] Starting frontend on :%FRONTEND_PORT% ...
REM Set variables in the parent environment. Quoted SET syntax prevents trailing spaces.
set "VITE_API_BASE_URL=http://127.0.0.1:%BACKEND_PORT%"
set "VITE_DEV_PORT=%FRONTEND_PORT%"
if /I "%GT_RUNTIME_MODE%"=="stable" (
start "%FRONTEND_TITLE%" /min cmd /k "title %FRONTEND_TITLE% && cd /d "%FRONTEND_DIR%" && npm run preview:stable"
) else (
start "%FRONTEND_TITLE%" /min cmd /k "title %FRONTEND_TITLE% && cd /d "%FRONTEND_DIR%" && npm run dev -- --host 0.0.0.0 --port %FRONTEND_PORT%"
)

REM --- [5/5] wait for frontend --------------------------------
echo [5/5] Waiting for frontend (max 15s)...
<nul set /p ".=      "
set "FE_READY=0"
for /L %%i in (1,1,15) do (
  if !FE_READY!==0 (
    REM Vite is explicitly bound to 0.0.0.0 above. Probe IPv4 loopback so the
    REM launcher also works when Windows IPv6 loopback is disabled or broken.
    REM Keep ProgressPreference silent: Invoke-WebRequest progress is a host stream
    REM and can leak through redirection as garbled terminal control output.
    powershell -NoProfile -NonInteractive -Command "$ProgressPreference='SilentlyContinue'; try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%FRONTEND_PORT%' -TimeoutSec 1 -UseBasicParsing; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
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
  echo       [ERROR] Frontend not responding.
)

REM --- done ---------------------------------------------------
echo.
set "LAUNCH_EXIT=0"
if "!READY!!FE_READY!"=="11" (
  echo  +-------------------------------------+
  echo  ^|  [OK] ALL SERVICES STARTED          ^|
  echo  ^|                                     ^|
  echo  ^|  Backend:  http://127.0.0.1:%BACKEND_PORT%   ^|
  echo  ^|  Frontend: http://127.0.0.1:%FRONTEND_PORT%   ^|
  echo  +-------------------------------------+
) else (
  set "LAUNCH_EXIT=1"
  echo  +-------------------------------------+
  echo  ^|  [ERROR] SOME SERVICES NOT READY    ^|
  echo  ^|  Check minimized windows for errors.^|
  echo  ^|                                     ^|
  echo  ^|  Backend:  http://127.0.0.1:%BACKEND_PORT%   ^|
  echo  ^|  Frontend: http://127.0.0.1:%FRONTEND_PORT%   ^|
  echo  +-------------------------------------+
)
echo.
exit /b !LAUNCH_EXIT!

:kill_named_tree
REM Elevated cmd windows prefix the visible title with "Administrator:". WINDOWTITLE
REM filtering then misses the reload supervisor, and killing only the listening worker
REM lets that supervisor immediately respawn stale settings. Kill the tagged cmd tree by
REM command line first; exclude this helper PowerShell process itself.
powershell -NoProfile -NonInteractive -Command "$tag='%~1'; Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like ('*' + $tag + '*') } | ForEach-Object { & taskkill.exe /PID $_.ProcessId /F /T | Out-Null }" >nul 2>nul
exit /b 0

:kill_port
REM Kill only orphaned reload workers whose recorded socket owner is already dead.
REM Tagged live process trees are stopped by :kill_named_tree above. Any remaining
REM live listener is treated as unknown; :wait_port_free aborts instead of killing it.
REM netstat is required because Get-NetTCPConnection can collapse duplicate binds.
powershell -NoProfile -NonInteractive -Command "$port = %~1; $ids = @(netstat -ano | Select-String -Pattern ('^\s*TCP\s+\S+:' + $port + '\s+\S+\s+LISTENING\s+(\d+)\s*$') | ForEach-Object { [int]$_.Matches[0].Groups[1].Value } | Where-Object { $_ -gt 4 } | Select-Object -Unique); if ($ids.Count -eq 0) { exit 0 }; $dead = @($ids | Where-Object { -not (Get-Process -Id $_ -ErrorAction SilentlyContinue) }); $orphans = @(Get-CimInstance Win32_Process | Where-Object { $cl = [string]$_.CommandLine; $hit = $false; foreach ($o in $dead) { if ($cl -like ('*spawn_main(parent_pid=' + $o + ',*')) { $hit = $true } }; $hit } | Select-Object -ExpandProperty ProcessId); foreach ($p in @($orphans | Select-Object -Unique)) { & taskkill.exe /PID $p /F /T 2>$null | Out-Null }" >nul 2>nul
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
set "WAIT_RESULT=!errorlevel!"
if not "!WAIT_RESULT!"=="0" echo       [ERROR] Port %~1 is still occupied; refusing to start.
exit /b !WAIT_RESULT!
