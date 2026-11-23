"""Liga a leitura dos grupos/canais de promoção do Telegram pela conta do usuário.

1) chave da API (my.telegram.org)  2) login na conta (o código quem digita é o usuário)
3) escolha dos grupos/canais. Tudo fica só em dados/ no PC.
"""
import asyncio
import getpass
import sys

from . import config
from .grupos import SESSAO

INSTRUCOES = """
=== Ler seus grupos de promoção do Telegram ===

Passo 1 - crie a chave da API (só uma vez):
  1. Abra https://my.telegram.org no navegador e entre com o seu número.
     (o Telegram manda um código no próprio app; digite lá no site)
  2. Clique em "API development tools".
  3. Preencha "App title" (ex.: Vigia) e "Short name" (ex.: vigia) e clique em "Create application".
  4. Copie o "App api_id" (número) e o "App api_hash" (letras e números).
"""


async def principal():
    from telethon import TelegramClient
    c = config.carregar()
    if c.get("tg_api_id") and c.get("tg_api_hash"):
        print("Chave da API já configurada.")
        api_id, api_hash = c["tg_api_id"], c["tg_api_hash"]
    else:
        print(INSTRUCOES)
        api_id = input("Cole o api_id e tecle Enter: ").strip()
        api_hash = input("Cole o api_hash e tecle Enter: ").strip()
        if not api_id.isdigit() or len(api_hash) < 20:
            sys.exit("api_id deve ser só números e o api_hash tem 32 caracteres. Rode de novo.")

    cliente = TelegramClient(str(SESSAO), int(api_id), api_hash)
    print("\nPasso 2 - entrar na sua conta do Telegram (só para LER os grupos):")
    await cliente.start(
        phone=lambda: input("Seu número com DDI e DDD (ex.: +5534999998888): ").strip(),
        code_callback=lambda: input("Código que o Telegram acabou de te mandar no app: ").strip(),
        password=lambda: getpass.getpass("Senha da verificação em duas etapas (não aparece): "),
    )
    eu = await cliente.get_me()
    print(f"OK, conectado como {eu.first_name}.")
    config.salvar({"tg_api_id": str(api_id), "tg_api_hash": api_hash})

    print("\nPasso 3 - escolha os grupos e canais de promoção:")
    opcoes = []
    async for d in cliente.iter_dialogs():
        if d.is_group or d.is_channel:
            opcoes.append((d.id, d.name or "sem nome"))
    if not opcoes:
        await cliente.disconnect()
        sys.exit("Não achei grupos nem canais na sua conta.")
    atuais = config.carregar().get("tg_grupos") or {}
    for i, (gid, nome) in enumerate(opcoes, 1):
        marca = " (já ligado)" if str(gid) in atuais else ""
        print(f"  {i:3}. {nome}{marca}")
    escolha = input("\nDigite os números separados por vírgula (ex.: 1,4,7): ")
    numeros = {int(x) for x in escolha.replace(" ", "").split(",") if x.isdigit()}
    grupos = {str(opcoes[n - 1][0]): opcoes[n - 1][1] for n in sorted(numeros) if 1 <= n <= len(opcoes)}
    await cliente.disconnect()
    if not grupos:
        sys.exit("Nenhum grupo escolhido; nada mudou.")
    config.salvar({"tg_grupos": grupos})
    print("\nVou ler:")
    for nome in grupos.values():
        print("  •", nome)
    print("\nPronto! O vigia vai reiniciar e começar a ler esses grupos.")


if __name__ == "__main__":
    asyncio.run(principal())
