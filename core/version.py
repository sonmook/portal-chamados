"""Versão da aplicação, compartilhada com o processo de release."""
from pathlib import Path
import re

VERSION = (Path(__file__).resolve().parent.parent / 'VERSION').read_text(encoding='utf-8').strip()
if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', VERSION):
    raise ValueError('VERSION deve conter uma versão no formato MAJOR.MINOR.PATCH.')
