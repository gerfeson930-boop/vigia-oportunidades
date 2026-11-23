"""Coletor do Pelando: promoções de lojas (produto novo) postadas pela comunidade.

A página de busca vem renderizada no servidor e traz as promoções no atributo `props` de um
componente Astro (formato [tipo, valor]). Só interessam promoções ativas e recentes.
"""
import html
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .base import Anuncio, FonteBloqueada

log = logging.getLogger("vigia.pelando")
MAX_IDADE = timedelta(days=2)
_RE_ILHA = re.compile(r'<astro-island[^>]*component-export="SearchFeedContent"[^>]*props="([^"]*)"')


def _decodificar(v):
    """Formato de props do Astro: [0, valor] (simples) ou [1, [itens codificados]] (lista)."""
    if isinstance(v, list) and len(v) == 2 and v[0] in (0, 1):
        return [_decodificar(i) for i in v[1]] if v[0] == 1 else _decodificar(v[1])
    if isinstance(v, dict):
        return {k: _decodificar(x) for k, x in v.items()}
    return v


def extrair_promocoes(pagina_html):
    m = _RE_ILHA.search(pagina_html)
    if not m:
        return None
    props = _decodificar(json.loads(html.unescape(m.group(1))))
    return ((props.get("initialData") or {}).get("deals") or {}).get("deals") or []


def _converter(d, agora):
    if d.get("status") == "expired" or not d.get("price") or not d.get("slug"):
        return None
    try:
        criada = datetime.fromisoformat(d["createdAt"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None
    if agora - criada > MAX_IDADE:
        return None
    fotos = d.get("imageSrcset") or []
    foto = max(fotos, key=lambda f: f.get("width", 0))["url"] if fotos else (d.get("imageUrl") or "")
    loja = (d.get("store") or {}).get("name") or "loja"
    temp = d.get("temperature")
    return Anuncio(
        fonte="pelando", id=str(d["id"]), titulo=d["title"].strip(), preco=float(d["price"]),
        url=f"https://www.pelando.com.br/d/{d['slug']}", local=loja,
        data=(f"🌡️ {temp}°" if temp is not None else "") + f" · postada {criada.astimezone():%d/%m %H:%M}",
        foto=foto,
    )


def buscar(navegador, termo):
    pg = navegador.new_page()
    try:
        resp = pg.goto(f"https://www.pelando.com.br/busca/{quote(termo)}", wait_until="domcontentloaded",
                       timeout=45000)
        conteudo = pg.content()
        titulo = pg.title()
        status = resp.status if resp else 0
    finally:
        pg.close()
    promocoes = extrair_promocoes(conteudo)
    if promocoes is None:
        t = titulo.lower()
        if status in (403, 429) or any(x in t for x in ("captcha", "attention", "denied", "verif")):
            raise FonteBloqueada(f"Pelando respondeu {status} ({titulo[:60]})")
        return []  # sem resultados
    agora = datetime.now(timezone.utc)
    resultado = [a for a in (_converter(d, agora) for d in promocoes) if a]
    log.info("Pelando '%s': %d promoções ativas recentes (de %d)", termo, len(resultado), len(promocoes))
    return resultado
