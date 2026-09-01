@echo off
rem Le o banco mestre (139 MB) e gera o pacote pequeno que sobe no app.
rem Rodar uma vez por mes, depois que o banco mestre for regerado.
chcp 65001 >nul
title PPG Rota Comercial - preparar pacote do banco mestre

cd /d "%~dp0"

set PYTHON=backend\.venv\Scripts\python.exe
set SCRIPT=backend\scripts\preparar_pacote.py

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
echo   Gerando o pacote de atualizacao
echo   Le o banco mestre e extrai so o que o app precisa.
echo ============================================================
echo.

"%PYTHON%" "%SCRIPT%" %1
if errorlevel 1 (
    echo.
    echo Nao foi possivel gerar o pacote. Veja a mensagem acima.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   PROXIMO PASSO
echo ============================================================
echo.
echo   1. Abra o app e entre como administrador
echo   2. Va em Gestao ^> Importar
echo   3. Escolha "Pacote do banco mestre"
echo   4. Envie o arquivo pacote-atualizacao.ppg desta pasta
echo   5. Leia a previa e confirme
echo.
echo   Nada e gravado ate voce confirmar na tela.
echo.

rem Abre a pasta com o arquivo ja selecionado, pra nao ter que procurar.
if exist "pacote-atualizacao.ppg" explorer /select,"%cd%\pacote-atualizacao.ppg"

pause
