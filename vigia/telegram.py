"""Cliente mínimo da API de bots do Telegram (só biblioteca padrão)."""
import json
import logging
import urllib.request
import urllib.error
import uuid

log = logging.getLogger("vigia.telegram")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0 Safari/537.36")


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

    def _enviar_arquivo(self, chat_id, conteudo, legenda, teclado=None):
        """sendPhoto com o arquivo (multipart), para não depender do Telegram conseguir baixar do OLX."""
        limite = uuid.uuid4().hex
        campos = {"chat_id": str(chat_id), "caption": legenda, "parse_mode": "HTML"}
        if teclado:
            campos["reply_markup"] = json.dumps(teclado)
        corpo = b""
        for nome, valor in campos.items():
            corpo += (f"--{limite}\r\nContent-Disposition: form-data; name=\"{nome}\"\r\n\r\n"
                      f"{valor}\r\n").encode()
        corpo += (f"--{limite}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"foto.jpg\"\r\n"
                  f"Content-Type: image/jpeg\r\n\r\n").encode() + conteudo + f"\r\n--{limite}--\r\n".encode()
        req = urllib.request.Request(f"{self.base}/sendPhoto", data=corpo,
                                     headers={"Content-Type": f"multipart/form-data; boundary={limite}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())["result"]
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Telegram sendPhoto {e.code}: {e.read().decode(errors='replace')[:300]}") from None

    def foto(self, chat_id, url_foto, legenda, teclado=None):
        """Baixa a foto aqui e envia o arquivo; se falhar, tenta pelo link; por último, só texto."""
        try:
            req = urllib.request.Request(url_foto, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                conteudo = r.read()
            return self._enviar_arquivo(chat_id, conteudo, legenda, teclado)
        except Exception as e:
            log.warning("upload da foto falhou (%s); tentando pelo link", e)
        try:
            dados = {"chat_id": chat_id, "photo": url_foto, "caption": legenda, "parse_mode": "HTML"}
            if teclado:
                dados["reply_markup"] = teclado
            return self._chamar("sendPhoto", dados)
        except RuntimeError as e:
            log.warning("foto falhou, mandando texto: %s", e)
            return self.mensagem(chat_id, legenda, teclado)

    def definir_comandos(self, comandos):
        self._chamar("setMyCommands", {"commands": [{"command": c, "description": d} for c, d in comandos]})
