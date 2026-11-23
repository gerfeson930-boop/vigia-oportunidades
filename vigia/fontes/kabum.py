"""Coletor da KaBuM (loja, produto novo): lê os 60 produtos da busca do JSON da própria página.

O preço usado é o "à vista/Pix" (priceWithDiscount). Só produtos disponíveis.
"""
import json
import logging
import re

from .base import Anuncio, FonteBloqueada

log = logging.getLogger("vigia.kabum")
_RE_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def montar_url(termo):
    slug = re.sub(r"[^a-z0-9]+", "-", termo.lower()).strip("-")
    return f"https://www.kabum.com.br/busca/{slug}"


def extrair(pagina_html):
    m = _RE_NEXT.search(pagina_html)
    if not m:
        return None
    dados = json.loads(m.group(1))
    pagina = ((dados.get("props") or {}).get("pageProps") or {}).get("data") or {}
    if isinstance(pagina, str):  # páginas de categoria (ex.: busca "ps5") trazem o JSON como texto
        pagina = json.loads(pagina)
    catalogo = pagina.get("catalogServer") or {}
    return [p for p in (catalogo.get("data") or []) if isinstance(p, dict)]


def _converter(p):
    if not p.get("available") or not p.get("code") or not p.get("name"):
        return None
    preco = p.get("priceWithDiscount") or p.get("price")
    try:
        preco = float(preco)
    except (TypeError, ValueError):
        return None
    if preco <= 0:
        return None
    cheio = p.get("price") or 0
    data = "à vista no Pix" + (f" (cheio R$ {cheio:,.0f})".replace(",", ".") if cheio and cheio > preco else "")
    return Anuncio(fonte="kabum", id=str(p["code"]), titulo=p["name"].strip(), preco=preco,
                   url=f"https://www.kabum.com.br/produto/{p['code']}/{p.get('friendlyName', '')}",
                   local=p.get("sellerName") or "KaBuM!", data=data, foto=p.get("image") or "")


def buscar(navegador, termo):
    pg = navegador.new_page()
    try:
        resp = pg.goto(montar_url(termo), wait_until="domcontentloaded", timeout=45000)
        status = resp.status if resp else 0
        conteudo = pg.content()
        titulo = pg.title()
    finally:
        pg.close()
    produtos = extrair(conteudo)
    if produtos is None:
        t = titulo.lower()
        if status in (403, 429) or any(x in t for x in ("captcha", "attention", "denied", "verif")):
            raise FonteBloqueada(f"KaBuM respondeu {status} ({titulo[:60]})")
        return []
    resultado = [a for a in map(_converter, produtos) if a]
    log.info("KaBuM '%s': %d produtos", termo, len(resultado))
    return resultado
