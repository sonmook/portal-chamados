"""Planeja Releases ausentes usando notas e commits da main; não altera o GitHub."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.resolve_release import SEMVER, git, resolve_release, version_at


def plan_releases(releases, selection='pendentes', repository=ROOT):
    current = version_at(repository, git(repository, 'rev-parse', 'HEAD'))
    if not current or not SEMVER.fullmatch(current):
        raise ValueError('VERSION atual inválido.')
    published = {r['tag_name'] for r in releases if not r.get('draft', False)}
    drafts = {r['tag_name'] for r in releases if r.get('draft', False)}
    notes = Path(repository) / 'docs' / 'releases'
    if selection == 'pendentes':
        versions = [p.stem[1:] for p in notes.glob('v*.md')
                    if SEMVER.fullmatch(p.stem[1:])]
        versions = [v for v in versions if tuple(map(int, v.split('.'))) <= tuple(map(int, current.split('.')))]
    elif selection == 'atual':
        versions = [current]
    else:
        # Valida entradas antes de compor caminhos ou argumentos do git.
        if not selection.startswith('v') or not SEMVER.fullmatch(selection[1:]):
            raise ValueError('Selecione atual, pendentes ou vMAJOR.MINOR.PATCH.')
        versions = [selection[1:]]
    plan = []
    first_parent = set(git(repository, 'rev-list', '--first-parent', 'HEAD').splitlines())
    for version in sorted(set(versions), key=lambda v: tuple(map(int, v.split('.')))):
        tag = 'v'+version
        if tag in published:
            continue
        if tag in drafts:
            raise ValueError(f'{tag} já possui rascunho; revise-o antes de publicar.')
        resolved = resolve_release('atual' if version == current else tag, repository)
        # Uma tag sem Release pode ser recuperada, mas nunca movida para outro commit.
        try:
            tagged = git(repository, 'rev-parse', '--verify', f'refs/tags/{tag}^{{commit}}')
        except subprocess.CalledProcessError:
            tagged = None
        if tagged:
            if tagged not in first_parent or version_at(repository, tagged) != version:
                raise ValueError(f'{tag} não corresponde à versão no histórico principal.')
            resolved['sha'] = tagged
        text = git(repository, 'show', f"{resolved['sha']}:docs/releases/{tag}.md")
        if not text.startswith((f'# Portal de TI {tag}\n', f'# Nexaltri {tag}\n')):
            raise ValueError(f'Notas de {tag} ausentes ou divergentes no commit selecionado.')
        # Latest só cabe à versão atual e ao HEAD exato que será validado.
        resolved['latest'] = 'true' if version == current and resolved['sha'] == git(repository, 'rev-parse', 'HEAD') else 'false'
        plan.append(resolved)
    return plan


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3):
        raise SystemExit('Uso: python scripts/plan_releases.py releases.json [pendentes|atual|vMAJOR.MINOR.PATCH]')
    try:
        result = plan_releases(json.loads(Path(sys.argv[1]).read_text()), sys.argv[2] if len(sys.argv) == 3 else 'pendentes')
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
    print('matrix='+json.dumps({'include': result}, separators=(',', ':')))
    print('has_releases='+str(bool(result)).lower())
