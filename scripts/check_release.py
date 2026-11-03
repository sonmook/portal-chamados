"""Valida os metadados que serão usados pela publicação da release."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.version import VERSION

notes = ROOT / 'docs' / 'releases' / f'v{VERSION}.md'
if not notes.is_file() or not notes.read_text(encoding='utf-8').startswith(f'# Portal de TI v{VERSION}\n'):
    raise SystemExit(f'Notas de release ausentes ou com versão divergente: {notes.name}')
if f'## v{VERSION}' not in (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8'):
    raise SystemExit('A versão deve estar registrada no CHANGELOG.md.')
if f'**Versão do código: {VERSION}**' not in (ROOT / 'README.md').read_text(encoding='utf-8'):
    raise SystemExit('A indicação da versão no README.md está divergente.')
print(VERSION)
