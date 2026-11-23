"""Testa, da máquina atual, se cada site responde às buscas (usado antes de migrar para um servidor).

python -m vigia.testar_fontes
"""
import sys

from playwright.sync_api import sync_playwright

from .fontes import enjoei, kabum, olx, pelando, sodre
from .fontes.base import FonteBloqueada
from .monitor import UA

TESTES = [
    ("OLX (MG)", lambda ctx: olx.buscar(ctx, "iphone 13", 1)),
    ("Enjoei", lambda ctx: enjoei.buscar(ctx, "iphone 13", recentes=False)),
    ("Pelando", lambda ctx: pelando.buscar(ctx, "iphone")),
    ("KaBuM", lambda ctx: kabum.buscar(ctx, "rtx 3060")),
    ("Leilões Sodré", lambda ctx: sodre.buscar(ctx, "notebook")),
]


def main():
    ok = True
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        ctx = navegador.new_context(locale="pt-BR", viewport={"width": 1366, "height": 900}, user_agent=UA)
        for nome, teste in TESTES:
            try:
                n = len(teste(ctx))
                print(f"  ✅ {nome:14} funcionou ({n} resultados)")
            except FonteBloqueada as e:
                ok = ok and nome != "OLX (MG)"
                print(f"  ❌ {nome:14} BLOQUEADO: {e}")
            except Exception as e:
                print(f"  ⚠️ {nome:14} erro: {str(e)[:120]}")
        navegador.close()
    if not ok:
        print("\nO OLX bloqueou esta máquina. O vigia ainda funcionaria aqui para as outras fontes.")
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
