"""Banco SQLite: buscas cadastradas e histórico de anúncios (base para a média de preço)."""
import json
import sqlite3
import threading
from datetime import datetime

from . import config

_trava = threading.Lock()
_con = sqlite3.connect(config.BANCO, check_same_thread=False)
_con.row_factory = sqlite3.Row
_con.executescript("""
CREATE TABLE IF NOT EXISTS buscas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    termo TEXT NOT NULL,
    excluir TEXT NOT NULL DEFAULT '[]',
    teto REAL,
    desconto INTEGER,
    ativa INTEGER NOT NULL DEFAULT 1,
    linha_base INTEGER NOT NULL DEFAULT 0,
    criada TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS anuncios (
    fonte TEXT NOT NULL,
    ad_id TEXT NOT NULL,
    busca_id INTEGER NOT NULL,
    titulo TEXT NOT NULL,
    preco REAL NOT NULL,
    url TEXT NOT NULL,
    valido_media INTEGER NOT NULL,
    alertado INTEGER NOT NULL DEFAULT 0,
    visto_em TEXT NOT NULL,
    PRIMARY KEY (fonte, ad_id, busca_id)
);
CREATE INDEX IF NOT EXISTS ix_anuncios_busca ON anuncios (busca_id, visto_em);
""")
if "foto" not in {r[1] for r in _con.execute("PRAGMA table_info(anuncios)")}:
    _con.execute("ALTER TABLE anuncios ADD COLUMN foto TEXT NOT NULL DEFAULT ''")
if "local" not in {r[1] for r in _con.execute("PRAGMA table_info(anuncios)")}:
    _con.execute("ALTER TABLE anuncios ADD COLUMN local TEXT NOT NULL DEFAULT ''")
_con.commit()


def _agora():
    return datetime.now().isoformat(timespec="seconds")


def _exec(sql, params=()):
    with _trava:
        cur = _con.execute(sql, params)
        _con.commit()
        return cur


def _todos(sql, params=()):
    with _trava:
        return [dict(r) for r in _con.execute(sql, params).fetchall()]


# ---- buscas ----

def nova_busca(termo, excluir, teto, desconto):
    cur = _exec("INSERT INTO buscas (termo, excluir, teto, desconto, criada) VALUES (?,?,?,?,?)",
                (termo, json.dumps(excluir, ensure_ascii=False), teto, desconto, _agora()))
    return cur.lastrowid


def listar_buscas(so_ativas=False):
    sql = "SELECT * FROM buscas" + (" WHERE ativa=1" if so_ativas else "") + " ORDER BY id"
    linhas = _todos(sql)
    for b in linhas:
        b["excluir"] = json.loads(b["excluir"])
    return linhas


def obter_busca(busca_id):
    r = _todos("SELECT * FROM buscas WHERE id=?", (busca_id,))
    if not r:
        return None
    r[0]["excluir"] = json.loads(r[0]["excluir"])
    return r[0]


def remover_busca(busca_id):
    _exec("DELETE FROM anuncios WHERE busca_id=?", (busca_id,))
    return _exec("DELETE FROM buscas WHERE id=?", (busca_id,)).rowcount


def atualizar_busca(busca_id, **campos):
    if "excluir" in campos:
        campos["excluir"] = json.dumps(campos["excluir"], ensure_ascii=False)
    sets = ", ".join(f"{k}=?" for k in campos)
    return _exec(f"UPDATE buscas SET {sets} WHERE id=?", (*campos.values(), busca_id)).rowcount


# ---- anúncios ----

def anuncio_existente(fonte, ad_id, busca_id):
    r = _todos("SELECT * FROM anuncios WHERE fonte=? AND ad_id=? AND busca_id=?", (fonte, ad_id, busca_id))
    return r[0] if r else None


def gravar_anuncio(a, busca_id, valido_media, alertado=False):
    _exec("""INSERT INTO anuncios (fonte, ad_id, busca_id, titulo, preco, url, valido_media, alertado, visto_em,
                                   foto, local)
             VALUES (?,?,?,?,?,?,?,?,?,?,?)
             ON CONFLICT(fonte, ad_id, busca_id) DO UPDATE SET
               preco=excluded.preco, titulo=excluded.titulo, visto_em=excluded.visto_em,
               foto=excluded.foto, local=excluded.local,
               alertado=MAX(anuncios.alertado, excluded.alertado)""",
          (a.fonte, a.id, busca_id, a.titulo, a.preco, a.url, int(valido_media), int(alertado), _agora(),
           a.foto or "", a.local or ""))


def precos_referencia(busca_id, limite=80):
    r = _todos("""SELECT preco FROM anuncios WHERE busca_id=? AND valido_media=1
                  ORDER BY visto_em DESC LIMIT ?""", (busca_id, limite))
    return [x["preco"] for x in r]


def ultimos_alertas(limite=15):
    return _todos("""SELECT a.*, b.termo FROM anuncios a JOIN buscas b ON b.id = a.busca_id
                     WHERE a.alertado>=1 ORDER BY a.visto_em DESC LIMIT ?""", (limite,))


def contar_alertas_hoje():
    hoje = datetime.now().date().isoformat()
    r = _todos("SELECT COUNT(*) n FROM anuncios WHERE alertado>=1 AND visto_em >= ?", (hoje,))
    return r[0]["n"]
