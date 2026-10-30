@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>nul
title SW Dev Launcher

REM ============================================================
REM  ASCII-ONLY FILE. DO NOT ADD CJK / EMOJI / BOX-DRAWING CHARS.
REM  Same constraint as start-dev.bat: with `chcp 65001`, cmd.exe
REM  seeks back into this file by CHARACTER count while the file is
REM  stored in BYTES. Any multi-byte char inside a `( ... )` block
REM  desyncs the file pointer and cmd executes comment fragments.
REM ============================================================
REM  Launcher for the sw-dev1.0 branch (tax demo).
REM
REM  Isolation from dev1.0 / start-dev.bat:
REM    - DB      : localhost:5532 / sw_audit_platform  (sw-postgres)
REM    - Redis   : localhost:6479                      (sw-redis)
REM    - Office  : localhost:8180                      (sw-onlyoffice)
REM    - Backend : :9981   (dev1.0 uses 9980)
REM    - Frontend: :3031   (dev1.0 uses 3030)
REM
REM  Env vars set below OVERRIDE backend/.env, because
REM  pydantic-settings gives real env vars priority over env_file.
REM  So dev1.0 config files stay untouched.
REM
REM  Containers must be up first:  .\scripts\sw-plan.ps1 up
REM ============================================================

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "BACKEND_DIR=%ROOT_DIR%\backend"
set "FRONTEND_DIR=%ROOT_DIR%\audit-platform\frontend"
set "BACKEND_PORT=9981"
set "FRONTEND_PORT=3031"
set "BACKEND_TITLE=SW-Backend-9981"
set "FRONTEND_TITLE=SW-Frontend-3031"

REM --- sw-plan container endpoints ----------------------------
set "SW_PG_PORT=5532"
set "SW_PG_DB=sw_audit_platform"
set "SW_REDIS_PORT=6479"
set "SW_OFFICE_PORT=8180"

REM --- pre-checks ---------------------------------------------
if not exist "%BACKEND_DIR%\app\main.py" ( echo [ERROR] Backend not found & exit /b 1 )
if not exist "%FRONTEND_DIR%\package.json" ( echo [ERROR] Frontend not found & exit /b 1 )
if not exist "%FRONTEND_DIR%\node_modules" ( echo [ERROR] Run "npm install" first & exit /b 1 )

set "PY="
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" set "PY=%ROOT_DIR%\.venv\Scripts\python.exe"
if "%PY%"=="" if exist "%BACKEND_DIR%\.venv\Scripts\python.exe" set "PY=%BACKEND_DIR%\.venv\Scripts\python.exe"
if "%PY%"=="" ( where python >nul 2>nul && set "PY=python" )
if "%PY%"=="" ( echo [ERROR] Python not found & exit /b 1 )

echo.
echo  ======================================
echo    SW Tax Platform - Dev Launcher
echo  ======================================
echo    DB    : localhost:%SW_PG_PORT%/%SW_PG_DB%
echo    Redis : localhost:%SW_REDIS_PORT%
echo    API   : :%BACKEND_PORT%    UI: :%FRONTEND_PORT%
echo  ======================================
echo.

REM --- [0/4] verify sw-plan containers ------------------------
echo [0/4] Checking sw-plan containers...
docker ps --filter "name=sw-postgres" --format "{{.Names}}" 2>nul | findstr /i "sw-postgres" >nul
if errorlevel 1 (
  echo [ERROR] sw-postgres is not running.
  echo         Start containers first:  .\scripts\sw-plan.ps1 up
  exit /b 1
)
docker ps --filter "name=sw-redis" --format "{{.Names}}" 2>nul | findstr /i "sw-redis" >nul
if errorlevel 1 echo [WARN] sw-redis not running: login/refresh may fail.
echo       sw-plan containers OK.

REM --- [1/4] stop old sw processes ----------------------------
echo [1/4] Stopping old SW processes...
taskkill /F /FI "WINDOWTITLE eq %BACKEND_TITLE%*" /T >nul 2>nul
taskkill /F /FI "WINDOWTITLE eq %FRONTEND_TITLE%*" /T >nul 2>nul

REM --- [2/4] start backend ------------------------------------
REM  DATABASE_URL / REDIS_URL are injected as real env vars so they
REM  win over backend/.env (which points at dev1.0 on 5432/6379).
echo [2/4] Starting backend on :%BACKEND_PORT% ...
set "BACKEND_RELOAD_ARGS=--reload"
if "%GT_BACKEND_NO_RELOAD%"=="1" set "BACKEND_RELOAD_ARGS="
set "SW_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:%SW_PG_PORT%/%SW_PG_DB%"
set "SW_REDIS_URL=redis://localhost:%SW_REDIS_PORT%/0"
start "%BACKEND_TITLE%" /min cmd /k "title %BACKEND_TITLE% && cd /d "%BACKEND_DIR%" && set DATABASE_URL=%SW_DB_URL% && set REDIS_URL=%SW_REDIS_URL% && set ONLYOFFICE_URL=http://localhost:%SW_OFFICE_PORT% && set ONLYOFFICE_CALLBACK_BASE=http://host.docker.internal:%BACKEND_PORT% && set WOPI_BASE_URL=http://host.docker.internal:%BACKEND_PORT%/wopi && set CORS_ORIGINS=http://localhost:%FRONTEND_PORT%,http://127.0.0.1:%FRONTEND_PORT% && "%PY%" run_uvicorn.py app.main:app --host 0.0.0.0 --port %BACKEND_PORT% %BACKEND_RELOAD_ARGS% --log-level warning"

REM --- [3/4] wait for backend ---------------------------------
echo [3/4] Waiting for backend health ...
set "BE_OK="
for /l %%i in (1,1,40) do (
  if not defined BE_OK (
    timeout /t 2 >nul
    curl -s -o nul -w "" http://127.0.0.1:%BACKEND_PORT%/api/health >nul 2>nul
    if not errorlevel 1 set "BE_OK=1"
  )
)
if not defined BE_OK echo [WARN] Backend not responding yet; check the %BACKEND_TITLE% window.
if defined BE_OK echo       Backend is up.

REM --- [4/4] start frontend -----------------------------------
echo [4/4] Starting frontend on :%FRONTEND_PORT% ...
start "%FRONTEND_TITLE%" /min cmd /k "title %FRONTEND_TITLE% && cd /d "%FRONTEND_DIR%" && set VITE_API_BASE_URL=http://127.0.0.1:%BACKEND_PORT% && set VITE_DEV_PORT=%FRONTEND_PORT% && set VITE_HOST=0.0.0.0 && npm run dev"

echo.
echo  ======================================
echo    SW stack starting
echo      UI  : http://localhost:%FRONTEND_PORT%
echo      API : http://localhost:%BACKEND_PORT%/api/health
echo  ======================================
echo.
echo  NOTE: first boot runs migrations on the empty sw database,
echo        so the initial request may take a while.
echo.
endlocal
