# Validação das atualizações

Cada correção deve incluir um teste que reproduza o problema e confirme permissões e dados preservados. A validação comum pode ser executada localmente e no GitHub Actions.

## Executar localmente

Com as dependências do lockfile instaladas, use o Python da venv:

```powershell
.\.venv\Scripts\python.exe scripts\validar_atualizacao.py
```

Linux:

```bash
.venv/bin/python scripts/validar_atualizacao.py
```

O comando usa a raiz do projeto mesmo quando chamado por caminho absoluto de outra pasta. Executa, em ordem:

1. Consistência de VERSION, README, CHANGELOG e notas da versão.
2. Compatibilidade das dependências instaladas (`pip check`).
3. Checks Django, falhando também em warnings.
4. Verificação de modelos sem migração (`makemigrations --check --dry-run`).
5. Suíte completa de testes Django em banco de testes.

Não instala pacotes, aplica migrações de atualização, publica código ou altera tags. Exibe a etapa com falha, marca as seguintes como não executadas e retorna código diferente de zero. Sem falhas, retorna zero. A saída dos comandos permanece disponível para diagnóstico.

## Validação no GitHub

O workflow Validação executa automaticamente em pull requests, atualizações na main e no agendamento semanal já existente. O job `tests` usa o comando único e registra uma tabela no resumo da execução. As demais etapas validam produção e estáticos; os jobs separados conferem vulnerabilidades das dependências, Docker/HTTPS/restauração e inicialização Windows.

Falhas impedem o sucesso do workflow. O merge exige conferir todos os checks; impedir tecnicamente o merge com checks vermelhos depende das regras configuradas no repositório. Este fluxo não altera essas regras.

Nas publicações de commits históricos, o workflow mantém os comandos anteriores se `validar_atualizacao.py` não existir naquela revisão. Assim, a validação de versões antigas não depende de um arquivo futuro.

## Cobertura e acompanhamento

A v1.10.1 acrescenta regressões de busca por ID/#ID, acesso por solicitante/equipe, combinação de filtros, categoria visível, limites inclusivos e exclusivos de datas, virada do dia entre UTC/São Paulo e erros de resolução sem efeitos colaterais.

A automação executa as verificações definidas. Alterar código para corrigir uma falha requer uma nova intervenção e commit; o workflow não faz mudanças sozinho. Antes de integrar uma atualização, confira o SHA validado e o resultado de todos os jobs. Mudanças em SLA, autenticação ou banco também precisam de cenários específicos desses módulos.

Testes locais não comprovam entrega real de e-mail, Google OAuth, volume de produção ou disponibilidade externa. Essas verificações pertencem à homologação da instalação e aos testes operacionais correspondentes.
