@echo off
REM SuppTracker Frontend Launcher
REM Uses the portable Node.js bundled with the project

set NODE_DIR=%~dp0node_portable\node-v22.14.0-win-x64
set PATH=%NODE_DIR%;%PATH%
cd /d %~dp0
echo Starting SuppTracker frontend on http://localhost:5173 ...
node_modules\.bin\vite.cmd
pause
