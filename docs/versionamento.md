# Versionamento do Portal de TI

`VERSION` é a fonte da versão do código. O portal e o login usam esse arquivo, também validado pelo CI. A versão do código em uma branch pode preceder sua publicação oficial.

Usamos `MAJOR.MINOR.PATCH`: mudanças incompatíveis incrementam MAJOR; funcionalidades compatíveis, MINOR; correções, PATCH. Tags usam o prefixo `v`, por exemplo `v1.1.0`.

## Preparar uma versão

1. Trabalhe em branch, sem alterar a main diretamente.
2. Atualize `VERSION`, a entrada do `CHANGELOG.md`, as notas em `docs/releases/vX.Y.Z.md` e a indicação no README.
3. Execute `python scripts/check_release.py` e a validação do projeto. Abra um PR e confirme os três checks antes do merge.

## Publicar após o merge

No GitHub, abra **Actions → Publicar versão → Run workflow**, escolha **main** e execute.

O fluxo repete os três jobs do CI (testes, dependências e homologação). Só então verifica que o commit validado ainda é a main e cria uma tag anotada, com identidade oficial `Emerson Franco <132287925+sonmook@users.noreply.github.com>`, e a Release com as notas versionadas. A ação usa o token do próprio GitHub; não exige um novo segredo.

Branches diferentes da main não publicam. Tags existentes não são movidas. Se a main avançar durante a validação, a ação termina sem criar uma nova tag: execute-a novamente. Se a tag foi enviada, mas a publicação da Release falhou, é possível repetir enquanto o commit da main continuar igual. Não reutilize uma versão para outro commit.

Publicar uma tag não implanta o sistema nem altera dados. A atualização de cada instalação segue as notas da versão, incluindo backup e migrações quando aplicáveis.
