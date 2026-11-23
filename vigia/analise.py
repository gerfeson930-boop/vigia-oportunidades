"""Filtros de relevância e a regra de "abaixo da média"."""
import re
import statistics
import unicodedata

# Anúncios com estas palavras não são o produto em si (a menos que a palavra esteja na busca).
ACESSORIOS = {
    "capa", "capinha", "case", "pelicula", "carregador", "fonte", "cabo", "suporte", "skin",
    "adesivo", "caixa", "embalagem", "controle", "jogo", "jogos",
    "carcaca", "dock", "compro", "procuro", "aluguel", "aluga",
    "alugo", "manutencao", "assistencia", "pulseira", "bolsa", "mochila",
    "dualsense", "joystick", "faceplate", "hd", "portal", "codigo", "resgate", "headset",
    "volante", "gift", "cartao", "cooler", "pelicula", "lente", "tripe",
}
# Só contam como acessório no início do título ("Tela iPhone 13"), não em "Notebook tela 15".
AMBIGUOS = {"tela", "display", "teclado", "bateria", "base"}
# Anúncios com defeito: ficam fora da média, mas podem virar alerta "para consertar".
DEFEITO = [
    "defeito", "quebrad", "trincad", "nao liga", "nao funciona", "para pecas", "pra pecas",
    "retirada de pecas", "sucata", "bloquead", "icloud", "conserto", "no estado", "sem garantia de funcionamento",
]
# Sinais de vendedor com pressa.
URGENCIA = [
    "urgente", "preciso vender", "vendo hoje", "mudanca", "aceito proposta", "abaixo da tabela",
    "queima", "desapego", "viagem", "barato", "oportunidade", "fechamento de loja", "liquidacao",
]


SINONIMOS = [
    (r"\bplay ?station ?(\d)\b", r"ps\1"), (r"\bplay (\d)\b", r"ps\1"),
    (r"\bx ?box\b", "xbox"), (r"\bmac ?book\b", "macbook"), (r"\bair ?pods\b", "airpods"),
    (r"\bthink ?pad\b", "thinkpad"), (r"\bi ?pad\b", "ipad"), (r"\bi ?phone\b", "iphone"),
]
PALAVRAS_VAZIAS = {"de", "da", "do", "das", "dos", "e", "com", "para", "pra", "a", "o", "em"}


def normalizar(txt):
    txt = unicodedata.normalize("NFKD", txt.lower())
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    txt = re.sub(r"[^a-z0-9]+", " ", txt).strip()
    for padrao, troca in SINONIMOS:
        txt = re.sub(padrao, troca, txt)
    return txt


def _palavras(txt):
    return set(normalizar(txt).split()) - PALAVRAS_VAZIAS


def interpretar_comando(texto):
    """'iphone 13 -pro -max ate 2500 desc 30' -> (termo, excluir, teto, desconto)."""
    teto = desconto = None
    m = re.search(r"\b(?:ate|até)\s+r?\$?\s*([\d\.]+)", texto, re.I)
    if m:
        teto = float(m.group(1).replace(".", ""))
        texto = texto[:m.start()] + texto[m.end():]
    m = re.search(r"\bdesc(?:onto)?\s+(\d{1,2})\s*%?", texto, re.I)
    if m:
        desconto = int(m.group(1)) or None
        texto = texto[:m.start()] + texto[m.end():]
    m = re.search(r"\btodos\b", texto, re.I)
    if m:
        desconto = 0
        texto = texto[:m.start()] + texto[m.end():]
    excluir = [normalizar(p[1:]) for p in texto.split() if p.startswith("-") and len(p) > 1]
    termo = " ".join(p for p in texto.split() if not p.startswith("-")).strip()
    return termo, excluir, teto, desconto


def relevante(titulo, busca):
    """O título precisa conter todas as palavras da busca e nenhuma excluída/acessório."""
    pal_titulo = _palavras(titulo)
    norm_titulo = " " + normalizar(titulo) + " "
    pal_busca = _palavras(busca["termo"])
    sem_espaco = norm_titulo.replace(" ", "")
    for p in pal_busca:
        # aceita a palavra exata, o começo de uma palavra ('13' em '13pro') ou grafia junta/separada ('ps5' x 'ps 5')
        if p in pal_titulo or any(w.startswith(p) and not w[len(p):].isdigit() for w in pal_titulo):
            continue
        if normalizar(busca["termo"]).replace(" ", "") in sem_espaco:
            continue
        return False
    for p in busca["excluir"]:
        if f" {p} " in norm_titulo:
            return False
    if (pal_titulo & ACESSORIOS) - pal_busca:
        return False
    inicio = set(normalizar(titulo).split()[:2])
    if (inicio & AMBIGUOS) - pal_busca:
        return False
    return True


def tem_defeito(titulo):
    t = normalizar(titulo)
    return any(d in t for d in DEFEITO)


def tem_urgencia(titulo):
    t = normalizar(titulo)
    return [u for u in URGENCIA if u in t]


def mediana_robusta(precos):
    """Mediana após descartar valores absurdos (iscas de R$ 1, preços digitados errado)."""
    if not precos:
        return None
    med = statistics.median(precos)
    filtrados = [p for p in precos if med * 0.3 <= p <= med * 3]
    return statistics.median(filtrados) if filtrados else med


def avaliar(anuncio, busca, precos_ref, cfg):
    """Decide se vale alertar. Retorna dict com o motivo, ou None."""
    defeito = tem_defeito(anuncio.titulo)
    urg = tem_urgencia(anuncio.titulo)
    if busca.get("desconto") == 0:  # modo "todos": avisa qualquer anúncio novo (bom para lotes)
        return {"mediana": mediana_robusta(precos_ref), "amostras": len(precos_ref), "defeito": defeito,
                "urgencia": urg, "desconto": None, "motivos": ["anúncio novo"], "suspeito": False}
    desc_exigido = busca.get("desconto") or cfg["desconto_padrao"]
    if urg:
        desc_exigido = max(5, desc_exigido - cfg["bonus_urgencia"])
    if defeito:
        desc_exigido = max(desc_exigido, 50)

    med = mediana_robusta(precos_ref) if len(precos_ref) >= cfg["amostras_min"] else None
    info = {"mediana": med, "amostras": len(precos_ref), "defeito": defeito,
            "urgencia": urg, "desconto": None, "motivos": [], "suspeito": False}

    if med:
        desconto = (1 - anuncio.preco / med) * 100
        info["desconto"] = desconto
        # Muito abaixo da média quase sempre é outro produto (jogo, controle, capa), isca ou golpe.
        if anuncio.preco < med * (0.2 if defeito else 0.35):
            return None
        if desconto >= desc_exigido:
            info["motivos"].append(f"{desconto:.0f}% abaixo da média")
            info["suspeito"] = anuncio.preco < med * 0.5 and not defeito
    if busca.get("teto") and anuncio.preco <= busca["teto"] and not defeito:
        info["motivos"].append(f"dentro do seu teto de R$ {busca['teto']:,.0f}".replace(",", "."))
    return info if info["motivos"] else None
