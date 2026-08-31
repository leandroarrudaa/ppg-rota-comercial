@echo off
rem Atualizacao da carteira e do RFM a partir do banco mestre (XMLs de NFe).
rem Mostra primeiro o que MUDARIA, e so grava depois de voce confirmar.
chcp 65001 >nul
title PPG Rota Comercial - atualizar carteira

cd /d "%~dp0"

set PYTHON=backend\.venv\Scripts\python.exe
set SCRIPT=backend\scripts\recarregar_do_banco_mestre.py

if not exist "%PYTHON%" (
    echo.
    echo Nao encontrei o Python do projeto em %PYTHON%
    echo Abra o projeto no Claude Code e peca para preparar o ambiente.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   PASSO 1 de 2 - SIMULACAO
echo   Nada sera gravado agora. E so para voce ver o que muda.
echo ============================================================
echo.

"%PYTHON%" "%SCRIPT%" --simular --com-historico
if errorlevel 1 (
    echo.
    echo A simulacao falhou. Nada foi alterado.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   PASSO 2 de 2 - CONFIRMACAO
echo ============================================================
echo.
echo   Leia os numeros acima. Se estiverem certos, confirme.
echo.
set /p RESPOSTA=  Gravar essas mudancas? (digite S para gravar):

if /i not "%RESPOSTA%"=="S" (
    echo.
    echo Cancelado. Nada foi alterado.
    echo.
    pause
    exit /b 0
)

echo.
"%PYTHON%" "%SCRIPT%" --com-historico
if errorlevel 1 (
    echo.
    echo A gravacao falhou. Verifique a mensagem acima.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Pronto. A carteira foi atualizada.
echo ============================================================
echo.
pause
