"""Pede o token do bot numa janelinha, valida no Telegram e salva em dados/config.json."""
import getpass
import re
import sys
import webbrowser

from . import config
from .telegram import Telegram

_RE_TOKEN = re.compile(r"\d{6,}:[A-Za-z0-9_-]{30,}")


def _validar(texto):
    """Aceita o token puro ou a mensagem inteira do BotFather. Devolve (token, info do bot)."""
    m = _RE_TOKEN.search(texto or "")
    if not m:
        raise ValueError("Não achei um token aí. Ele tem o formato 123456789:AAH...")
    token = m.group(0)
    try:
        info = Telegram(token).eu()
    except Exception:
        raise ValueError("O Telegram recusou esse token. Confira se copiou inteiro.")
    config.salvar({"telegram_token": token, "chat_id": None})
    return token, info


def telegram():
    try:
        import tkinter as tk
    except ImportError:
        return _telegram_console()

    raiz = tk.Tk()
    raiz.title("Vigia de Oportunidades")
    raiz.resizable(False, False)
    raiz.attributes("-topmost", True)
    tk.Label(raiz, text="Cole aqui o token que o @BotFather te mandou\n"
                        "(pode colar a mensagem inteira dele):", justify="left"
             ).pack(padx=16, pady=(16, 6), anchor="w")
    campo = tk.Entry(raiz, width=52, show="•")
    campo.pack(padx=16)
    campo.focus_set()
    status = tk.Label(raiz, text="", fg="#b00020", wraplength=380, justify="left")
    status.pack(padx=16, pady=6, anchor="w")
    resultado = {}

    def colar():
        try:
            campo.delete(0, "end")
            campo.insert(0, raiz.clipboard_get().strip())
        except tk.TclError:
            status.config(text="A área de transferência está vazia. Copie o token primeiro.")

    def salvar(_evento=None):
        status.config(text="Conferindo com o Telegram...", fg="#555")
        raiz.update()
        try:
            _, info = _validar(campo.get())
        except ValueError as e:
            status.config(text=str(e), fg="#b00020")
            return
        resultado["bot"] = info["username"]
        raiz.destroy()

    botoes = tk.Frame(raiz)
    botoes.pack(padx=16, pady=(0, 16), anchor="e")
    tk.Button(botoes, text="Colar", width=10, command=colar).pack(side="left", padx=4)
    tk.Button(botoes, text="Salvar", width=10, command=salvar).pack(side="left", padx=4)
    raiz.bind("<Return>", salvar)
    raiz.mainloop()

    if "bot" not in resultado:
        print("Token não salvo.")
        sys.exit(1)
    bot = resultado["bot"]
    print(f"\nOK! Bot @{bot} configurado.")
    print(f"Abrindo https://t.me/{bot}: mande /start para ele.")
    webbrowser.open(f"https://t.me/{bot}")


def _telegram_console():
    print("Cole o token que o @BotFather te deu e tecle Enter:")
    try:
        _, info = _validar(input("> "))
    except ValueError as e:
        print(e)
        sys.exit(1)
    print(f"\nOK! Bot @{info['username']} configurado. Mande /start para ele.")


def mercado_livre():
    from .fontes import ml
    print("""
Mercado Livre pela API oficial:
 1. Entre em https://developers.mercadolivre.com.br/devcenter e crie uma aplicação.
 2. Em 'URI de redirect' coloque: https://www.google.com
 3. Copie o 'Client ID' (App ID) e a 'Client Secret'.
""")
    client_id = input("Client ID: ").strip()
    secret = getpass.getpass("Client Secret (não aparece): ").strip()
    redirect = "https://www.google.com"
    print(f"\n 4. Abra no navegador, autorize e copie o endereço para onde ele te mandar:\n"
          f"https://auth.mercadolivre.com.br/authorization?response_type=code&client_id={client_id}"
          f"&redirect_uri={redirect}\n")
    volta = input("Cole o endereço (https://www.google.com/?code=...): ").strip()
    codigo = volta.split("code=")[-1].split("&")[0]
    try:
        r = ml.trocar_codigo(client_id, secret, codigo, redirect)
    except Exception as e:
        print(f"Não deu certo: {e}")
        sys.exit(1)
    config.salvar({"ml_client_id": client_id, "ml_client_secret": secret,
                   "ml_refresh_token": r["refresh_token"]})
    try:
        achados = ml.buscar("notebook thinkpad")
        print(f"\nOK! Teste de busca no ML trouxe {len(achados)} anúncios em MG.")
    except Exception as e:
        print(f"\nCredenciais salvas, mas o teste de busca falhou: {e}")
        print("O ML pode estar restringindo a busca pela API; o vigia segue só com o OLX.")


if __name__ == "__main__":
    mercado_livre() if "ml" in sys.argv[1:] else telegram()
