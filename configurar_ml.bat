@echo off
rem Liga o Mercado Livre pela API oficial (opcional).
chcp 65001 >nul
cd /d "%~dp0"
.venv\Scripts\python -m vigia.configurar ml
echo.
echo Reinicie o vigia para ele passar a usar o ML (rode iniciar.bat ou reinicie o PC).
pause
