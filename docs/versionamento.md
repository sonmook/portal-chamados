# Versionamento do Portal de TI

`VERSION` é a fonte da versão do código. O portal e o login usam esse arquivo, também validado pelo CI. A versão do código em uma branch pode preceder sua publicação oficial.

Usamos `MAJOR.MINOR.PATCH`: mudanças incompatíveis incrementam MAJOR; funcionalidades compatíveis, MINOR; correções, PATCH. Tags usam o prefixo `v`, por exemplo `v1.4.0`.

## Preparar uma versão

1. Trabalhe em branch, sem alterar a main diretamente.
2. Atualize `VERSION`, a entrada do `CHANGELOG.md`, as notas em `docs/releases/vX.Y.Z.md` e a indicação no README.
3. Execute `python scripts/check_release.py` e a validação do projeto. Abra um PR e confirme todos os checks antes do merge.

## Publicar a versão atual

Após o merge, abra **Actions → Publicar versão → Run workflow**, escolha a branch **main** e a opção **atual**. O fluxo lê `VERSION` e publica a versão do código validado; nesta preparação, **v1.8.0**.

As versões **v1.3.0 e v1.4.0 já foram registradas**. As opções `v1.3.0` e `v1.5.0` permitem recuperar versões históricas anteriores à atual. São resolvidas pelo histórico principal, não recebem Latest e não alteram tags ou Releases existentes. A v1.3.0 corresponde ao commit e97932d e a v1.5.0 ao commit 421fed7.

Na homologação, o certificado público é copiado temporariamente para dentro do contexto permitido pelo Docker Bake e montado como secret. A pasta é excluída da imagem e removida ao final, inclusive em falhas.

Cada publicação repete os jobs do CI (testes, dependências, homologação e inicialização no Windows) com checkout do SHA escolhido, e publica o mesmo commit. A etapa nativa Windows se aplica às revisões que já contêm o inicializador; versões históricas anteriores preservam suas validações existentes. A ação não instala a atualização em servidores ou no Windows automaticamente.

## Registro histórico das versões v1.5.0 e v1.6.0

As tags v1.5.0 e v1.6.0 já foram registradas. O procedimento abaixo documenta a publicação realizada quando a main estava em 1.6.0; a opção **atual** sempre lê VERSION e nesta preparação publica 1.8.0. Não a use para recriar uma versão anterior.

Procedimento histórico:

1. Abra **Actions → Publicar versão → Run workflow** na branch **main** e selecione **v1.5.0**. A ação valida o commit histórico `421fed7` (notificações), cria a tag oficial e publica as notas da v1.5.0 sem marcar Latest.
2. Aguarde a conclusão dessa execução. Confira a Release em **Releases → Portal de TI v1.5.0**.
3. Execute o mesmo workflow novamente na **main**, agora com **atual**. O fluxo valida o commit atual e publica **v1.6.0** como Latest.
4. Confira as duas Releases e seus commits. A v1.4.0 e as tags anteriores permanecem intactas.

Cada execução valida testes, dependências e homologação no próprio commit da versão. Se alguma etapa falhar, corrija a causa antes de tentar novamente. A versão atual pode ser conferida antes de publicar com `python scripts/resolve_release.py atual`.

## Proteções da publicação

- Apenas execuções na main publicam. A versão histórica deve pertencer ao histórico principal e ser anterior à atual.
- A tag anotada usa a identidade oficial `Emerson Franco <132287925+sonmook@users.noreply.github.com>`; o fluxo usa o token do próprio GitHub, sem novo segredo.
- Tags existentes não são movidas e Releases existentes não são reescritas. A tag v1.2.0 permanece intacta.
- Para a versão atual, se a main avançar durante a validação, a ação termina sem publicar: execute-a novamente para validar o novo commit.
- Se a tag foi enviada, mas a criação da Release falhou, é possível repetir para o mesmo commit. Não reutilize uma versão para outro commit.

A resolução pode ser inspecionada sem alterações locais ou remotas com `python scripts/resolve_release.py atual`, `python scripts/resolve_release.py v1.3.0` ou `python scripts/resolve_release.py v1.5.0`. Esses comandos exibem SHA, versão, tag e indicação de Latest; não criam tags.

A versão exibida no portal e no login é carregada ao iniciar o processo. Depois de atualizar o código, reinicie a aplicação; no desenvolvimento, pare o `runserver` com Ctrl+C e inicie-o novamente.

Publicar uma tag não implanta o sistema nem altera dados. A atualização de cada instalação segue as notas da versão, incluindo backup e migrações quando aplicáveis.
