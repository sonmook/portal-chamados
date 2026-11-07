# Versionamento do Portal de TI

`VERSION` é a fonte da versão do código. O portal e o login usam esse arquivo, também validado pelo CI. A versão do código em uma branch pode preceder sua publicação oficial.

Usamos `MAJOR.MINOR.PATCH`: mudanças incompatíveis incrementam MAJOR; funcionalidades compatíveis, MINOR; correções, PATCH. Tags usam o prefixo `v`, por exemplo `v1.4.0`.

## Preparar uma versão

1. Trabalhe em branch, sem alterar a main diretamente.
2. Atualize `VERSION`, a entrada do `CHANGELOG.md`, as notas em `docs/releases/vX.Y.Z.md` e a indicação no README.
3. Execute `python scripts/check_release.py` e a validação do projeto. Abra um PR e confirme os três checks antes do merge.

## Publicar a versão atual

Após o merge, abra **Actions → Publicar versão → Run workflow**, escolha a branch **main** e a opção **atual**. O fluxo lê `VERSION` e publica a versão do código validado; nesta preparação, **v1.5.0**.

As versões **v1.3.0 e v1.4.0 já foram registradas**. A opção `v1.3.0` permanece disponível apenas para recuperação histórica: resolve o commit e97932d, não recebe Latest e não altera tags ou Releases existentes.

Na homologação, o certificado público é copiado temporariamente para dentro do contexto permitido pelo Docker Bake e montado como secret. A pasta é excluída da imagem e removida ao final, inclusive em falhas.

Cada publicação repete os três jobs do CI (testes, dependências e homologação) com checkout do SHA escolhido, e publica o mesmo commit. A ação não instala a atualização em servidores ou no Windows automaticamente.

## Proteções da publicação

- Apenas execuções na main publicam. A versão histórica deve pertencer ao histórico principal e ser anterior à atual.
- A tag anotada usa a identidade oficial `Emerson Franco <132287925+sonmook@users.noreply.github.com>`; o fluxo usa o token do próprio GitHub, sem novo segredo.
- Tags existentes não são movidas e Releases existentes não são reescritas. A tag v1.2.0 permanece intacta.
- Para a versão atual, se a main avançar durante a validação, a ação termina sem publicar: execute-a novamente para validar o novo commit.
- Se a tag foi enviada, mas a criação da Release falhou, é possível repetir para o mesmo commit. Não reutilize uma versão para outro commit.

A resolução pode ser inspecionada sem alterações locais ou remotas com `python scripts/resolve_release.py atual` ou `python scripts/resolve_release.py v1.3.0`. Esses comandos exibem SHA, versão, tag e indicação de Latest; não criam tags.

A versão exibida no portal e no login é carregada ao iniciar o processo. Depois de atualizar o código, reinicie a aplicação; no desenvolvimento, pare o `runserver` com Ctrl+C e inicie-o novamente.

Publicar uma tag não implanta o sistema nem altera dados. A atualização de cada instalação segue as notas da versão, incluindo backup e migrações quando aplicáveis.
