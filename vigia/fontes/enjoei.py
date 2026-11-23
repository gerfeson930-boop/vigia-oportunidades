"""Coletor do Enjoei: abre a busca num Chromium real e lê a resposta da busca que a própria página faz.

Envio para o Brasil todo (sr=same_country). Na rodada normal pega só o que foi publicado nas
últimas 24 h (lp=24h); na primeira rodada de uma busca, pega sem esse filtro para aprender preços.
"""
import logging
from urllib.parse import quote

from .base import Anuncio, FonteBloqueada

log = logging.getLogger("vigia.enjoei")
# Só alguns tamanhos existem (150, 300, 800...); o id precisa do "=" de preenchimento do base64.
FOTO = "https://photos.enjoei.com.br/public/800x800/{}"


def url_foto(id_publico):
    return FOTO.format(id_publico + "=" * (-len(id_publico) % 4))


def montar_url(termo, recentes):
    url = f"https://www.enjoei.com.br/s?q={quote(termo)}&sr=same_country"
    return url + "&lp=24h" if recentes else url


def _converter(no):
    try:
        preco = float((no.get("price") or {}).get("current"))
    except (TypeError, ValueError):
        return None
    titulo = ((no.get("title") or {}).get("name") or "").strip()
    if not titulo or not no.get("path") or preco <= 0:
        return None
    foto_id = (no.get("photo") or {}).get("image_public_id")
    return Anuncio(
        fonte="enjoei", id=str(no["id"]), titulo=titulo, preco=preco,
        url=f"https://www.enjoei.com.br/p/{no['path']}", local="envia para todo o Brasil",
        data="novo" if no.get("used") is False else "usado",
        foto=url_foto(foto_id) if foto_id else "",
    )


def buscar(navegador, termo, recentes=True):
    pg = navegador.new_page()
    try:
        try:
            with pg.expect_response(lambda r: "graphql-search-x" in r.url, timeout=30000) as info:
                pg.goto(montar_url(termo, recentes), wait_until="domcontentloaded", timeout=45000)
            dados = info.value.json()
        except Exception as e:
            t = pg.title().lower()
            if any(x in t for x in ("captcha", "attention", "denied", "verif")):
                raise FonteBloqueada(f"Enjoei: {pg.title()[:60]}")
            raise RuntimeError(f"Enjoei não respondeu à busca: {e}") from None
    finally:
        pg.close()
    arestas = (((dados.get("data") or {}).get("search") or {}).get("products") or {}).get("edges") or []
    resultado = [a for a in (_converter(e.get("node") or {}) for e in arestas) if a]
    log.info("Enjoei '%s': %d anúncios", termo, len(resultado))
    return resultado
