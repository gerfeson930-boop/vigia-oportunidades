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

    @staticmethod
    def _baixar(url):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()

    def album(self, chat_id, itens):
        """Envia até 10 fotos num álbum (sendMediaGroup), cada uma com sua legenda.

        itens: [(url_foto, legenda_html)]. As fotos são baixadas aqui e enviadas como arquivo.
        Devolve as legendas que não entraram no álbum (foto indisponível), para irem como texto.
        """
        arquivos, media, sem_foto = [], [], []
        for url, legenda in itens[:10]:
            try:
                arquivos.append(self._baixar(url))
                media.append({"type": "photo", "media": f"attach://f{len(arquivos) - 1}",
                              "caption": legenda[:1024], "parse_mode": "HTML"})
            except Exception as e:
                log.warning("foto do álbum indisponível (%s)", e)
                sem_foto.append(legenda)
        if len(media) == 1:  # álbum precisa de 2+ fotos; com 1, vai como foto simples
            self._enviar_arquivo(chat_id, arquivos[0], media[0]["caption"])
            return sem_foto
        if not media:
            return sem_foto
        limite = uuid.uuid4().hex
        corpo = b""
        for nome, valor in (("chat_id", str(chat_id)), ("media", json.dumps(media))):
            corpo += (f"--{limite}\r\nContent-Disposition: form-data; name=\"{nome}\"\r\n\r\n"
                      f"{valor}\r\n").encode()
        for i, conteudo in enumerate(arquivos):
            corpo += (f"--{limite}\r\nContent-Disposition: form-data; name=\"f{i}\"; filename=\"f{i}.jpg\"\r\n"
                      f"Content-Type: image/jpeg\r\n\r\n").encode() + conteudo + b"\r\n"
        corpo += f"--{limite}--\r\n".encode()
        req = urllib.request.Request(f"{self.base}/sendMediaGroup", data=corpo,
                                     headers={"Content-Type": f"multipart/form-data; boundary={limite}"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                json.loads(r.read())
        except urllib.error.HTTPError as e:
            log.warning("álbum falhou: %s %s", e.code, e.read().decode(errors="replace")[:200])
            return [m["caption"] for m in media] + sem_foto
        return sem_foto

    def definir_comandos(self, comandos):
        self._chamar("setMyCommands", {"commands": [{"command": c, "description": d} for c, d in comandos]})
