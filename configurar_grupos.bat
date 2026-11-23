@echo off
rem Liga a leitura dos seus grupos/canais de promoção do Telegram e reinicia o vigia.
chcp 65001 >nul
cd /d "%~dp0"
.venv\Scripts\python -m vigia.configurar_grupos || (pause & exit /b 1)
call "%~dp0parar.bat" silencioso
start "" /d "%~dp0" .venv\Scripts\pythonw.exe -m vigia
echo.
echo Vigia reiniciado. Pode fechar esta janela.
pause
