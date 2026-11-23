"""Coletor do OLX: abre a busca num Chromium real e lê os anúncios do JSON embutido na página.

A página traz os 50 anúncios completos (título, preço, cidade, UF, data, fotos) no payload do
Next.js (`self.__next_f.push`). Ler esse JSON é mais confiável que ler os cards, que só são
preenchidos quando aparecem na tela.
"""
import json
import logging
import re
from datetime import datetime
from urllib.parse import quote_plus

from .base import Anuncio, FonteBloqueada

log = logging.getLogger("vigia.olx")

ESTADO = "mg"  # Minas Gerais
_RE_PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
_dec = json.JSONDecoder()


def montar_url(termo, pagina=1):
    url = f"https://www.olx.com.br/estado-{ESTADO}?q={quote_plus(termo)}&sf=1"  # sf=1: mais recentes
    if pagina > 1:
        url += f"&o={pagina}"
    return url


def extrair_anuncios(html):
    """Devolve os objetos de anúncio (dicts com listId) encontrados no payload da página."""
    texto = "".join(json.loads(m.group(1)) for m in _RE_PUSH.finditer(html))
    ads = {}
    for m in re.finditer(r'"listId":', texto):
        pos = inicio = m.start()
        for _ in range(60):  # volta até achar a '{' que abre o objeto do anúncio
            inicio = texto.rfind("{", 0, inicio)
            if inicio < 0:
                break
            try:
                obj, fim = _dec.raw_decode(texto, inicio)
            except ValueError:
                continue
            if fim > pos and isinstance(obj, dict) and "listId" in obj:
                ads.setdefault(obj["listId"], obj)
                break
    return list(ads.values())


def _preco(obj):
    v = obj.get("priceValue")
    if isinstance(v, (int, float)) and v > 0:
        return float(v)
    m = re.search(r"R\$\s*([\d\.]+)(?:,(\d{2}))?", str(obj.get("price") or ""))
    if not m:
        return None
    return float(m.group(1).replace(".", "")) + (int(m.group(2)) / 100 if m.group(2) else 0)


def _converter(obj):
    preco = _preco(obj)
    if preco is None or not obj.get("subject") or not obj.get("url"):
        return None
    loc = obj.get("locationDetails") or {}
    if loc.get("uf") and loc["uf"].lower() != ESTADO:
        return None
    imgs = obj.get("images") or []
    foto = imgs[0].get("original", "") if imgs and isinstance(imgs[0], dict) else ""
    data = ""
    if isinstance(obj.get("date"), (int, float)):
        data = datetime.fromtimestamp(obj["date"]).strftime("%d/%m %H:%M")
    local = ", ".join(x for x in (loc.get("municipality"), loc.get("neighbourhood")) if x)
    return Anuncio(fonte="olx", id=str(obj["listId"]), titulo=obj["subject"].strip(), preco=preco,
                   url=obj["url"].split("?")[0], local=local or obj.get("location", ""), data=data, foto=foto)


def buscar(navegador, termo, paginas=1):
    """Retorna lista de Anuncio. `navegador` é um BrowserContext do Playwright."""
    resultado = []
    for pagina in range(1, paginas + 1):
        pg = navegador.new_page()
        try:
            resp = pg.goto(montar_url(termo, pagina), wait_until="load", timeout=60000)
            status = resp.status if resp else 0
            titulo_pg = pg.title()
            html = pg.content()
        finally:
            pg.close()
        brutos = extrair_anuncios(html)
        if not brutos:
            t = titulo_pg.lower()
            if status in (403, 429) or any(x in t for x in ("moment", "attention", "captcha", "verif")):
                raise FonteBloqueada(f"OLX respondeu {status} ({titulo_pg[:60]})")
            break  # busca sem resultados
        resultado += [a for a in map(_converter, brutos) if a]
        if len(brutos) < 50:
            break  # não há próxima página
    log.info("OLX '%s': %d anúncios", termo, len(resultado))
    return resultado
