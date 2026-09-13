@echo off
setlocal
cd /d "%~dp0"

echo Clip AI v22 M2 - Smarter Clip Intelligence
echo.
where ffmpeg >nul 2>nul || (echo [ERROR] FFmpeg is not on PATH.& pause & exit /b 1)
where ffprobe >nul 2>nul || (echo [ERROR] FFprobe is not on PATH.& pause & exit /b 1)
where node >nul 2>nul || (echo [ERROR] Node.js is not on PATH.& pause & exit /b 1)
if not exist "apps\worker\.venv\Scripts\python.exe" (echo [ERROR] Python virtual environment is missing in apps\worker\.venv& echo Run the setup steps in README.md first.& pause & exit /b 1)
if not exist "apps\web\node_modules" (echo [INFO] Frontend dependencies are missing. Running npm install...& pushd apps\web & call npm install & popd)

start "Clip AI Worker" cmd /k "cd /d ""%~dp0apps\worker"" && .venv\Scripts\activate && uvicorn main:app --port 8000"
start "Clip AI Web" cmd /k "cd /d ""%~dp0apps\web"" && npm run dev"
timeout /t 4 /nobreak >nul
start "" http://localhost:3000
echo Clip AI is starting. Keep the two service windows open while you use it.
endlocal
