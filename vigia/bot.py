"""Comandos do bot no Telegram. Só o primeiro chat que mandar /start é atendido (bot privado)."""
import html
import logging
import re

from . import analise, config, db
from .fontes import ml

log = logging.getLogger("vigia.bot")

COMANDOS = [
    ("achados", "Últimos achados salvos"),
    ("nova", "Nova busca: /nova iphone 13 -pro ate 2500"),
    ("lista", "Ver suas buscas"),
    ("remove", "Apagar busca: /remove 3"),
    ("desliga", "Desligar uma busca: /desliga 3"),
    ("liga", "Religar uma busca: /liga 3"),
    ("faixas", "Ver as faixas de desconto"),
    ("forte", "% para 🔥 pechincha: /forte 35"),
    ("desconto", "% para ✅ boa oferta: /desconto 25 ou /desconto 3 40"),
    ("leve", "% para 💡 resumo: /leve 12 (0 desliga)"),
    ("pacote", "Adicionar as buscas de revenda sugeridas"),
    ("agora", "Rodar as buscas agora"),
    ("pausa", "Pausar tudo"),
    ("retoma", "Retomar tudo"),
    ("status", "Situação do vigia"),
    ("pessoas", "Quem recebe os alertas (compartilhar)"),
    ("ajuda", "Como usar"),
]

AJUDA = """<b>Vigia de oportunidades</b> (OLX em MG, Enjoei Brasil todo e promoções do Pelando{ml})

Use os botões aqui embaixo, ou <b>digite o nome de um produto</b> para começar a vigiar.
🔔 <b>Achados</b> mostra os últimos alertas com link.

<b>/nova</b> termo [opções] cria uma busca com opções:
• <code>-palavra</code> exclui anúncios com essa palavra
• <code>ate 2500</code> também avisa qualquer anúncio até esse preço
• <code>desc 30</code> exige 30% abaixo da média (padrão {desc}%)
• <code>todos</code> avisa todo anúncio novo (bom para "vendo lote")

Exemplos:
<code>/nova iphone 13 -pro -max -mini ate 2300</code>
<code>/nova rtx 3060 desc 20</code>
<code>/nova lote eletronicos todos</code>

Como funciona: na 1ª rodada eu só aprendo os preços (sem alertas). Depois, para cada anúncio novo:
🔥 <b>{forte}%+</b> abaixo da média: pechincha, com foto, sai na hora e sempre primeiro
✅ <b>{desc}%+</b>: boa oferta, com foto
💡 <b>{leve}</b>: entra no resumo do fim da rodada, do maior para o menor desconto
Ajuste com /forte, /desconto e /leve. Com "urgente", "mudança", "aceito proposta" etc. exijo {bonus} pontos a menos. "Com defeito" fica fora da média e só vira alerta se estiver 50% abaixo.
Rodo a cada {intervalo} min."""

