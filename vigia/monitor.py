"""O vigia: roda as buscas em intervalos, compara com a média e dispara alertas."""
import html
import logging
import random
import threading
import time
from datetime import datetime

from . import analise, config, db
from .fontes import ml, olx
from .fontes.base import FonteBloqueada

log = logging.getLogger("vigia.monitor")

PAUSA_BLOQUEIO = 60 * 60   # 1 h sem tocar numa fonte que bloqueou
MAX_ALERTAS_RODADA = 15


def _brl(v):
    return f"R$ {v:,.0f}".replace(",", ".")


def formatar_alerta(a, busca, info, motivo_extra=None):
    e = html.escape
    marcas = []
    if info["suspeito"]:
        marcas.append("⚠️ preço baixo demais, confira se não é golpe")
    if info["defeito"]:
        marcas.append("🔧 com defeito / para conserto")
    if info["urgencia"]:
        marcas.append("⏱ vendedor com pressa: " + ", ".join(info["urgencia"]))
    linhas = [
        f"🔔 <b>{e(a.titulo)}</b>",
        f"💰 <b>{_brl(a.preco)}</b>" + (f"  ·  média {_brl(info['mediana'])} ({info['amostras']} anúncios)"
                                        if info["mediana"] else ""),
        "✅ " + "; ".join(info["motivos"] + ([motivo_extra] if motivo_extra else [])),
        *marcas,
        f"📍 {e(a.local)}  ·  {a.fonte.upper()}  ·  {e(a.data)}",
        f"🔎 busca #{busca['id']}: {e(busca['termo'])}",
        f'<a href="{e(a.url)}">Abrir anúncio</a>',
    ]
    return "\n".join(l for l in linhas if l.strip())


