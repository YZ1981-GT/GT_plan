@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"

set "BACKEND_DIR=%ROOT_DIR%\backend"
set "FRONTEND_DIR=%ROOT_DIR%\audit-platform\frontend"

set "BACKEND_PORT=9980"
set "FRONTEND_PORT=3030"

set "BACKEND_TITLE=GT Backend Dev"
set "FRONTEND_TITLE=GT Frontend Dev"

if not exist "%BACKEND_DIR%\app\main.py" (
  echo [ERROR] 未找到后端目录：%BACKEND_DIR%
  exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
  echo [ERROR] 未找到前端目录：%FRONTEND_DIR%
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 未检测到 npm，请先安装 Node.js。
  exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
  echo [ERROR] 未检测到前端依赖，请先执行 audit-platform\frontend 下的 npm install。
  exit /b 1
)

if exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
  set "BACKEND_START_CMD="%ROOT_DIR%\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload --reload-dir app --reload-exclude "*.pyc" --reload-exclude "__pycache__" --reload-exclude ".hypothesis""
) else if exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
  set "BACKEND_START_CMD="%BACKEND_DIR%\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload --reload-dir app --reload-exclude "*.pyc" --reload-exclude "__pycache__" --reload-exclude ".hypothesis""
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "BACKEND_START_CMD=py -3 -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload --reload-dir app --reload-exclude "*.pyc" --reload-exclude "__pycache__" --reload-exclude ".hypothesis""
  ) else (
    where python >nul 2>nul
    if errorlevel 1 (
      echo [ERROR] 未检测到 Python，请先安装 Python 或创建 backend\.venv。
      exit /b 1
    )
    set "BACKEND_START_CMD=python -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload --reload-dir app --reload-exclude "*.pyc" --reload-exclude "__pycache__" --reload-exclude ".hypothesis""
  )
)

echo [INFO] 正在关闭旧进程...
call :kill_window "%BACKEND_TITLE%"
call :kill_window "%FRONTEND_TITLE%"
call :kill_port %BACKEND_PORT%
call :kill_port %FRONTEND_PORT%
timeout /t 2 /nobreak >nul

echo [INFO] 正在启动后端，端口 %BACKEND_PORT% ...
start "%BACKEND_TITLE%" cmd /k "cd /d ""%BACKEND_DIR%"" && %BACKEND_START_CMD%"

timeout /t 2 /nobreak >nul

echo [INFO] 正在启动前端，端口 %FRONTEND_PORT% ...
start "%FRONTEND_TITLE%" cmd /k "cd /d ""%FRONTEND_DIR%"" && set VITE_API_BASE_URL=http://localhost:%BACKEND_PORT% && set VITE_DEV_PORT=%FRONTEND_PORT% && npm run dev"

echo [INFO] 已重新启动前后端。
echo [INFO] 后端：http://localhost:%BACKEND_PORT%
echo [INFO] 前端：http://localhost:%FRONTEND_PORT%
exit /b 0

:kill_window
taskkill /F /FI "WINDOWTITLE eq %~1" /T >nul 2>nul
exit /b 0

:kill_port
for /f %%P in ('powershell -NoProfile -Command "$ErrorActionPreference = ''SilentlyContinue''; $ids = Get-NetTCPConnection -LocalPort %~1 | Select-Object -ExpandProperty OwningProcess -Unique; foreach ($id in $ids) { $id }"') do (
  taskkill /PID %%P /F >nul 2>nul
)
exit /b 0
