"""Configuração local (token do bot, chat autorizado, credenciais do ML). Fica só no seu PC."""
import json
import os
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
DADOS.mkdir(exist_ok=True)
ARQ = DADOS / "config.json"
BANCO = DADOS / "vigia.db"
LOG = DADOS / "vigia.log"

PADROES = {
    "intervalo_min": 10,      # minutos entre rodadas
    "desconto_padrao": 25,    # % abaixo da mediana para alertar
    "bonus_urgencia": 10,     # pontos de % a menos exigidos quando o anúncio tem "urgente" etc.
    "amostras_min": 15,       # anúncios de referência antes de confiar na média
    "pausado": False,
}

_trava = threading.Lock()


def carregar():
    with _trava:
        dados = dict(PADROES)
        if ARQ.exists():
            dados.update(json.loads(ARQ.read_text(encoding="utf-8")))
        if os.environ.get("TELEGRAM_TOKEN"):  # na nuvem o token vem de um segredo, nunca do arquivo
            dados["telegram_token"] = os.environ["TELEGRAM_TOKEN"]
        return dados


def salvar(mudancas):
    with _trava:
        atual = json.loads(ARQ.read_text(encoding="utf-8")) if ARQ.exists() else {}
        atual.update(mudancas)
        tmp = ARQ.with_suffix(".tmp")
        tmp.write_text(json.dumps(atual, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, ARQ)
