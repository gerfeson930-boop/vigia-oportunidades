#!/usr/bin/env bash
# Instala (ou atualiza) o Vigia de Oportunidades num servidor Linux (Ubuntu/Debian) e cria o
# serviço que mantém ele rodando 24 h e volta sozinho depois de reiniciar.
# Uso (no servidor):  curl -fsSL https://raw.githubusercontent.com/gerfeson930-boop/vigia-oportunidades/main/deploy/instalar_servidor.sh | bash
set -euo pipefail

PASTA="${PASTA:-$HOME/vigia}"
REPO="https://github.com/gerfeson930-boop/vigia-oportunidades.git"
SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"

echo "== Instalando dependências do sistema"
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq git python3 python3-venv >/dev/null

echo "== Baixando o vigia em $PASTA"
if [ -d "$PASTA/.git" ]; then git -C "$PASTA" pull -q --ff-only; else git clone -q "$REPO" "$PASTA"; fi
cd "$PASTA"
mkdir -p dados

echo "== Ambiente Python e navegador (alguns minutos na primeira vez)"
python3 -m venv .venv
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt
$SUDO .venv/bin/python -m playwright install-deps chromium >/dev/null
.venv/bin/python -m playwright install chromium >/dev/null

echo "== Serviço do sistema (liga sozinho e reinicia se cair)"
$SUDO tee /etc/systemd/system/vigia.service >/dev/null <<EOF
[Unit]
Description=Vigia de Oportunidades
After=network-online.target
Wants=network-online.target

[Service]
User=$(id -un)
WorkingDirectory=$PASTA
ExecStart=$PASTA/.venv/bin/python -m vigia
Restart=always
RestartSec=30
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
$SUDO systemctl daemon-reload
$SUDO systemctl enable -q vigia

if [ -f dados/config.json ]; then
  $SUDO systemctl restart vigia
  echo "== Vigia rodando. Log: $PASTA/dados/vigia.log"
else
  echo "== Instalado. Falta copiar os dados do PC (o enviar_para_servidor.bat faz isso)."
fi
