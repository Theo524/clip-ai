@echo off
setlocal
cd /d "%~dp0"
echo Clip AI v22 Long-Term Beta preflight
echo =====================
where ffmpeg >nul 2>nul && echo [OK] FFmpeg || echo [MISSING] FFmpeg
where ffprobe >nul 2>nul && echo [OK] FFprobe || echo [MISSING] FFprobe
where node >nul 2>nul && echo [OK] Node.js || echo [MISSING] Node.js
where python >nul 2>nul && echo [OK] Python || echo [MISSING] Python
if exist "apps\worker\.venv\Scripts\python.exe" (echo [OK] Worker virtual environment) else echo [MISSING] apps\worker\.venv
if exist "apps\web\node_modules" (echo [OK] Frontend node_modules) else echo [INFO] Frontend dependencies will install on first launcher run
if exist "apps\worker\.env" (echo [OK] Worker .env) else echo [INFO] Worker .env not found; defaults/.env.example will be used

echo.
echo Once the worker is running, visit http://localhost:3000/status for the full live system check.
pause
endlocal
