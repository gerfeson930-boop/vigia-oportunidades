"""O vigia: roda as buscas em intervalos (várias ao mesmo tempo), compara com a média e dispara alertas."""
import html
import logging
import queue
import random
import threading
import time
from datetime import datetime

from . import analise, config, db
from .fontes import enjoei, kabum, ml, olx, pelando, sodre
from .fontes.base import FonteBloqueada

log = logging.getLogger("vigia.monitor")

PAUSA_BLOQUEIO = 60 * 60   # 1 h sem tocar numa fonte que bloqueou
MAX_BOAS_RODADA = 20       # alertas "boa" com foto por rodada; o excedente vai para o resumo
MAX_LINHAS_RESUMO = 25
ALERTADO = {analise.LEVE: 1, analise.BOA: 2, analise.FORTE: 2}  # nível gravado no banco
NOMES_FONTE = {"olx": "OLX", "enjoei": "Enjoei", "ml": "Mercado Livre", "pelando": "Pelando",
               "kabum": "KaBuM", "leilao": "Leilão Sodré Santoro", "telegram": "grupo do Telegram"}
PROMOCOES = {"pelando", "kabum"}  # produto novo em loja: comparado com a média dos usados
QUEDA_LOJA = 0.90                 # loja: avisa quando o preço cai 10% ou mais desde a última vez
MAX_LEILOES_RODADA = 10


def formatar_leilao(a, termo):
    e = html.escape
    return "\n".join([
        f"🔨 <b>LEILÃO</b> · {e(a.data)}",
        f"📦 <b>{e(a.titulo[:200])}</b>",
        f"📍 {e(a.local)}  ·  Sodré Santoro",
        f"🔎 palavra-chave de leilão: {e(termo)}",
        f'<a href="{e(a.url)}">Ver lote e dar lance</a>',
    ])
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


def _brl(v):
    return f"R$ {v:,.0f}".replace(",", ".")


def _variacao(desconto):
    return f"-{desconto:.0f}%" if desconto >= 0 else f"+{-desconto:.0f}%"


def linha_resumo(a, info):
    e = html.escape
    desc = f"<b>{_variacao(info['desconto'])}</b> " if info.get("desconto") is not None else ""
    rotulo = "média usados" if a.fonte in PROMOCOES else "média"
    media = f" ({rotulo} {_brl(info['mediana'])})" if info.get("mediana") else ""
    if a.fonte in PROMOCOES:
        onde = f"🏷️ {a.local} via {NOMES_FONTE[a.fonte]}"
    elif a.fonte != "olx":
        onde = NOMES_FONTE.get(a.fonte, a.fonte)
    else:
        onde = a.local.split(",")[0] if a.local else ""
    return (f"• {desc}{_brl(a.preco)}{media} — <a href=\"{e(a.url)}\">{e(a.titulo[:55])}</a>"
            + (f" · {e(onde)}" if onde else ""))


def formatar_alerta(a, busca, info, motivo_extra=None):
    e = html.escape
    marcas = []
    if info.get("nivel") == analise.FORTE:
        marcas.append("🔥🔥 <b>PECHINCHA</b>: bem abaixo da média, vale correr")
    if info["suspeito"]:
        marcas.append("⚠️ preço baixo demais, confira se não é golpe")
    if info["defeito"]:
        marcas.append("🔧 com defeito / para conserto")
    if info["urgencia"]:
        marcas.append("⏱ vendedor com pressa: " + ", ".join(info["urgencia"]))
    promo = a.fonte in PROMOCOES
    rotulo = "média dos usados" if promo else "média"
    preco = f"💰 <b>{_brl(a.preco)}</b>"
    if info["mediana"] and info.get("desconto") is not None:
        preco += f"  ({rotulo} {_brl(info['mediana'])}, <b>{_variacao(info['desconto'])}</b>)"
    elif info["mediana"]:
        preco += f"  ({rotulo} {_brl(info['mediana'])})"
    icone = "🔥" if info.get("nivel") == analise.FORTE else ("🏷️" if promo else "🔔")
    if promo:
        marcas.insert(0, f"🏷️ <b>PROMOÇÃO</b> de loja, produto novo: {e(a.local)}")
        onde = f"🛒 {e(a.local)} (via {NOMES_FONTE[a.fonte]})  ·  {e(a.data)}"
    else:
        onde = f"📍 {e(a.local)}  ·  {NOMES_FONTE.get(a.fonte, a.fonte.upper())}  ·  {e(a.data)}"
    linhas = [
        preco,
        f"{icone} <b>{e(a.titulo)}</b>",
        "✅ " + "; ".join(info["motivos"] + ([motivo_extra] if motivo_extra else [])),
        *marcas,
        onde,
        f"🔎 busca #{busca['id']}: {e(busca['termo'])}",
        f'<a href="{e(a.url)}">Abrir anúncio</a>',
    ]
    return "\n".join(l for l in linhas if l.strip())


