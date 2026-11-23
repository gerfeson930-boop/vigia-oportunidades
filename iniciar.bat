@echo off
rem Roda o vigia com uma janela de console, para ver o que ele esta fazendo. Feche a janela para parar.
chcp 65001 >nul
cd /d "%~dp0"
call parar.bat silencioso
.venv\Scripts\python -m vigia
pause
