# Versionamento e Releases da Nexaltri

`VERSION` é a fonte da versão do produto, exibida no portal e no login. Usamos `MAJOR.MINOR.PATCH` e tags com prefixo `v`. Uma branch pode conter código ainda não publicado; o [GitHub Releases](https://github.com/sonmook/portal-chamados/releases) é o registro das publicações oficiais.

## Preparar uma versão

1. Trabalhe em branch e abra um PR. Atualize `VERSION`, `CHANGELOG.md`, `docs/releases/vX.Y.Z.md` e a indicação no README.
2. Execute `python scripts/validar_atualizacao.py` com o Python da venv e confirme os checks do PR antes do merge.
3. Quando houver mudança visível, gere e revise capturas de demonstração. Guarde-as em uma nova pasta `docs/imagens/vX.Y.Z/` e acrescente a etapa à [evolução visual](evolucao-visual.md). Preserve as imagens anteriores.

Uma atualização apenas desta documentação não incrementa a versão do produto. A documentação publicada em uma Release corresponde ao commit da tag; melhorias posteriores do README continuam acessíveis na main e no histórico.

## Publicação automática após o merge

O workflow **Publicar versão** roda na main quando mudam `VERSION`, notas de Release ou os arquivos do próprio publicador. A atualização deste publicador também inicia a recuperação das versões ainda sem Release. Não publica a partir de PRs ou branches de trabalho.

O planejamento consulta as Releases existentes e as notas versionadas. Para cada versão ausente, encontra o último commit correspondente no histórico de primeiro pai da main. Publicações existentes são ignoradas. Se houver uma tag sem Release, usa o commit daquela tag, desde que a versão e a origem sejam compatíveis; nunca a move.

Cada commit planejado passa pelos jobs de testes, dependências, homologação, Windows e visual. Os jobs que ainda não existiam no produto histórico são ignorados quando não se aplicam. Só depois da validação completa o fluxo cria as tags anotadas e publica as notas do próprio commit. Versões antigas recebem `Latest=false`; a versão atual só recebe Latest quando o SHA validado é o HEAD exato da main.

Em 18/11/2026, a consulta anterior a esta atualização encontrou Releases de **v1.1.0 a v1.9.0**. O primeiro planejamento recupera **v1.10.0, v1.10.1, v1.11.0, v1.12.0, v1.13.0 e v1.14.0**, além de publicar a **v1.15.0** atual. Esta lista é um registro da consulta; confira o estado vigente na página de Releases e nas execuções do workflow.

## Executar ou recuperar manualmente

Abra **Actions → Publicar versão → Run workflow**, selecione **main** e informe:

| Entrada | Resultado |
| --- | --- |
| `pendentes` | Publica todas as versões com notas e histórico válidos ainda sem Release. É o padrão. |
| `atual` | Publica somente a versão indicada por VERSION, se estiver ausente. |
| `v1.10.0` ou outra versão semântica | Recupera a versão histórica solicitada, se estiver ausente e for anterior à atual. |

Se tudo já estiver publicado, o planejamento fica vazio e nada é alterado. Se uma validação falhar, corrija a causa antes de repetir. Se a main avançar durante a validação da versão atual, o fluxo encerra essa publicação; execute novamente para validar o novo commit. Rascunhos preexistentes exigem revisão, evitando sobrescrita acidental.

Para inspecionar sem publicar:

```bash
python scripts/resolve_release.py atual
python scripts/resolve_release.py v1.10.0
# releases.json deve conter a lista obtida da API de Releases do repositório.
python scripts/plan_releases.py releases.json pendentes
```

O planejamento não cria tags, commits ou Releases. O arquivo da API é somente entrada temporária; não precisa ser versionado.

## Proteções e implantação

- Notas, VERSION e SHA precisam corresponder. A versão histórica precisa existir no histórico principal, não apenas em uma branch lateral.
- Publicações são serializadas; tags existentes não são movidas e Releases existentes não são reescritas. Notas antigas mantêm o nome Portal de TI; a Nexaltri usa o nome novo.
- A tag anotada usa `Emerson Franco <132287925+sonmook@users.noreply.github.com>` e o token nativo do GitHub, sem novo segredo.
- O certificado público de build da homologação é montado como secret, excluído da imagem e removido ao final.
- Publicar uma Release não instala a atualização no Windows ou em servidores. Siga as notas da versão para backup, migrações, estáticos e reinício.

Após atualizar uma instalação, reinicie os processos: a versão exibida é carregada na inicialização. A [galeria histórica](evolucao-visual.md), as notas e o CHANGELOG complementam o registro oficial das Releases.