class Monitor:
    def __init__(self, avisar, avisar_album=None):
        """avisar(texto, foto=None) envia uma mensagem; avisar_album([(foto, legenda)]) envia fotos em álbum."""
        self.avisar = avisar
        self.avisar_album = avisar_album
        self.acordar = threading.Event()
        self.parar = threading.Event()
        self.bloqueio_ate = {}      # fonte -> timestamp
        self.devagar_ate = 0        # depois de um bloqueio, volta a 1 busca por vez por 1 h
        self.ultima_rodada = None
        self.ultimo_erro = None
        self._trava = threading.Lock()

    # ---- fontes ----
    def _fonte_livre(self, fonte):
        return time.time() >= self.bloqueio_ate.get(fonte, 0)

    def _bloquear(self, fonte, erro):
        with self._trava:
            if not self._fonte_livre(fonte):
                return  # outra busca em paralelo já registrou e avisou
            self.bloqueio_ate[fonte] = time.time() + PAUSA_BLOQUEIO
            self.devagar_ate = time.time() + PAUSA_BLOQUEIO
        log.warning("%s bloqueado: %s", fonte, erro)
        self.avisar(f"🚧 {NOMES_FONTE.get(fonte, fonte)} recusou o acesso ({html.escape(str(erro)[:150])}).\n"
                    f"Vou deixar essa fonte quieta por 1 hora e, nesse tempo, fazer 1 busca por vez.")

    def coletar(self, navegador, busca):
        """Busca em todas as fontes. Devolve (anuncios, fontes_que_responderam).

        Numa fonte em que a busca ainda não aprendeu os preços, pega mais anúncios (2 páginas no
        OLX; no Enjoei, sem o filtro de 24 h)."""
        base = busca["fontes_base"]
        anuncios, ok = [], set()
        fontes = [("olx", lambda aprende: olx.buscar(navegador, busca["termo"], 2 if aprende else 1)),
                  ("enjoei", lambda aprende: enjoei.buscar(navegador, busca["termo"], recentes=not aprende)),
                  ("pelando", lambda aprende: pelando.buscar(navegador, busca["termo"])),
                  ("kabum", lambda aprende: kabum.buscar(navegador, busca["termo"]))]
        if ml.configurado():
            fontes.append(("ml", lambda aprende: ml.buscar(busca["termo"], 2 if aprende else 1)))
        for fonte, buscar in fontes:
            if not self._fonte_livre(fonte):
                continue
            try:
                anuncios += buscar(fonte not in base)
                ok.add(fonte)
            except FonteBloqueada as e:
                self._bloquear(fonte, e)
            except Exception as e:  # uma fonte com problema não derruba as outras
                log.warning("%s falhou na busca #%s: %s", fonte, busca["id"], e)
        return anuncios, ok

    # ---- análise ----
    @staticmethod
    def _referencia(busca_id, fonte, cfg):
        """Média da própria plataforma quando há amostras; senão, de todas juntas."""
        so_fonte = db.precos_referencia(busca_id, fonte=fonte)
        return so_fonte if len(so_fonte) >= cfg["amostras_min"] else db.precos_referencia(busca_id)

    def processar(self, busca, anuncios, fontes_ok, cfg):
        """Grava os anúncios e devolve (alertas, resumo_da_busca_nova).

        Só alerta em fontes onde a busca já aprendeu os preços; nas outras, só aprende.
        Cada alerta é um dict: nivel, desconto, texto (card com foto), foto, linha (para o resumo).
        """
        alertas = []
        vistos = set()
        relevantes = 0
        for a in anuncios:
            if (a.fonte, a.id) in vistos or not analise.relevante(a.titulo, busca):
                continue
            vistos.add((a.fonte, a.id))
            relevantes += 1
            defeito = analise.tem_defeito(a.titulo)
            promo = a.fonte in PROMOCOES
            antigo = db.anuncio_existente(a.fonte, a.id, busca["id"])
            info = extra = None
            if promo and a.fonte in busca["fontes_base"]:
                usados = db.precos_referencia(busca["id"])
                if antigo is None:  # promoção/produto novo: compara com a média dos usados
                    info = analise.avaliar_promocao(a, busca, usados, cfg)
                elif antigo["alertado"] < 2 and a.preco <= antigo["preco"] * QUEDA_LOJA:
                    # o preço da loja caiu: avisa (no mínimo no resumo 💡)
                    queda = (1 - a.preco / antigo["preco"]) * 100
                    extra = f"preço caiu {queda:.0f}% na loja (era {_brl(antigo['preco'])})"
                    info = analise.avaliar_promocao(a, busca, usados, cfg) or {
                        "mediana": None, "amostras": 0, "defeito": False, "urgencia": [], "desconto": None,
                        "motivos": [], "suspeito": False, "nivel": analise.LEVE, "promocao": True}
                    if info["nivel"] is None:
                        info["nivel"] = analise.LEVE
                    if antigo["alertado"] and ALERTADO[info["nivel"]] <= antigo["alertado"] and queda < 20:
                        info = None  # já avisado nesse nível e a queda não é grande
            elif a.fonte in busca["fontes_base"]:
                ref = self._referencia(busca["id"], a.fonte, cfg)
                if antigo is None:
                    info = analise.avaliar(a, busca, ref, cfg)
                elif antigo["alertado"] < 2 and a.preco <= antigo["preco"] * 0.95:
                    # já conhecido, mas baixou de preço: reavalia (um "leve" pode virar pechincha)
                    info = analise.avaliar(a, busca, ref, cfg)
                    extra = f"baixou de {_brl(antigo['preco'])} para {_brl(a.preco)}"
                    if info and antigo["alertado"] and ALERTADO[info["nivel"]] <= antigo["alertado"]:
                        info = None  # já avisado nesse nível
            nivel = ALERTADO[info["nivel"]] if info else 0
            # produto novo de loja não entra na média dos usados
            db.gravar_anuncio(a, busca["id"], valido_media=not defeito and not promo, alertado=nivel)
            if info:
                alertas.append({"nivel": info["nivel"], "desconto": info.get("desconto") or 0,
                                "texto": formatar_alerta(a, busca, info, extra), "foto": a.foto,
                                "linha": linha_resumo(a, info) + (f" · 📉 {html.escape(extra)}" if extra else "")})
        if fontes_ok - busca["fontes_base"]:
            db.marcar_fontes_base(busca["id"], fontes_ok)
        resumo = None
        if not busca["linha_base"] and fontes_ok:
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
    def _trabalhador(self, fila, saida):
        """Thread com navegador próprio: pega buscas da fila e devolve o que coletou."""
        from playwright.sync_api import sync_playwright
        try:
            with sync_playwright() as p:
                navegador = p.chromium.launch(headless=True)
                ctx = navegador.new_context(locale="pt-BR", viewport={"width": 1366, "height": 900},
                                            user_agent=UA)
                try:
                    while not self.parar.is_set():
                        try:
                            busca = fila.get_nowait()
                        except queue.Empty:
                            break
                        try:
                            saida.put((busca, *self.coletar(ctx, busca), None))
                        except Exception as e:
                            saida.put((busca, [], set(), e))
                        time.sleep(random.uniform(2, 5))  # pausa entre buscas, para não martelar o site
                finally:
                    navegador.close()
        except Exception as e:  # navegador não abriu: devolve o erro para cada busca restante
            log.exception("trabalhador de coleta falhou")
            while True:
                try:
                    saida.put((fila.get_nowait(), [], set(), e))
                except queue.Empty:
                    break

    def _proximo_resultado(self, saida, trabalhadores):
        while True:  # espera o próximo resultado sem travar se as threads morrerem
            try:
                return saida.get(timeout=5)
            except queue.Empty:
                if self.parar.is_set():
                    return None
                if not any(t.is_alive() for t in trabalhadores) and saida.empty():
                    return None

    def rodada(self, p=None):
        cfg = config.carregar()
        buscas = db.listar_buscas(so_ativas=True)
        if not buscas:
            self.ultima_rodada = datetime.now()
            return
        paralelo = 1 if time.time() < self.devagar_ate else max(1, int(cfg.get("paralelo", 3)))
        fila, saida = queue.Queue(), queue.Queue()
        for b in buscas:
            fila.put(b)
        trabalhadores = [threading.Thread(target=self._trabalhador, args=(fila, saida), daemon=True,
                                          name=f"coleta-{i}") for i in range(min(paralelo, len(buscas)))]
        for t in trabalhadores:
            t.start()

        ordem = {analise.FORTE: 0, analise.BOA: 1, analise.LEVE: 2}
        boas_enviadas = 0
        resumos, leves = [], []  # leves: (desconto, linha), vão no resumo do fim da rodada
        for _ in buscas:
            resultado = self._proximo_resultado(saida, trabalhadores)
            if resultado is None:
                break
            busca, anuncios, fontes_ok, erro = resultado
            if erro:
                log.error("erro na busca #%s: %s", busca["id"], erro)
                self.ultimo_erro = f"{datetime.now():%d/%m %H:%M} busca #{busca['id']}: {erro}"
                continue
            try:
                alertas, resumo = self.processar(busca, anuncios, fontes_ok, cfg)
            except Exception as e:
                log.exception("erro processando a busca #%s", busca["id"])
                self.ultimo_erro = f"{datetime.now():%d/%m %H:%M} busca #{busca['id']}: {e}"
                continue
            if resumo:
                resumos.append(resumo)
            # pechinchas primeiro, depois boas; dentro de cada nível, maior desconto primeiro
            for al in sorted(alertas, key=lambda x: (ordem[x["nivel"]], -x["desconto"])):
                if al["nivel"] == analise.FORTE:
                    self.avisar(al["texto"], al["foto"] or None)  # pechincha sai sempre e na hora
                elif al["nivel"] == analise.BOA and boas_enviadas < MAX_BOAS_RODADA:
                    self.avisar(al["texto"], al["foto"] or None)
                    boas_enviadas += 1
                else:
                    leves.append((al["desconto"], al["linha"], al["foto"]))
        for t in trabalhadores:
            t.join(timeout=60)
        if not self.parar.is_set():
            self._leiloes(cfg)

        if leves:
            leves.sort(key=lambda x: -x[0])
            mostrar = leves[:MAX_LINHAS_RESUMO]
            extra = (f" Mostrando os {len(mostrar)} maiores; o resto está em 🔔 Achados."
                     if len(leves) > len(mostrar) else "")
            self.avisar(f"💡 <b>Também um pouco abaixo da média</b> ({len(leves)}), "
                        f"do maior para o menor desconto. Toque na foto para ver o link.{extra}")
            com_foto = [(foto, linha.removeprefix("• ")) for _, linha, foto in mostrar if foto]
            sem_foto = [linha for _, linha, foto in mostrar if not foto]
            if com_foto and self.avisar_album:
                self.avisar_album(com_foto)
            else:
                sem_foto = [linha for _, linha, _ in mostrar]
            if sem_foto:
                self.avisar("\n".join(sem_foto))
        if resumos:  # buscas novas: um resumo só, em vez de uma mensagem por busca
            cab = (f"📊 <b>Preços aprendidos</b> ({len(resumos)} buscas novas). A partir da próxima rodada:\n"
                   f"🔥 {cfg['desconto_forte']}%+ abaixo da média: pechincha, com foto, na hora\n"
                   f"✅ {cfg['desconto_padrao']}%+: boa oferta, com foto\n"
                   + (f"💡 {cfg['desconto_leve']}%+: no resumo do fim de cada rodada\n"
                      if cfg["desconto_leve"] else ""))
            texto = cab
            for r in resumos:
                if len(texto) + len(r) > 3800:
                    self.avisar(texto)
                    texto = ""
                texto += "\n" + r
            self.avisar(texto)
        self.ultima_rodada = datetime.now()

    def _leiloes(self, cfg):
        """Lotes novos da Sodré Santoro com as palavras-chave de leilão (1ª vez de cada termo só aprende)."""
        termos = cfg.get("leilao_termos") or sodre.TERMOS_PADRAO
        if not termos or not self._fonte_livre("leilao"):
            return
        base = set(cfg.get("leilao_base") or [])
        from playwright.sync_api import sync_playwright
        enviados, aprendidos = 0, set()
        try:
            with sync_playwright() as p:
                navegador = p.chromium.launch(headless=True)
                ctx = navegador.new_context(locale="pt-BR", viewport={"width": 1366, "height": 900},
                                            user_agent=UA)
                try:
                    for termo in termos:
                        if self.parar.is_set():
                            break
                        try:
                            lotes = sodre.buscar(ctx, termo)
                        except FonteBloqueada as e:
                            self._bloquear("leilao", e)
                            break
                        except Exception as e:
                            log.warning("leilão '%s' falhou: %s", termo, e)
                            continue
                        for a in lotes:
                            if db.anuncio_existente("leilao", a.id, 0):
                                continue  # lote já visto (em qualquer palavra-chave)
                            avisar = termo in base and enviados < MAX_LEILOES_RODADA
                            db.gravar_anuncio(a, 0, valido_media=False, alertado=2 if avisar else 0)
                            if avisar:
                                self.avisar(formatar_leilao(a, termo), a.foto or None)
                                enviados += 1
                        aprendidos.add(termo)
                        time.sleep(random.uniform(1, 3))
                finally:
                    navegador.close()
        except Exception:
            log.exception("erro nos leilões")
        if aprendidos - base:
            config.salvar({"leilao_base": sorted(base | aprendidos)})

    def rodada_unica(self):
        """Modo nuvem: uma rodada e encerra."""
        if not config.carregar()["pausado"]:
            self.rodada()

    def executar(self):
        while not self.parar.is_set():
            cfg = config.carregar()
            if not cfg["pausado"]:
                log.info("rodada iniciada")
                inicio = time.time()
                self.rodada()
                log.info("rodada concluída em %.0f s", time.time() - inicio)
            espera = cfg["intervalo_min"] * 60 + random.uniform(-60, 60)
            self.acordar.wait(timeout=max(60, espera))
            self.acordar.clear()