PACOTE = [
    # modelos específicos dão médias mais justas que termos genéricos ("thinkpad" mistura T410 e P16)
    # notebooks
    "thinkpad t470", "thinkpad t480", "thinkpad t490", "thinkpad t14", "thinkpad e14", "thinkpad x13",
    "latitude 5490", "latitude 7490", "latitude 5420", "latitude 7420",
    "macbook air m1", "macbook air m2", "macbook air m3", "macbook pro m1",
    "notebook gamer rtx 3050", "ideapad gaming",
    # iPhone
    "iphone 11 -pro -max", "iphone 12 -pro -max -mini", "iphone 12 pro -max",
    "iphone 13 -pro -max -mini", "iphone 13 pro -max", "iphone 13 pro max",
    "iphone 14 -pro -max -plus", "iphone 14 pro -max", "iphone 15 -pro -max -plus", "iphone 15 pro -max",
    # Samsung
    "galaxy s21 fe", "galaxy s22 -ultra", "galaxy s23 -ultra -fe", "galaxy s23 ultra",
    "galaxy s24 -ultra -fe", "galaxy a15", "galaxy a34", "galaxy a54", "galaxy a55",
    # consoles
    "ps5 -jogo", "ps5 slim -jogo", "ps4 pro -jogo", "xbox series s", "xbox series x -jogo",
    "nintendo switch -jogo -oled", "nintendo switch oled -jogo", "steam deck",
    # placas de vídeo e peças
    "rtx 3060 -ti", "rtx 3060 ti", "rtx 3070 -ti", "rtx 3070 ti", "rtx 4060 -ti", "rtx 4060 ti",
    "rtx 4070", "rx 6600", "ryzen 5 5600", "ryzen 7 5700x", "i5 12400",
    "ssd nvme 1tb", "memoria ddr4 16gb", "memoria ddr5",
    # monitores
    "monitor 144hz 24", "monitor 144hz 27", "monitor 165hz", "monitor ultrawide",
    # tablets
    "ipad 9 -air -pro -mini", "ipad 10 -air -pro -mini", "ipad air", "ipad pro", "galaxy tab s6 lite", "galaxy tab s9",
    # relógios
    "apple watch se", "apple watch series 8", "apple watch series 9", "galaxy watch 5", "galaxy watch 6",
    # fones e caixas de som
    "airpods pro", "airpods 3", "jbl charge 5", "jbl flip 6", "jbl boombox",
    "sony wh 1000xm4", "sony wh 1000xm5",
    # ferramentas
    "parafusadeira dewalt", "parafusadeira makita", "furadeira makita", "furadeira dewalt",
    "martelete bosch", "esmerilhadeira bosch", "serra makita",
    # bikes e patinetes
    "patinete eletrico", "patinete xiaomi", "bicicleta eletrica", "bike speed", "mountain bike aro 29",
    # câmeras e drones
    "sony a6400", "canon t7", "nikon d3500", "gopro hero", "drone dji mini", "lente canon",
    # escritório
    "cadeira ergonomica", "cadeira gamer", "mesa escritorio",
    "lote eletronicos todos", "lote celulares todos", "lote notebooks todos",
    "queima de estoque -roupa -roupas todos", "fechamento de loja -ponto -aluguel -roupa todos",
]


# Botões fixos embaixo do chat: tocar neles equivale ao comando.
BOTOES = {
    "🔔 Achados": "achados", "📋 Buscas": "lista", "▶️ Rodar agora": "agora",
    "📊 Status": "status", "❓ Ajuda": "ajuda",
}
TECLADO = {
    "keyboard": [[{"text": "🔔 Achados"}, {"text": "📋 Buscas"}],
                 [{"text": "▶️ Rodar agora"}, {"text": "📊 Status"}, {"text": "❓ Ajuda"}]],
    "resize_keyboard": True, "is_persistent": True,
    "input_field_placeholder": "Digite um produto para vigiar (ex.: iphone 13)",
}


# Comandos que só o dono pode usar; quem foi liberado usa o resto (ver, rodar, adicionar busca).
SO_DONO = {"remove", "desliga", "liga", "desconto", "forte", "leve", "pausa", "retoma", "pacote",
           "pessoas", "liberar", "recusar", "tirar"}


def _nome(msg):
    de = msg.get("from") or {}
    nome = " ".join(x for x in (de.get("first_name"), de.get("last_name")) if x) or "Sem nome"
    return nome + (f" (@{de['username']})" if de.get("username") else "")


