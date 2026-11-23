"""Coletor do Mercado Livre pela API oficial (precisa de app em developers.mercadolivre.com.br).

O site do ML exige login para acesso automatizado; a API oficial é o caminho permitido.
Fica desligado até `configurar_ml.py` salvar client_id, client_secret e refresh_token.
"""
import json
import time
import logging
import urllib.request
import urllib.parse
import urllib.error

from .base import Anuncio, FonteBloqueada
from .. import config

log = logging.getLogger("vigia.ml")
API = "https://api.mercadolibre.com"
ESTADO_NOME = "Minas Gerais"

_token = {"valor": None, "expira": 0}
_estado_id = {"valor": None}


def configurado():
    c = config.carregar()
    return bool(c.get("ml_client_id") and c.get("ml_client_secret") and c.get("ml_refresh_token"))


def _post_form(url, dados):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(dados).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def trocar_codigo(client_id, client_secret, codigo, redirect_uri):
    return _post_form(f"{API}/oauth/token", {
        "grant_type": "authorization_code", "client_id": client_id,
        "client_secret": client_secret, "code": codigo, "redirect_uri": redirect_uri,
    })


def _access_token():
    if _token["valor"] and time.time() < _token["expira"] - 60:
        return _token["valor"]
    c = config.carregar()
    try:
        r = _post_form(f"{API}/oauth/token", {
            "grant_type": "refresh_token", "client_id": c["ml_client_id"],
            "client_secret": c["ml_client_secret"], "refresh_token": c["ml_refresh_token"],
        })
    except urllib.error.HTTPError as e:
        raise FonteBloqueada(f"ML recusou renovar o token ({e.code}). Rode configurar_ml.bat de novo.")
    _token["valor"] = r["access_token"]
    _token["expira"] = time.time() + int(r.get("expires_in", 21600))
    if r.get("refresh_token") and r["refresh_token"] != c["ml_refresh_token"]:
        config.salvar({"ml_refresh_token": r["refresh_token"]})  # ML gira o refresh token
    return _token["valor"]


def _get(caminho, params):
    url = f"{API}{caminho}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_access_token()}",
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429):
            raise FonteBloqueada(f"API do ML respondeu {e.code} na busca: {e.read()[:200]!r}")
        raise


def buscar(termo, paginas=1):
    if not configurado():
        return []
    resultado = []
    for pagina in range(paginas):
        params = {"q": termo, "limit": 50, "offset": pagina * 50}
        if _estado_id["valor"]:
            params["state"] = _estado_id["valor"]
        dados = _get("/sites/MLB/search", params)
        if not _estado_id["valor"]:
            # descobre o id de Minas Gerais pelos filtros que a própria API devolve, e refaz
            for f in dados.get("available_filters", []):
                if f.get("id") == "state":
                    for v in f.get("values", []):
                        if v.get("name") == ESTADO_NOME:
                            _estado_id["valor"] = v["id"]
            if _estado_id["valor"]:
                params["state"] = _estado_id["valor"]
                dados = _get("/sites/MLB/search", params)
        for it in dados.get("results", []):
            if it.get("price") is None:
                continue
            end = it.get("address") or {}
            resultado.append(Anuncio(
                fonte="ml", id=it["id"], titulo=it["title"], preco=float(it["price"]),
                url=it.get("permalink", ""), local=f"{end.get('city_name', '')}".strip(),
                data="usado" if it.get("condition") == "used" else "novo",
                foto=(it.get("thumbnail") or "").replace("http://", "https://"),
            ))
        if len(dados.get("results", [])) < 50:
            break
    log.info("ML '%s': %d anúncios", termo, len(resultado))
    return resultado
