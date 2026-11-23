"""Leitor dos grupos/canais de promoção que o usuário já segue no Telegram.

Usa a API oficial do Telegram pela conta do próprio usuário (Telethon), só lendo. A cada mensagem
nova nos grupos escolhidos: acha o produto (das buscas cadastradas) e o preço, compara com a média
dos usados e, se valer a pena (🔥 ou ✅), avisa pelo bot com a foto do post.

Configuração: `python -m vigia.configurar_grupos` (chave de my.telegram.org + login + escolha dos grupos).
"""
import asyncio
import html
import logging
import re
import threading

from . import analise, config, db
from .fontes.base import Anuncio

log = logging.getLogger("vigia.grupos")
SESSAO = config.DADOS / "sessao_telegram"

_RE_PRECO = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{2}))?", re.I)
# preço que não é o do produto: cupom, desconto, frete, cashback, parcela
_NAO_E_PRECO = re.compile(r"^\s*(?:off|de desconto|desconto|de cashback|cashback|em cupom|no cupom)", re.I)
_ANTES_NAO_E_PRECO = re.compile(r"(frete|cupom de|cashback de|desconto de|economi[az]e?|parcelas? de|\d+\s?x\s?(de)?)\s*$",
                                re.I)
_RE_LINK = re.compile(r"https?://\S+")


def extrair_preco(texto):
    """Menor preço "de verdade" do post (ignora cupom, frete, cashback e parcela). None se não achar."""
    precos = []
    for m in _RE_PRECO.finditer(texto):
        if _NAO_E_PRECO.match(texto[m.end():m.end() + 20]):
            continue
        if _ANTES_NAO_E_PRECO.search(texto[max(0, m.start() - 25):m.start()]):
            continue
        valor = float(m.group(1).replace(".", "")) + (int(m.group(2)) / 100 if m.group(2) else 0)
        if valor >= 10:
            precos.append(valor)
    return min(precos) if precos else None


def titulo_do_post(texto):
    """As primeiras linhas com conteúdo (onde os canais põem o nome do produto)."""
    linhas = [l.strip(" *_-•🔥⚡️✅👉➡️📦💥🚨") for l in texto.splitlines()]
    linhas = [l for l in linhas if len(l) > 3 and not l.lower().startswith("http") and "R$" not in l]
    if not linhas:
        return ""
    # nome curto ("PS5 Slim") costuma continuar na linha seguinte
    return (linhas[0] if len(linhas[0]) >= 25 or len(linhas) == 1 else f"{linhas[0]} {linhas[1]}")[:200]


def buscas_do_post(texto, buscas):
    """Buscas cadastradas que batem com o título do post."""
    titulo = titulo_do_post(texto)
    return titulo, [b for b in buscas if b.get("desconto") != 0 and analise.relevante(titulo, b)]


def link_do_post(chat, msg_id):
    usuario = getattr(chat, "username", None)
    if usuario:
        return f"https://t.me/{usuario}/{msg_id}"
    return f"https://t.me/c/{chat.id}/{msg_id}"


def _brl(v):
    return f"R$ {v:,.0f}".replace(",", ".")


def formatar(titulo, preco, info, busca, grupo, link_post, link_oferta):
    e = html.escape
    nivel_forte = info["nivel"] == analise.FORTE
    media = ""
    if info.get("mediana"):
        sinal = "-" if info["desconto"] >= 0 else "+"
        media = f"  (média dos usados {_brl(info['mediana'])}, <b>{sinal}{abs(info['desconto']):.0f}%</b>)"
    linhas = [
        f"💰 <b>{_brl(preco)}</b>{media}",
        f"{'🔥' if nivel_forte else '📣'} <b>{e(titulo[:150])}</b>",
        "✅ " + "; ".join(info["motivos"]),
    ]
    if nivel_forte:
        linhas.append("🔥🔥 <b>PECHINCHA</b>: bem abaixo da média, vale correr")
    linhas += [f"📣 postado em <b>{e(grupo)}</b>", f"🔎 busca #{busca['id']}: {e(busca['termo'])}"]
    links = [f'<a href="{e(link_post)}">Ver post</a>'] if link_post else []
    if link_oferta:
        links.insert(0, f'<a href="{e(link_oferta)}">Abrir oferta</a>')
    linhas.append("  ·  ".join(links))
    return "\n".join(linhas)


