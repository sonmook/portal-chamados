# Versionamento do Portal de TI

`VERSION` é a fonte da versão do código. O portal e o login usam esse arquivo, também validado pelo CI. A versão do código em uma branch pode preceder sua publicação oficial.

Usamos `MAJOR.MINOR.PATCH`: mudanças incompatíveis incrementam MAJOR; funcionalidades compatíveis, MINOR; correções, PATCH. Tags usam o prefixo `v`, por exemplo `v1.4.0`.

## Preparar uma versão

1. Trabalhe em branch, sem alterar a main diretamente.
2. Atualize `VERSION`, a entrada do `CHANGELOG.md`, as notas em `docs/releases/vX.Y.Z.md` e a indicação no README.
3. Execute `python scripts/check_release.py` e a validação do projeto. Abra um PR e confirme os três checks antes do merge.

## Registrar as versões pendentes

Depois do merge do fluxo de publicação, abra **Actions → Publicar versão → Run workflow**, sempre na branch **main**.

1. Selecione **v1.3.0** e execute. O fluxo encontra o último commit do histórico principal que ainda contém `VERSION=1.3.0`, valida esse código e publica a tag e a Release históricas. No histórico atual, o commit é **e97932d**, anterior à integração da v1.4.0. A Release histórica não recebe o marcador Latest.
2. Aguarde a conclusão. Execute novamente selecionando **atual**. O fluxo lê `VERSION` na main, valida esse commit e publica a **v1.4.0** como Latest.

Cada execução repete os três jobs do CI (testes, dependências e homologação) com checkout do SHA exato escolhido. A validação da v1.3.0 usa seu próprio código e suas próprias notas, sem marcar o código atual com uma versão antiga. A v1.4.0 pode ser instalada diretamente sobre a v1.2.0: não é necessário instalar a v1.3.0 primeiro.

## Proteções da publicação

- Apenas execuções na main publicam. A versão histórica deve pertencer ao histórico principal e ser anterior à atual.
- A tag anotada usa a identidade oficial `Emerson Franco <132287925+sonmook@users.noreply.github.com>`; o fluxo usa o token do próprio GitHub, sem novo segredo.
- Tags existentes não são movidas e Releases existentes não são reescritas. A tag v1.2.0 permanece intacta.
- Para a versão atual, se a main avançar durante a validação, a ação termina sem publicar: execute-a novamente para validar o novo commit.
- Se a tag foi enviada, mas a criação da Release falhou, é possível repetir para o mesmo commit. Não reutilize uma versão para outro commit.

A resolução pode ser inspecionada sem alterações locais ou remotas com `python scripts/resolve_release.py atual` ou `python scripts/resolve_release.py v1.3.0`. Esses comandos exibem SHA, versão, tag e indicação de Latest; não criam tags.

A versão exibida no portal e no login é carregada ao iniciar o processo. Depois de atualizar o código, reinicie a aplicação; no desenvolvimento, pare o `runserver` com Ctrl+C e inicie-o novamente.

Publicar uma tag não implanta o sistema nem altera dados. A atualização de cada instalação segue as notas da versão, incluindo backup e migrações quando aplicáveis.
