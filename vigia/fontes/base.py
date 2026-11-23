from dataclasses import dataclass


@dataclass
class Anuncio:
    fonte: str
    id: str
    titulo: str
    preco: float
    url: str
    local: str = ""
    data: str = ""
    foto: str = ""


class FonteBloqueada(Exception):
    """O site recusou o acesso (bloqueio, captcha, login). O vigia pausa a fonte e avisa."""
