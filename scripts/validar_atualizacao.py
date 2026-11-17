"""Executa a validação comum local/CI sem instalar pacotes ou aplicar migrações."""
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parent.parent
ETAPAS = (
    ('Metadados da versão', ('scripts/check_release.py',)),
    ('Compatibilidade de dependências', ('-m', 'pip', 'check')),
    ('Configuração Django', ('manage.py', 'check', '--fail-level', 'WARNING')),
    ('Consistência das migrações', ('manage.py', 'makemigrations', '--check', '--dry-run')),
    ('Testes de regressão', ('manage.py', 'test', '--verbosity', '1')),
)


def main():
    resultados = []
    codigo = 0
    for nome, argumentos in ETAPAS:
        print(f'\n>>> {nome}', flush=True)
        inicio = perf_counter()
        try:
            codigo = subprocess.run([sys.executable, *argumentos], cwd=ROOT).returncode
        except OSError as erro:
            print(f'Não foi possível executar a etapa: {erro}', file=sys.stderr)
            codigo = 1
        resultados.append((nome, codigo == 0, perf_counter() - inicio))
        if codigo:
            break
    resumo = ['## Validação da atualização', '', '| Etapa | Resultado | Tempo |', '| --- | --- | --- |']
    for nome, passou, segundos in resultados:
        resumo.append(f'| {nome} | {"Aprovado" if passou else "Falhou"} | {segundos:.1f}s |')
    for nome, _ in ETAPAS[len(resultados):]:
        resumo.append(f'| {nome} | Não executado | — |')
    resumo.extend(['', 'Validação aprovada.' if codigo == 0 else 'Validação interrompida na primeira falha.'])
    print('\n' + '\n'.join(resumo), flush=True)
    if destino := os.environ.get('GITHUB_STEP_SUMMARY'):
        with Path(destino).open('a', encoding='utf-8') as arquivo:
            arquivo.write('\n'.join(resumo) + '\n')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
