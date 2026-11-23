"""Ponto de entrada.

python -m vigia            -> fica rodando (PC): bot respondendo na hora + rodada a cada 10 min
python -m vigia --uma-vez  -> nuvem (GitHub Actions): lê comandos, faz uma rodada, lê de novo e sai
"""
import logging
import logging.handlers
import sys
import threading

from . import config
from .bot import Bot
from .monitor import Monitor
from .telegram import Telegram


def _uma_instancia():
    """Impede duas cópias rodando ao mesmo tempo (ex.: início automático + clique manual)."""
    f = open(config.DADOS / "vigia.lock", "w")
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("O vigia já está rodando.")
        sys.exit(0)
    return f


def main():
    trava = _uma_instancia()
    handlers = [logging.handlers.RotatingFileHandler(config.LOG, maxBytes=2_000_000, backupCount=3,
                                                     encoding="utf-8")]
    if sys.stderr:  # com pythonw (sem janela) não há console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=handlers)
    cfg = config.carregar()
    if not cfg.get("telegram_token"):
        print("Falta o token do bot. Rode configurar_token.bat (ou defina TELEGRAM_TOKEN).")
        sys.exit(1)

    tg = Telegram(cfg["telegram_token"])
    bot = Bot(tg, None)
    monitor = Monitor(bot.avisar)
    bot.monitor = monitor

    if "--uma-vez" in sys.argv:
        bot.ler_pendentes()
        monitor.rodada_unica()
        bot.ler_pendentes()  # comandos que chegaram durante a rodada
        trava.close()
        return

    t = threading.Thread(target=monitor.executar, name="monitor", daemon=True)
    t.start()
    logging.info("vigia iniciado como @%s", tg.eu().get("username"))
    try:
        bot.executar(monitor.parar)
    except KeyboardInterrupt:
        pass
    finally:
        monitor.parar.set()
        monitor.acordar.set()
        t.join(timeout=30)
        trava.close()


if __name__ == "__main__":
    main()
