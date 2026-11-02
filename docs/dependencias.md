# Auditoria de dependências — 01/11/2026

Ferramenta: pip-audit 2.10.1, serviço PyPI. Escopo: dependências Python de execução,
incluindo transitivas. A consulta inicial encontrou 25 registros em Django 6.0.4,
com duplicações na resposta do serviço: 13 IDs distintos.

Atualizações aplicadas: Django 6.0.4 → 6.0.9; sqlparse 0.6.0 → 0.6.1.
O lockfile final contém 14 dependências de execução, fixadas com hashes.
A consulta do lockfile final não reportou vulnerabilidades conhecidas.

IDs encontrados antes da atualização:

- PYSEC-2026-197
- PYSEC-2026-198
- PYSEC-2026-199
- PYSEC-2026-200
- PYSEC-2026-201
- PYSEC-2026-2090
- PYSEC-2026-2091
- PYSEC-2026-2092
- PYSEC-2026-3717
- PYSEC-2026-4035
- PYSEC-2026-50
- PYSEC-2026-54
- PYSEC-2026-55

Para repetir (em ambiente de ferramentas com pip-audit instalado):

```bash
python -m pip_audit --require-hashes -r requirements.txt
```

Nenhum advisory foi ignorado e nenhuma verificação TLS/hash foi desativada.
Os 67 testes, instalação em venv vazio, checks e coleta de estáticos foram
validados em Linux/Python 3.12. A consulta reflete os dados disponíveis nessa data;
não é garantia de ausência de vulnerabilidades desconhecidas. O CI repete a
consulta semanalmente e em alterações.

Não inclui bibliotecas do navegador/CDNs, imagens de sistema, infraestrutura,
ferramentas de desenvolvimento ou testes de exploração das falhas reportadas.
A confirmação de execução do workflow no GitHub é separada da validação local.


## Complemento de homologação — 01/11/2026

Adicionados Gunicorn 25.3.0 e packaging 26.3 para o servidor WSGI. A auditoria
PyPI do lockfile com 16 dependências não reportou vulnerabilidades conhecidas.
A imagem Docker foi construída com verificação de hashes/TLS. Este resultado não
é uma varredura das imagens base Python/Caddy nem dos pacotes do sistema operacional.
