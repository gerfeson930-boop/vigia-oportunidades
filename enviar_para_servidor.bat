@echo off
rem Leva o vigia deste PC para um servidor Linux (VPS ou mini PC) que fica ligado 24 h.
rem 1) instala no servidor  2) testa os sites de lá  3) copia seus dados  4) liga lá e desliga aqui.
chcp 65001 >nul
cd /d "%~dp0"
echo === Levar o vigia para um servidor 24 h ===
echo.
echo Você precisa do endereço do servidor no formato usuario@ip  (ex.: root@203.0.113.10).
echo A senha do servidor quem digita é você, quando ele pedir (não aparece na tela).
echo.
set /p ALVO=Endereço do servidor:
if "%ALVO%"=="" (echo Nada informado. & pause & exit /b 1)

echo.
echo [1/4] Instalando no servidor (pode levar uns 5 minutos)...
ssh -o StrictHostKeyChecking=accept-new %ALVO% "curl -fsSL https://raw.githubusercontent.com/gerfeson930-boop/vigia-oportunidades/main/deploy/instalar_servidor.sh | bash" || (echo Falhou a instalação. & pause & exit /b 1)

echo.
echo [2/4] Testando os sites a partir do servidor...
ssh %ALVO% "cd ~/vigia && .venv/bin/python -m vigia.testar_fontes"
echo.
choice /m "Continuar e passar o vigia para o servidor"
if errorlevel 2 (echo Nada foi mudado. O vigia continua no PC. & pause & exit /b 0)

echo.
echo [3/4] Copiando seus dados (bot, buscas, histórico, login dos grupos)...
call "%~dp0parar.bat" silencioso
scp dados\config.json dados\vigia.db %ALVO%:~/vigia/dados/ || (echo Falhou a cópia. Religando no PC. & start "" /d "%~dp0" .venv\Scripts\pythonw.exe -m vigia & pause & exit /b 1)
if exist dados\sessao_telegram.session scp dados\sessao_telegram.session %ALVO%:~/vigia/dados/

echo.
echo [4/4] Ligando no servidor...
ssh %ALVO% "sudo systemctl restart vigia 2>/dev/null || systemctl restart vigia; sleep 8; tail -n 3 ~/vigia/dados/vigia.log"
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Vigia de Oportunidades.lnk" 2>nul
echo.
echo Pronto! O vigia agora roda no servidor, 24 h. Neste PC ele foi desligado e não inicia mais com o Windows.
echo Para voltar a rodar no PC: dê dois cliques em instalar.bat.
pause
