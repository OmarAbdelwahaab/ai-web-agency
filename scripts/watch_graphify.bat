@echo off
title Graphify Watcher - AI Web Agency
cd /d "%~dp0\.."
echo ========================================================
echo   Graphify Knowledge Graph Watcher Active
echo   Auto-updating graphify-out/ on code modifications
echo ========================================================
echo Press Ctrl+C to stop.
.venv\Scripts\python.exe -m graphify.watch . --debounce 3
