@echo off
rem Lancador de um clique do app PPG Rota Comercial.
rem Sobe o backend e o frontend e abre o navegador automaticamente.
title PPG Rota Comercial - servidores (feche esta janela para parar)

cd /d "%~dp0"

rem Sobe o backend (FastAPI/uvicorn) numa janela propria minimizada.
start "PPG Rota Comercial - backend" /min "backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --port 8090

rem Sobe o frontend (Vite dev server) numa janela propria minimizada.
start "PPG Rota Comercial - frontend" /min cmd /c "cd /d ""%~dp0app"" && npm run dev"

rem Aguarda os dois subirem e abre o app no navegador.
ping -n 7 127.0.0.1 >nul
start "" http://127.0.0.1:5175
