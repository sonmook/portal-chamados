# Desenvolvimento, CI e produção

## Cadastro de equipes — primeira etapa da v1.1.0

Faça backup e execute `python manage.py migrate` antes de iniciar esta revisão.
A migração 0013 cria equipes e vínculos de integrantes e inclui os seis cadastros
iniciais de forma idempotente. Não migra chamados, não atribui técnicos e não concede
permissões adicionais a coordenadores. Não publicar a v1.1.0 antes das próximas etapas.

Administradores gerenciam as equipes em `/equipes/`, pelo menu do portal. A edição
é transacional com a auditoria; conta ativa com `is_staff` é requisito para seleção
e coordenadores precisam integrar a equipe. Se um integrante for desativado ou
rebaixado na gestão de usuários, seu vínculo permanece visível, sinalizado na tela;
é necessário removê-lo explicitamente da seleção para salvar uma nova edição.
Desativar uma equipe preserva seus vínculos, sem excluir registros. O registro de
auditoria preserva IDs de integrantes/coordenadores e status antes/depois; nome e
descrição são registrados como alterados, sem reproduzir o conteúdo.

Edições antigas retornam 409 e exigem reabrir o formulário. O Django Admin permite
somente consulta. Escritas diretas por SQL/ORM não passam pelo fluxo de validação
e auditoria. SQLite continua sem bloqueio de linha: o controle de versão não é
garantia de capacidade sob carga concorrente real de produção.

Esta branch parte da main sem a migração de última interação ainda pendente na
branch `feat/ultima-interacao`. Antes de integrar ambas as entregas, conciliar os
dois ramos de migrações do helpdesk e repetir `makemigrations --check` e os testes;
não resolver conflitos apagando migrações já aplicadas.

## Proteção do login administrativo

O AdminSite configurado por `core.admin_config.PortalAdminConfig` aplica o mesmo
limite do portal aos POSTs de `/admin/login/`: 10 por conta/IP e 50 por IP, em
janelas fixas de 15 minutos, incluindo tentativas bem-sucedidas. Os contadores são
compartilhados entre ambas as rotas e processos usando o mesmo banco. Ao exceder,
a resposta é 429 com `Retry-After` e sem cache. O CSRF é verificado antes da contagem;
GETs não contam. O login mantém o formulário e as permissões padrão do Django Admin.
Não há bloqueio permanente de conta. A troca de IP e a virada de janela limitam a
proteção; complemente com controles de tráfego e alertas na infraestrutura.

Atrás de proxy, configurar `DJANGO_TRUSTED_PROXY_NETWORKS` e garantir que o proxy
substitua `X-Real-IP`; não aceitar cabeçalhos de origem não confiável. Sem isso,
usuários podem compartilhar a cota do IP do proxy. O fluxo OAuth/Allauth continua
com seus próprios controles, fora deste limitador. Não aumente workers SQLite
sem validar concorrência; a limitação não substitui o dimensionamento do banco.

MFA administrativo ainda não está implementado. Para uma próxima entrega, avaliar
TOTP ou WebAuthn com biblioteca mantida, inscrição verificada, códigos de recuperação
e procedimento seguro de perda do dispositivo. A política deve exigir o segundo
fator no acesso ao admin mesmo para sessões iniciadas pelo portal ou pelo Google:
proteger somente `/admin/login/` ou habilitar MFA no Allauth isoladamente não garante
isso. Cobrir sessões já existentes, recuperação e acesso de emergência antes de
exigir MFA em produção. Enquanto isso, avaliar acesso ao admin por rede restrita,
com regras de infraestrutura verificadas; nenhuma regra externa é criada pelo PR.

## Redistribuição de chamados

Redistribuição de chamados não exige migração. Administradores acessam o botão
nos detalhes de um chamado ativo ou os links de pendências na edição do técnico.
Só são aceitos destinos ativos com papel de técnico e um motivo de até 500
caracteres. O motivo é persistido na auditoria: não inclua credenciais ou dados
sensíveis. O registro inclui ator, data e os IDs anterior/novo; sua gravação e a
transferência ocorrem na mesma transação. O campo técnico no Django Admin passa
a ser somente leitura para manter a atribuição administrativa nesse fluxo.

Desativação/rebaixamento pelos formulários do portal/admin exige redistribuir
as pendências primeiro, sem modificar os responsáveis de chamados concluídos.
O fluxo recupera também chamados já atribuídos a contas inativas. Alterações
diretas por SQL/ORM não passam por essa validação. A transferência compara a
atribuição recebida da tela com a persistida e recusa conflito; em caso de 409,
reabra a página e confira o responsável atual. SQLite continua sem bloqueio de
linha e pode rejeitar escritas concorrentes; não foi validada carga concorrente
real de produção. Valide no banco/infraestrutura de destino antes de escalar.