class Bot:
    def __init__(self, tg, monitor):
        self.tg = tg
        self.monitor = monitor
        self._atual = None  # chat que mandou o comando em andamento (para responder só a ele)
        self._usuario = None

    def _usuario_bot(self):
        if self._usuario is None:
            try:
                self._usuario = self.tg.eu().get("username", "")
            except Exception:
                return "seu_bot"
        return self._usuario

    def chat(self):
        return config.carregar().get("chat_id")

    def destinos(self):
        """Dono + pessoas liberadas: todos recebem os alertas."""
        c = config.carregar()
        chats = [c["chat_id"]] if c.get("chat_id") else []
        return chats + [int(x) for x in (c.get("convidados") or {})]

    def _enviar(self, chat, texto, foto=None):
        try:
            if foto:
                self.tg.foto(chat, foto, texto[:1024], TECLADO)
            else:
                self.tg.mensagem(chat, texto, TECLADO)
        except Exception:
            log.exception("falha ao enviar mensagem para %s", chat)

    def avisar(self, texto, foto=None):
        """Alerta: vai para o dono e para todas as pessoas liberadas."""
        chats = self.destinos()
        if not chats:
            log.info("sem chat cadastrado; alerta descartado")
        for chat in chats:
            self._enviar(chat, texto, foto)

    def avisar_album(self, itens):
        """itens: [(url_foto, legenda)]. Manda em álbuns de até 10; o que ficar sem foto vai como texto."""
        for chat in self.destinos():
            sobras = []
            for i in range(0, len(itens), 10):
                try:
                    sobras += self.tg.album(chat, itens[i:i + 10])
                except Exception:
                    log.exception("falha ao enviar álbum")
                    sobras += [legenda for _, legenda in itens[i:i + 10]]
            if sobras:
                self._enviar(chat, "\n\n".join(sobras))

    def responder(self, texto, foto=None):
        """Resposta a um comando: só para quem mandou."""
        if self._atual is not None:
            self._enviar(self._atual, texto, foto)
        else:
            self.avisar(texto, foto)

    def _pedir_acesso(self, msg, chat_id):
        c = config.carregar()
        pendentes = c.get("pendentes") or {}
        if str(chat_id) in pendentes:
            self.tg.mensagem(chat_id, "⏳ Seu pedido já foi enviado. Aguarde o dono do vigia liberar.")
            return
        pendentes[str(chat_id)] = _nome(msg)
        config.salvar({"pendentes": pendentes})
        self.tg.mensagem(chat_id, "👋 Pedido enviado ao dono deste vigia. Assim que ele liberar, "
                                  "você começa a receber os alertas aqui.")
        self._enviar(c["chat_id"], f"👤 <b>{html.escape(_nome(msg))}</b> quer usar o vigia "
                                   f"(receber os mesmos alertas que você).\n\n"
                                   f"✅ Liberar: /liberar_{chat_id}\n❌ Recusar: /recusar_{chat_id}")

    def tratar(self, msg):
        chat_id = msg["chat"]["id"]
        texto = (msg.get("text") or "").strip()
        c = config.carregar()
        dono = c.get("chat_id")
        if dono is None and texto.startswith("/start"):
            config.salvar({"chat_id": chat_id})
            self.tg.mensagem(chat_id, "✅ Pronto, este chat agora recebe os alertas.", TECLADO)
            if not db.listar_buscas():  # já sobe as buscas de revenda e começa a vigiar
                self._atual = chat_id
                self.c_pacote("")
                self.monitor.acordar.set()
                self.responder("▶️ Primeira rodada começando agora. Ela só aprende os preços e te "
                               "manda a média de cada busca; os alertas vêm a partir da segunda.")
            return
        e_dono = chat_id == dono
        if not e_dono and str(chat_id) not in (c.get("convidados") or {}):
            log.info("mensagem de quem ainda não tem acesso (tipo de chat: %s)", msg["chat"].get("type"))
            if msg["chat"].get("type") == "private" and dono is not None:
                self._pedir_acesso(msg, chat_id)
            else:
                self.tg.mensagem(chat_id, "Este bot é privado.")
            return
        self._atual = chat_id
        if texto in BOTOES:
            cmd, arg = BOTOES[texto], ""
        elif not texto.startswith("/"):
            cmd, arg = "nova", texto  # texto solto vira uma busca nova
        else:
            cmd, _, arg = texto.partition(" ")
            cmd = cmd[1:].split("@")[0].lower()
            arg = arg.strip()
            m = re.fullmatch(r"(liberar|recusar|tirar)_(-?\d+)", cmd)  # comandos clicáveis
            if m:
                cmd, arg = m.group(1), m.group(2)
        if cmd in SO_DONO and not e_dono:
            return self.responder("🔒 Só o dono do vigia pode fazer isso.")
        fn = getattr(self, f"c_{cmd}", None)
        if not fn:
            return self.responder("Comando desconhecido. /ajuda")
        try:
            fn(arg)
        except ValueError as e:  # erro de uso: só explica
            self.responder(f"⚠️ {html.escape(str(e))}")
        except Exception as e:
            log.exception("erro no comando %s", cmd)
            self.responder(f"Deu erro: {html.escape(str(e))}")

    def _ajuda(self, dono=None):
        c = config.carregar()
        if dono is None:
            dono = self._atual is None or self._atual == c.get("chat_id")
        leve = f"{c['desconto_leve']}%+" if c["desconto_leve"] else "desligado"
        texto = AJUDA.format(ml=" + Mercado Livre" if ml.configurado() else "", desc=c["desconto_padrao"],
                             forte=c["desconto_forte"], leve=leve,
                             bonus=c["bonus_urgencia"], intervalo=c["intervalo_min"])
        if dono:
            texto += ("\n\n👥 <b>Compartilhar:</b> mande o link t.me/" + self._usuario_bot()
                      + " para um amigo; quando ele mandar /start, você recebe o pedido para liberar. "
                        "Veja e gerencie em /pessoas.")
        else:
            texto += ("\n\n👥 Você usa o vigia de outra pessoa: recebe os mesmos alertas, pode ver achados, "
                      "buscas e status e adicionar produtos. Apagar buscas e mudar as faixas é com o dono.")
        return texto

    def _id(self, arg):
        try:
            return int(arg.split()[0].lstrip("#"))
        except (ValueError, IndexError):
            raise ValueError("informe o número da busca (veja /lista)")

    def _criar(self, texto):
        termo, excluir, teto, desconto = analise.interpretar_comando(texto)
        if len(analise.normalizar(termo)) < 2:
            raise ValueError("faltou o termo. Ex.: /nova notebook thinkpad -tela ate 1500")
        return db.nova_busca(termo, excluir, teto, desconto), termo

    # ---- comandos ----
    def c_start(self, arg):
        self.responder(self._ajuda())

    def c_ajuda(self, arg):
        self.responder(self._ajuda())

    def c_achados(self, arg):
        itens = db.ultimos_alertas(10)
        if not itens:
            return self.responder("Nenhum achado ainda. Os alertas começam depois da primeira rodada "
                                  "de cada busca.")
        self.responder(f"🔔 <b>Últimos {len(itens)} achados</b> (do mais antigo ao mais recente):")
        for a in reversed(itens):  # o mais recente fica por último, perto do campo de digitar
            preco = f"R$ {a['preco']:,.0f}".replace(",", ".")
            texto = (f"💰 <b>{preco}</b>\n🔔 <b>{html.escape(a['titulo'])}</b>\n"
                     f"📍 {html.escape(a.get('local') or '')}  ·  visto {a['visto_em'][8:10]}/{a['visto_em'][5:7]}"
                     f"\n🔎 {html.escape(a['termo'])}\n"
                     f'<a href="{html.escape(a["url"])}">Abrir anúncio</a>')
            self.responder(texto, a.get("foto") or None)

    def c_nova(self, arg):
        bid, termo = self._criar(arg)
        self.responder(f"🆕 Busca #{bid} <b>{html.escape(termo)}</b> criada. Vou aprender os preços na "
                       f"próxima rodada e te mando a média. (Para rodar já: /agora)")

    def c_pacote(self, arg):
        existentes = {analise.normalizar(b["termo"]) for b in db.listar_buscas()}
        criadas = []
        for linha in PACOTE:
            termo = analise.interpretar_comando(linha)[0]
            if analise.normalizar(termo) not in existentes:
                criadas.append(f"#{self._criar(linha)[0]} {termo}")
        if not criadas:
            return self.responder("O pacote já estava todo cadastrado.")
        self.responder(f"📦 {len(criadas)} buscas adicionadas:\n" + "\n".join(map(html.escape, criadas)) +
                       "\n\nApague o que não quiser com /remove N. A primeira rodada só aprende preços.")

    def c_lista(self, arg):
        buscas = db.listar_buscas()
        if not buscas:
            return self.responder("Nenhuma busca ainda. Use /nova ou /pacote.")
        cfg = config.carregar()
        linhas = []
        for b in buscas:
            ref = db.precos_referencia(b["id"])
            med = analise.mediana_robusta(ref)
            partes = [f"{'🟢' if b['ativa'] else '⚪️'} <b>#{b['id']}</b> {html.escape(b['termo'])}"]
            if b["excluir"]:
                partes.append("sem: " + ", ".join(b["excluir"]))
            if b["teto"]:
                partes.append(f"teto R$ {b['teto']:,.0f}".replace(",", "."))
            if b["desconto"] == 0:
                partes.append("todos")
            else:
                partes.append(f"{b['desconto'] or cfg['desconto_padrao']}%")
            if med:
                partes.append(f"média R$ {med:,.0f} ({len(ref)})".replace(",", "."))
            elif not b["linha_base"]:
                partes.append("aguardando 1ª rodada")
            linhas.append(" · ".join(partes))
        texto = "\n".join(linhas)
        for i in range(0, len(texto), 3800):  # limite de tamanho do Telegram
            self.responder(texto[i:i + 3800])

    def c_remove(self, arg):
        bid = self._id(arg)
        self.responder(f"🗑 Busca #{bid} apagada." if db.remover_busca(bid) else "Busca não encontrada.")

    def c_desliga(self, arg):
        bid = self._id(arg)
        self.responder(f"⚪️ Busca #{bid} desligada." if db.atualizar_busca(bid, ativa=0) else "Não encontrada.")

    def c_liga(self, arg):
        bid = self._id(arg)
        self.responder(f"🟢 Busca #{bid} ligada." if db.atualizar_busca(bid, ativa=1) else "Não encontrada.")

    def c_desconto(self, arg):
        nums = [int(x) for x in arg.replace("%", " ").split() if x.isdigit()]
        if len(nums) == 1 and 5 <= nums[0] <= 90:
            config.salvar({"desconto_padrao": nums[0]})
            return self.c_faixas("")
        if len(nums) == 2 and 5 <= nums[1] <= 90:
            ok = db.atualizar_busca(nums[0], desconto=nums[1])
            return self.responder(f"Busca #{nums[0]} agora exige {nums[1]}% para ✅ boa oferta."
                                  if ok else "Não encontrada.")
        self.responder("Use /desconto 25 (todas) ou /desconto 3 40 (só a busca #3). Entre 5 e 90.")

    def c_forte(self, arg):
        nums = [int(x) for x in arg.replace("%", " ").split() if x.isdigit()]
        if len(nums) != 1 or not 10 <= nums[0] <= 90:
            raise ValueError("use /forte 35 (entre 10 e 90)")
        config.salvar({"desconto_forte": nums[0]})
        self.c_faixas("")

    def c_leve(self, arg):
        nums = [int(x) for x in arg.replace("%", " ").split() if x.isdigit()]
        if len(nums) != 1 or not (nums[0] == 0 or 5 <= nums[0] <= 60):
            raise ValueError("use /leve 12 (entre 5 e 60), ou /leve 0 para desligar o resumo")
        config.salvar({"desconto_leve": nums[0]})
        self.c_faixas("")

    def c_faixas(self, arg):
        c = config.carregar()
        forte = max(c["desconto_forte"], c["desconto_padrao"] + 5)
        avisos = []
        if c["desconto_leve"] and c["desconto_leve"] >= c["desconto_padrao"]:
            avisos.append("⚠️ o resumo (💡) só pega o que fica abaixo da faixa ✅; com esses números ele fica vazio.")
        if forte != c["desconto_forte"]:
            avisos.append(f"(🔥 ajustado para {forte}%: precisa ficar pelo menos 5 pontos acima do ✅)")
        self.responder(
            "<b>Faixas de desconto</b> (em relação à média de cada produto):\n"
            f"🔥 pechincha: <b>{forte}%</b> ou mais, com foto, na hora, sempre primeiro  ·  /forte\n"
            f"✅ boa oferta: <b>{c['desconto_padrao']}%</b> ou mais, com foto  ·  /desconto\n"
            + (f"💡 resumo da rodada: <b>{c['desconto_leve']}%</b> ou mais  ·  /leve\n" if c["desconto_leve"]
               else "💡 resumo da rodada: desligado  ·  /leve 12 para ligar\n")
            + "\n".join(avisos))

    def c_agora(self, arg):
        self.monitor.acordar.set()
        self.responder("▶️ Rodando as buscas agora.")

    def c_pausa(self, arg):
        config.salvar({"pausado": True})
        self.responder("⏸ Vigia pausado. /retoma para voltar.")

    def c_retoma(self, arg):
        config.salvar({"pausado": False})
        self.monitor.acordar.set()
        self.responder("▶️ Vigia retomado.")

    # ---- pessoas ----
    def _alterar_pessoa(self, arg, de, para):
        try:
            chat = str(int(arg))
        except ValueError:
            raise ValueError("pessoa não encontrada; veja /pessoas")
        c = config.carregar()
        origem, destino = dict(c.get(de) or {}), dict(c.get(para) or {}) if para else None
        if chat not in origem:
            raise ValueError("pessoa não encontrada (talvez já tenha sido tratada); veja /pessoas")
        nome = origem.pop(chat)
        mudancas = {de: origem}
        if para:
            destino[chat] = nome
            mudancas[para] = destino
        config.salvar(mudancas)
        return int(chat), nome

    def c_liberar(self, arg):
        chat, nome = self._alterar_pessoa(arg, "pendentes", "convidados")
        self._enviar(chat, "✅ Liberado! A partir de agora você recebe os alertas do vigia aqui.\n\n" + self._ajuda(False))
        self.responder(f"✅ {html.escape(nome)} liberado. Ele recebe os mesmos alertas que você. "
                       f"Para tirar depois: /pessoas")

    def c_recusar(self, arg):
        chat, nome = self._alterar_pessoa(arg, "pendentes", None)
        self._enviar(chat, "O dono do vigia não liberou o acesso.")
        self.responder(f"❌ Pedido de {html.escape(nome)} recusado.")

    def c_tirar(self, arg):
        chat, nome = self._alterar_pessoa(arg, "convidados", None)
        self._enviar(chat, "Seu acesso ao vigia foi encerrado pelo dono.")
        self.responder(f"🚪 {html.escape(nome)} não recebe mais os alertas.")

    def c_pessoas(self, arg):
        c = config.carregar()
        conv, pend = c.get("convidados") or {}, c.get("pendentes") or {}
        linhas = ["👥 <b>Pessoas com acesso</b> (recebem os mesmos alertas que você):"]
        linhas += [f"• {html.escape(n)} · tirar: /tirar_{i}" for i, n in conv.items()] or ["• ninguém ainda"]
        if pend:
            linhas.append("\n⏳ <b>Pedidos aguardando:</b>")
            linhas += [f"• {html.escape(n)} · /liberar_{i} · /recusar_{i}" for i, n in pend.items()]
        linhas.append("\nPara convidar alguém, mande o link do bot: "
                      f"t.me/{self._usuario_bot()}. Quando a pessoa mandar /start, "
                      "o pedido aparece aqui para você liberar.")
        self.responder("\n".join(linhas))

    def c_status(self, arg):
        import time
        cfg = config.carregar()
        ativas = len(db.listar_buscas(so_ativas=True))
        ult = self.monitor.ultima_rodada
        linhas = [
            "⏸ pausado" if cfg["pausado"] else "▶️ rodando",
            f"{ativas} buscas ativas, a cada {cfg['intervalo_min']} min",
            f"última rodada: {ult:%d/%m %H:%M}" if ult else "última rodada: ainda não terminou nenhuma",
            f"alertas hoje: {db.contar_alertas_hoje()}",
            "Mercado Livre: " + ("ligado" if ml.configurado() else "desligado (rode configurar_ml.bat)"),
        ]
        for fonte, ate in self.monitor.bloqueio_ate.items():
            if ate > time.time():
                linhas.append(f"🚧 {fonte.upper()} em pausa por bloqueio até {time.strftime('%H:%M', time.localtime(ate))}")
        if self.monitor.ultimo_erro:
            linhas.append(f"último erro: {html.escape(self.monitor.ultimo_erro[:200])}")
        self.responder("\n".join(linhas))

    # ---- laço ----
    def ler_pendentes(self):
        """Modo nuvem: trata os comandos que chegaram desde a última execução e confirma no Telegram."""
        offset = config.carregar().get("tg_offset", 0)
        for u in self.tg.atualizacoes(offset, timeout=0):
            offset = u["update_id"] + 1
            config.salvar({"tg_offset": offset})  # salva antes: um comando com erro não repete para sempre
            if "message" in u:
                try:
                    self.tratar(u["message"])
                except Exception:
                    log.exception("erro tratando mensagem")
        if offset:
            self.tg.atualizacoes(offset, timeout=0)  # confirma o recebimento para o Telegram

    def executar(self, parar):
        try:
            self.tg.definir_comandos(COMANDOS)
        except Exception:
            log.exception("não consegui registrar o menu de comandos")
        offset = 0
        while not parar.is_set():
            try:
                for u in self.tg.atualizacoes(offset):
                    offset = u["update_id"] + 1
                    if "message" in u:
                        self.tratar(u["message"])
            except Exception:
                log.exception("erro lendo o Telegram; tentando de novo em 15 s")
                parar.wait(15)