class Monitor:
    def __init__(self, avisar):
        """avisar(texto, foto=None) envia a mensagem ao usuário."""
        self.avisar = avisar
        self.acordar = threading.Event()
        self.parar = threading.Event()
        self.bloqueio_ate = {}      # fonte -> timestamp
        self.ultima_rodada = None
        self.ultimo_erro = None
        self._contexto = None

    # ---- navegador ----
    def _navegador(self, p):
        if self._contexto is None:
            self._contexto = p.chromium.launch_persistent_context(
                str(config.DADOS / "navegador"), headless=True, locale="pt-BR",
                viewport={"width": 1366, "height": 900},
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"),
            )
        return self._contexto

    def _fonte_livre(self, fonte):
        return time.time() >= self.bloqueio_ate.get(fonte, 0)

    def _bloquear(self, fonte, erro):
        self.bloqueio_ate[fonte] = time.time() + PAUSA_BLOQUEIO
        log.warning("%s bloqueado: %s", fonte, erro)
        self.avisar(f"🚧 {fonte.upper()} recusou o acesso ({html.escape(str(erro)[:150])}).\n"
                    f"Vou deixar essa fonte quieta por 1 hora e tento de novo.")

    # ---- uma busca ----
    def coletar(self, p, busca):
        paginas = 1 if busca["linha_base"] else 2
        anuncios = []
        if self._fonte_livre("olx"):
            try:
                anuncios += olx.buscar(self._navegador(p), busca["termo"], paginas)
            except FonteBloqueada as e:
                self._bloquear("olx", e)
        if ml.configurado() and self._fonte_livre("ml"):
            try:
                anuncios += ml.buscar(busca["termo"], paginas)
            except FonteBloqueada as e:
                self._bloquear("ml", e)
        return anuncios

    def processar(self, busca, anuncios, cfg):
        """Grava os anúncios e devolve a lista de alertas (texto, foto)."""
        alertas = []
        vistos = set()
        relevantes = 0
        for a in anuncios:
            if (a.fonte, a.id) in vistos or not analise.relevante(a.titulo, busca):
                continue
            vistos.add((a.fonte, a.id))
            relevantes += 1
            defeito = analise.tem_defeito(a.titulo)
            antigo = db.anuncio_existente(a.fonte, a.id, busca["id"])
            ref = db.precos_referencia(busca["id"])
            alertar = None
            if busca["linha_base"]:
                if antigo is None:
                    info = analise.avaliar(a, busca, ref, cfg)
                    if info:
                        alertar = formatar_alerta(a, busca, info)
                elif not antigo["alertado"] and a.preco <= antigo["preco"] * 0.95:
                    info = analise.avaliar(a, busca, ref, cfg)
                    if info:
                        alertar = formatar_alerta(a, busca, info,
                                                  f"baixou de {_brl(antigo['preco'])} para {_brl(a.preco)}")
            db.gravar_anuncio(a, busca["id"], valido_media=not defeito, alertado=bool(alertar))
            if alertar:
                alertas.append((alertar, a.foto))
        resumo = None
        if not busca["linha_base"]:
            db.atualizar_busca(busca["id"], linha_base=1)
            ref = db.precos_referencia(busca["id"])
            med = analise.mediana_robusta(ref)
            resumo = f"#{busca['id']} {html.escape(busca['termo'])}: "
            if busca.get("desconto") == 0:
                resumo += f"{relevantes} anúncios · avisa todo novo"
            elif len(ref) < cfg["amostras_min"]:
                resumo += f"{relevantes} anúncios · poucos para a média" + (f" ({_brl(med)})" if med else "")
            else:
                resumo += f"média <b>{_brl(med)}</b> ({relevantes} anúncios)"
        return alertas, resumo

    # ---- rodada ----
    def rodada(self, p):
        cfg = config.carregar()
        buscas = db.listar_buscas(so_ativas=True)
        enviados = 0
        resumos = []
        for b in buscas:
            if self.parar.is_set():
                return
            try:
                anuncios = self.coletar(p, b)
                alertas, resumo = self.processar(b, anuncios, cfg)
                if resumo:
                    resumos.append(resumo)
                for texto, foto in alertas:
                    if enviados >= MAX_ALERTAS_RODADA:
                        break
                    self.avisar(texto, foto or None)
                    enviados += 1
            except Exception as e:  # uma busca com problema não derruba as outras
                log.exception("erro na busca #%s", b["id"])
                self.ultimo_erro = f"{datetime.now():%d/%m %H:%M} busca #{b['id']}: {e}"
            time.sleep(random.uniform(4, 10))  # ritmo humano entre buscas
        if resumos:  # buscas novas: um resumo só, em vez de uma mensagem por busca
            cab = (f"📊 <b>Preços aprendidos</b> ({len(resumos)} buscas novas). A partir da próxima "
                   f"rodada aviso o que aparecer {cfg['desconto_padrao']}% abaixo da média.\n")
            texto = cab
            for r in resumos:
                if len(texto) + len(r) > 3800:
                    self.avisar(texto)
                    texto = ""
                texto += "\n" + r
            self.avisar(texto)
        if enviados >= MAX_ALERTAS_RODADA:
            self.avisar(f"Parei em {MAX_ALERTAS_RODADA} alertas nesta rodada para não lotar o chat. "
                        f"Se isso se repetir, aumente o desconto com /desconto.")
        self.ultima_rodada = datetime.now()

    def rodada_unica(self):
        """Modo nuvem: uma rodada e encerra."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                if not config.carregar()["pausado"]:
                    self.rodada(p)
            finally:
                if self._contexto:
                    self._contexto.close()
                    self._contexto = None

    def executar(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            while not self.parar.is_set():
                cfg = config.carregar()
                if not cfg["pausado"]:
                    log.info("rodada iniciada")
                    self.rodada(p)
                    log.info("rodada concluída")
                espera = cfg["intervalo_min"] * 60 + random.uniform(-60, 60)
                self.acordar.wait(timeout=max(60, espera))
                self.acordar.clear()
            if self._contexto:
                self._contexto.close()
