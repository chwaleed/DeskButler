@echo off
REM Run the AI Desktop Agent: build the frontend, then launch the backend window.
REM Double-click this file, or run `run.cmd` from a terminal.
setlocal

cd /d "%~dp0"

REM --- Optional: redirect uv/npm caches off a full system drive. ---
REM If C: has no space, uncomment and point these at a drive that does:
REM set "UV_PYTHON_INSTALL_DIR=%~dp0.uv\python"
REM set "UV_CACHE_DIR=%~dp0.uv\cache"
REM set "npm_config_cache=%~dp0.npm-cache"

echo [1/3] Building frontend...
cd frontend
call npm install || goto :error
call npm run build || goto :error
cd ..

echo [2/3] Syncing backend deps...
cd backend
call uv sync || goto :error

REM Dev logging: prints every tool call, result, and error to this terminal.
REM Uncomment the next line to enable.
REM set "DESKBUTLER_DEV=1"

echo [3/3] Launching app...
call uv run python -m agent.main
cd ..
goto :eof

:error
echo.
echo Build failed. See the output above.
exit /b 1
