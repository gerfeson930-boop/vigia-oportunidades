@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Vigia de Oportunidades - instalacao ===
python --version >nul 2>&1 || (echo Python nao encontrado. Instale em https://www.python.org/downloads/ e rode de novo. & pause & exit /b 1)

if not exist .venv\Scripts\python.exe (
  echo Criando ambiente Python...
  python -m venv .venv || (pause & exit /b 1)
)
echo Instalando dependencias...
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -r requirements.txt || (pause & exit /b 1)
echo Baixando o navegador usado nas buscas (uma vez so)...
.venv\Scripts\python -m playwright install chromium || (pause & exit /b 1)

echo.
if exist dados\config.json (
  choice /m "Ja existe um bot configurado. Trocar o token"
  if errorlevel 2 goto inicio
)
.venv\Scripts\python -m vigia.configurar || (pause & exit /b 1)

:inicio
echo.
choice /m "Iniciar o vigia automaticamente junto com o Windows"
if errorlevel 2 goto rodar
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\Vigia de Oportunidades.lnk'); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='-m vigia'; $s.WorkingDirectory='%~dp0'; $s.Save()"
echo Atalho criado na pasta Inicializar do Windows.

:rodar
call "%~dp0parar.bat" silencioso
start "" /d "%~dp0" .venv\Scripts\pythonw.exe -m vigia
echo.
echo Vigia rodando em segundo plano. Mande /start para o seu bot no Telegram.
echo Log: %~dp0dados\vigia.log
pause
