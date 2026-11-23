"""Cliente mínimo da API de bots do Telegram (só biblioteca padrão)."""
import json
import logging
import urllib.request
import urllib.error

log = logging.getLogger("vigia.telegram")


class Telegram:
    def __init__(self, token):
        self.base = f"https://api.telegram.org/bot{token}"

    def _chamar(self, metodo, dados, timeout=40):
        req = urllib.request.Request(f"{self.base}/{metodo}", data=json.dumps(dados).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())["result"]
        except urllib.error.HTTPError as e:
            detalhe = e.read().decode(errors="replace")[:300]
            raise RuntimeError(f"Telegram {metodo} {e.code}: {detalhe}") from None

    def eu(self):
        return self._chamar("getMe", {})

    def atualizacoes(self, offset, timeout=30):
        return self._chamar("getUpdates", {"offset": offset, "timeout": timeout,
                                           "allowed_updates": ["message"]}, timeout=timeout + 10)

    def mensagem(self, chat_id, texto, teclado=None):
        dados = {"chat_id": chat_id, "text": texto, "parse_mode": "HTML", "disable_web_page_preview": True}
        if teclado:
            dados["reply_markup"] = teclado
        return self._chamar("sendMessage", dados)

    def foto(self, chat_id, url_foto, legenda):
        try:
            return self._chamar("sendPhoto", {"chat_id": chat_id, "photo": url_foto,
                                              "caption": legenda, "parse_mode": "HTML"})
        except RuntimeError as e:
            log.warning("foto falhou, mandando texto: %s", e)
            return self.mensagem(chat_id, legenda)

    def definir_comandos(self, comandos):
        self._chamar("setMyCommands", {"commands": [{"command": c, "description": d} for c, d in comandos]})
