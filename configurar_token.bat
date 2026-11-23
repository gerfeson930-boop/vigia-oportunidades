@echo off
rem Abre a janelinha para colar o token do bot e (re)inicia o vigia em segundo plano.
chcp 65001 >nul
cd /d "%~dp0"
.venv\Scripts\python -m vigia.configurar || (pause & exit /b 1)
echo.
choice /m "Iniciar o vigia automaticamente junto com o Windows"
if errorlevel 2 goto rodar
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\Vigia de Oportunidades.lnk'); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='-m vigia'; $s.WorkingDirectory='%~dp0'; $s.Save()"
echo Atalho criado na pasta Inicializar do Windows.
:rodar
call "%~dp0parar.bat" silencioso
start "" /d "%~dp0" .venv\Scripts\pythonw.exe -m vigia
echo.
echo Vigia rodando em segundo plano. Pode fechar esta janela.
timeout /t 8
