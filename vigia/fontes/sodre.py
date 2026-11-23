"""Leilões da Sodré Santoro (segmento "materiais": eletrônicos, informática, equipamentos).

A busca do site (/materiais/lotes?term=...) dispara uma chamada interna `search-lots`; o coletor lê
a resposta dessa chamada dentro do navegador. Lotes costumam ter várias unidades, então não há
comparação com média: o vigia avisa cada LOTE NOVO com as palavras-chave de leilão.
"""
import logging
from datetime import datetime
from urllib.parse import quote

from .base import Anuncio, FonteBloqueada

log = logging.getLogger("vigia.sodre")

TERMOS_PADRAO = ["notebook", "iphone", "celular", "smartphone", "macbook", "ipad", "tablet",
                 "playstation", "xbox", "nintendo", "monitor", "placa de video", "drone", "camera",
                 "informatica", "eletronicos"]


def _valor(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _converter(s):
    if s.get("lot_status") in ("encerrado", "vendido", "cancelado") or not s.get("lot_id"):
        return None
    atual, inicial = _valor(s.get("bid_actual")), _valor(s.get("bid_initial"))
    quando = ""
    try:
        quando = datetime.fromisoformat(s["auction_date_init"]).strftime("%d/%m às %H:%M")
    except (KeyError, ValueError, TypeError):
        pass
    fotos = s.get("lot_pictures") or []
    lance = (f"lance atual R$ {atual:,.0f}" if atual else f"lance inicial R$ {inicial:,.0f}").replace(",", ".")
    return Anuncio(
        fonte="leilao", id=str(s["lot_id"]), titulo=(s.get("lot_title") or "lote").strip(),
        preco=atual or inicial,
        url=f"https://leilao.sodresantoro.com.br/leilao/{s.get('auction_id')}/lote/{s['lot_id']}/",
        local=(s.get("lot_location") or "").upper(),
        data=f"{lance} · leilão {quando}".strip(" ·"),
        foto=fotos[0] if fotos else "",
    )


def buscar(navegador, termo):
    pg = navegador.new_page()
    try:
        try:
            with pg.expect_response(lambda r: "search-lots" in r.url and r.request.post_data
                                    and "match_phrase_prefix" in r.request.post_data, timeout=30000) as info:
                pg.goto(f"https://www.sodresantoro.com.br/materiais/lotes?term={quote(termo)}"
                        f"&sort=auction_date_init_asc", wait_until="domcontentloaded", timeout=45000)
            dados = info.value.json()
        except Exception as e:
            t = pg.title().lower()
            if any(x in t for x in ("captcha", "attention", "denied", "verif")):
                raise FonteBloqueada(f"Sodré Santoro: {pg.title()[:60]}")
            raise RuntimeError(f"Sodré Santoro não respondeu à busca: {e}") from None
    finally:
        pg.close()
    lotes = [a for a in (_converter(h.get("_source", h)) for h in dados.get("results") or []) if a]
    log.info("Leilão '%s': %d lotes", termo, len(lotes))
    return lotes