def configurado():
    c = config.carregar()
    return bool(c.get("tg_api_id") and c.get("tg_api_hash") and c.get("tg_grupos")
                and SESSAO.with_suffix(".session").exists())


class LeitorGrupos:
    def __init__(self, avisar):
        self.avisar = avisar  # avisar(texto, foto) — foto pode ser bytes
        self.ativo = False
        self.ultimo_erro = None

    def tratar(self, texto, chat, msg_id, grupo, foto_bytes=None):
        """Processa um post. Devolve a quantidade de alertas enviados (também usado nos testes)."""
        if not texto:
            return 0
        cfg = config.carregar()
        preco = extrair_preco(texto)
        if preco is None:
            return 0
        titulo, buscas = buscas_do_post(texto, db.listar_buscas(so_ativas=True))
        enviados = 0
        for busca in buscas[:1]:  # o mesmo post só gera um alerta
            ad_id = f"{getattr(chat, 'id', chat)}:{msg_id}"
            if db.anuncio_existente("telegram", ad_id, busca["id"]):
                continue
            link_post = link_do_post(chat, msg_id) if hasattr(chat, "id") else ""
            links = _RE_LINK.findall(texto)
            a = Anuncio(fonte="telegram", id=ad_id, titulo=titulo, preco=preco,
                        url=links[0] if links else link_post, local=grupo)
            info = analise.avaliar_promocao(a, busca, db.precos_referencia(busca["id"]), cfg)
            nivel = 2 if info and info["nivel"] in (analise.FORTE, analise.BOA) else 0
            db.gravar_anuncio(a, busca["id"], valido_media=False, alertado=nivel)
            if nivel:
                self.avisar(formatar(titulo, preco, info, busca, grupo, link_post,
                                     links[0] if links else ""), foto_bytes)
                enviados += 1
        return enviados

    async def _rodar(self):
        from telethon import TelegramClient, events
        c = config.carregar()
        grupos = [int(g) for g in c["tg_grupos"]]
        cliente = TelegramClient(str(SESSAO), int(c["tg_api_id"]), c["tg_api_hash"])
        await cliente.connect()
        if not await cliente.is_user_authorized():
            self.ultimo_erro = "sessão do Telegram expirou: rode configurar_grupos.bat"
            log.warning(self.ultimo_erro)
            return

        @cliente.on(events.NewMessage(chats=grupos))
        async def nova(evento):
            try:
                texto = evento.raw_text or ""
                if extrair_preco(texto) is None:
                    return
                chat = await evento.get_chat()
                foto = await evento.download_media(file=bytes) if evento.photo else None
                nome = getattr(chat, "title", None) or "grupo"
                n = await asyncio.to_thread(self.tratar, texto, chat, evento.id, nome, foto)
                if n:
                    log.info("alerta de promoção vindo de %s", nome)
            except Exception as e:
                self.ultimo_erro = str(e)
                log.exception("erro lendo mensagem de grupo")

        self.ativo = True
        log.info("lendo %d grupos/canais de promoção", len(grupos))
        await cliente.run_until_disconnected()

    def executar(self):
        """Roda numa thread própria; se cair, tenta de novo em 1 minuto."""
        while True:
            try:
                asyncio.run(self._rodar())
            except Exception as e:
                self.ultimo_erro = str(e)
                log.exception("leitor de grupos caiu; tentando de novo em 60 s")
            self.ativo = False
            if not configurado():
                return
            threading.Event().wait(60)