## Instalação e atualização

- Python 3.12, dependências de execução em requirements.txt com todas as versões e hashes.
- Instalar: `python -m pip install --require-hashes -r requirements.txt` e `python -m pip check`.
- Atualizar o lockfile em Python 3.12, num ambiente de ferramentas separado, com pip-tools 7.6.2:
  `pip-compile --generate-hashes --strip-extras --upgrade --no-emit-index-url --no-emit-trusted-host --output-file requirements.txt requirements.in`.
- Revisar o diff, auditar e rodar toda a suíte antes de publicar. Não editar hashes para contornar erros de integridade.
- O lockfile foi instalado e validado em Linux/Python 3.12. Windows/macOS ainda não foram executados nesta etapa.

## GitHub Actions

O workflow `.github/workflows/ci.yml` roda em pushes à main, pull requests, manualmente
e semanalmente (segunda-feira às 12:00 UTC). Usa token somente de leitura e não faz deploy.

Executa instalação com hashes, pip check, checks Django, teste de migrações pendentes,
suíte de testes, perfil de produção e collectstatic com configuração isolada.
O job de dependências consulta pip-audit 2.10.1; falha em vulnerabilidades conhecidas
ou falhas de consulta, sem ignorar advisories. Para exigir aprovação desses checks antes
de merges, o proprietário deve configurar a proteção da branch; o workflow não altera
permissões do repositório. Push direto continua sujeito à política configurada no GitHub.

## Perfil de produção

Selecionar explicitamente `DJANGO_SETTINGS_MODULE=core.settings_production` no processo
WSGI/ASGI e também nas operações de migrate, collectstatic e checks.
O perfil exige valores definidos pelo operador, nunca credenciais versionadas:

| Variável | Finalidade |
| --- | --- |
| DJANGO_SECRET_KEY | Chave nova, aleatória, pelo menos 50 caracteres; gerar com get_random_secret_key e armazenar em gerenciador de segredos. Não reutilizar a chave antiga do repositório. |
| DJANGO_ALLOWED_HOSTS | Hosts separados por vírgula, sem esquema, porta ou wildcard. |
| DJANGO_DB_PATH | Caminho absoluto do banco SQLite persistente e privado. |
| DJANGO_MEDIA_ROOT | Diretório absoluto de uploads privados, sem alias público. |
| DJANGO_STATIC_ROOT | Diretório absoluto público para collectstatic, separado de uploads e banco. |
| DJANGO_CSRF_TRUSTED_ORIGINS | Opcional: origens HTTPS explícitas, separadas por vírgula, quando necessárias. |
| DJANGO_TRUST_PROXY_SSL_HEADER | Opcional: 1 somente com proxy confiável que remova/substitua X-Forwarded-Proto recebido do cliente. |

DEBUG permanece desativado em produção; redirecionamento HTTPS e cookies Secure ficam
ativos. O HSTS usa duração inicial de uma hora e não abrange subdomínios nem preload.
O `check --deploy` mostra W005 e W021 por essa decisão; `python scripts/check_production.py`
mantém essas observações visíveis e falha para qualquer outro diagnóstico. Não habilitar
preload ou abranger subdomínios sem comprovar HTTPS em toda a infraestrutura.

A chave fixa antiga foi removida do código atual, mas permanece no histórico Git:
qualquer implantação que a utilizasse deve trocar a chave e invalidar sessões antigas.
A chave gerada para desenvolvimento fica em arquivo local ignorado com permissão 0600
na criação em sistemas POSIX. Não versionar arquivos .env, bancos, uploads ou chaves.

Esse perfil continua com SQLite. É necessário validar volume, concorrência, backup e
restauração antes de decidir por SQLite em produção ou implementar PostgreSQL. Nenhum
servidor, domínio, certificado ou banco externo foi provisionado por esta alteração.
O backend de e-mail real também precisa ser configurado e testado na implantação.

Use servidor WSGI/ASGI apropriado, proxy HTTPS, processo supervisionado e armazenamento
persistente. Não usar runserver em produção. Configure limites de upload e o endereço
real do cliente no servidor para que o limitador de login não agrupe todos pelo proxy.
Depois de fornecer configuração segura, execute migrate, collectstatic,
check_production.py e um teste funcional pelo domínio HTTPS real.

OAuth real, restauração, concorrência, infraestrutura e entrega de e-mails permanecem
fora da validação local. A separação de configurações não equivale a publicar o sistema.
