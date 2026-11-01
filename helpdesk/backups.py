"""Cópia SQLite + uploads privados. Todos os escritores devem estar parados."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verificar_sqlite(path):
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Banco com falha de integridade.')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Banco com vínculos inválidos.')


def arquivos(root):
    resultado = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Links simbólicos não são permitidos no backup.')
        if path.is_file():
            resultado.append(path)
        elif not path.is_dir():
            raise ValueError('Arquivo especial não é permitido no backup.')
    return resultado


def criar_backup(banco, midia, destino):
    banco, midia, destino = [Path(p).absolute() for p in (banco, midia, destino)]
    if banco.is_symlink() or midia.is_symlink():
        raise ValueError('Links simbólicos não são permitidos.')
    if not banco.is_file():
        raise ValueError('Banco SQLite de origem não encontrado.')
    if destino == midia or midia in destino.parents:
        raise ValueError('O backup não pode ficar dentro dos uploads.')
    if destino.exists():
        raise ValueError('O destino já existe; nada foi sobrescrito.')
    lista = arquivos(midia) if midia.exists() else []
    destino.mkdir(mode=0o700, parents=True)
    try:
        with closing(sqlite3.connect(banco.as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(destino / 'db.sqlite3')) as target:
                source.backup(target)
        (destino / 'db.sqlite3').chmod(0o600)
        (destino / 'media').mkdir(mode=0o700)
        for origem in lista:
            target = destino / 'media' / origem.relative_to(midia)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copyfile(origem, target)
            target.chmod(0o600)
        verificar_sqlite(destino / 'db.sqlite3')
        manifest = {'versao':1, 'arquivos':{p.relative_to(destino).as_posix():digest(p) for p in arquivos(destino)}}
        (destino / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        (destino / 'manifest.json').chmod(0o600)
    except Exception:
        shutil.rmtree(destino)
        raise


def verificar_backup(origem):
    origem = Path(origem).absolute()
    if origem.is_symlink():
        raise ValueError('Links simbólicos não são permitidos.')
    lista = arquivos(origem)
    try:
        manifest = json.loads((origem / 'manifest.json').read_text())
    except (OSError, ValueError) as erro:
        raise ValueError('Manifesto ausente ou inválido.') from erro
    if manifest.get('versao') != 1 or not isinstance(manifest.get('arquivos'), dict):
        raise ValueError('Formato de backup inválido.')
    esperado = manifest['arquivos']
    if set(esperado) != {p.relative_to(origem).as_posix() for p in lista if p.name != 'manifest.json' or p.parent != origem}:
        raise ValueError('A lista de arquivos diverge do manifesto.')
    if 'db.sqlite3' not in esperado or any(p != 'db.sqlite3' and not p.startswith('media/') for p in esperado):
        raise ValueError('Estrutura de backup inválida.')
    for nome, hash_esperado in esperado.items():
        if digest(origem / nome) != hash_esperado:
            raise ValueError('Arquivo diverge do hash registrado.')
    verificar_sqlite(origem / 'db.sqlite3')
    return origem


def restaurar_backup(origem, destino):
    origem = verificar_backup(origem)
    destino = Path(destino).absolute()
    if destino.exists():
        raise ValueError('Restaure somente para diretório novo; nada foi sobrescrito.')
    if origem in destino.parents:
        raise ValueError('O destino não pode ficar dentro do backup.')
    shutil.copytree(origem, destino)
    destino.chmod(0o700)
    verificar_backup(destino)
