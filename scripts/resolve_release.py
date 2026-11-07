"""Resolve a versão atual ou versões históricas autorizadas, sem criar ou mover tags."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
HISTORICAS = ('v1.3.0', 'v1.5.0')
SEMVER = re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)')


def git(repository, *args):
    return subprocess.run(['git', *args], cwd=repository, check=True,
                          capture_output=True, text=True).stdout.strip()


def version_at(repository, sha):
    try:
        return git(repository, 'show', f'{sha}:VERSION')
    except subprocess.CalledProcessError:
        return None


def resolve_release(selection='atual', repository=ROOT):
    if selection not in ('atual', *HISTORICAS):
        raise ValueError('Selecione atual, v1.3.0 ou v1.5.0.')
    head = git(repository, 'rev-parse', 'HEAD')
    current = version_at(repository, head)
    if not current or not SEMVER.fullmatch(current):
        raise ValueError('A versão atual em VERSION é inválida.')
    if selection == 'atual':
        return {'sha': head, 'version': current, 'tag': f'v{current}', 'latest': 'true'}
    wanted = selection[1:]
    if tuple(map(int, wanted.split('.'))) >= tuple(map(int, current.split('.'))):
        raise ValueError('A publicação histórica deve ser anterior à versão atual.')
    # O primeiro pai acompanha as integrações da main, sem escolher commits de branches laterais.
    for sha in git(repository, 'rev-list', '--first-parent', head).splitlines():
        if version_at(repository, sha) == wanted:
            return {'sha': sha, 'version': wanted, 'tag': selection, 'latest': 'false'}
    raise ValueError(f'A {selection} não foi encontrada no histórico principal; nenhuma tag será criada.')


if __name__ == '__main__':
    if len(sys.argv) > 2:
        raise SystemExit('Uso: python scripts/resolve_release.py [atual|v1.3.0|v1.5.0]')
    try:
        result = resolve_release(sys.argv[1] if len(sys.argv) == 2 else 'atual')
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
    for key, value in result.items():
        print(f'{key}={value}')
