from pathlib import Path

from django.core.exceptions import ValidationError


MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024


def validar_anexo(arquivo):
    """Limita tamanho e confere assinatura básica; não substitui antivírus."""
    if arquivo.size > MAX_ATTACHMENT_SIZE:
        raise ValidationError("O anexo deve ter no máximo 10 MB.")
    posicao = arquivo.tell()
    try:
        arquivo.seek(0)
        inicio = arquivo.read(16)
    finally:
        arquivo.seek(posicao)
    extensao = Path(arquivo.name).suffix.lower()
    valido = (
        (extensao == '.png' and inicio.startswith(b'\x89PNG\r\n\x1a\n'))
        or (extensao in ('.jpg', '.jpeg') and inicio.startswith(b'\xff\xd8\xff'))
        or (extensao == '.pdf' and inicio.startswith(b'%PDF-'))
    )
    if not valido:
        raise ValidationError("Envie um arquivo PNG, JPEG ou PDF com conteúdo correspondente à extensão.")
