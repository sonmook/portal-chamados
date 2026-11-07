# Desenvolvimento, CI e produção

## Encaminhamento automático por categoria

Faça backup e aplique `python manage.py migrate` antes de iniciar esta revisão.
A migração 0016 acrescenta regras únicas por categoria: Rede → Infraestrutura e
Redes; Acessos → Identidades e Acessos; Hardware → Suporte Especializado — N2;
Software → Sistemas e Aplicações; Outros → a triagem identificada pelo cadastro.
Não altera chamados existentes, usuários, equipes ou seus vínculos. Se um destino
padrão foi renomeado, cria a regra desativada na triagem, sem adivinhar um destino
nem recriar equipes; revise essas regras antes de ativá-las. Equipes inativas não
são reativadas automaticamente.

Administradores acessam **Gerenciar Equipes → Encaminhamento por categoria**.
Podem mudar o destino ativo e ativar/desativar cada regra. Coordenadores e técnicos
não têm essa permissão. O Django Admin oferece apenas consulta das regras, para
manter a configuração no fluxo auditado. Edições antigas retornam 409 e devem ser
reabertas. A categoria de uma regra existente é fixa; não há exclusão pelo portal,
mas categorias sem regra podem ser cadastradas novamente.

Na criação de chamados pelo portal e pelo Django Admin, o servidor verifica a
regra e o destino. Regra ausente/inativa, equipe inativa ou sem técnico ativo leva
à triagem. A triagem continua recebendo mesmo sem integrantes, para preservar a
fila inicial. Disponibilidade significa conta ativa, is_staff e vínculo de equipe;
não é uma verificação de presença online ou capacidade. Uma alteração de regra
detectada durante o processamento também leva à triagem, sem tentar um destino
não validado. A decisão fica na auditoria com categoria, regra/versão, equipe e
motivo de uso da triagem. Não atribui técnico, não modifica as regras de SLA e não
reclassifica chamados já abertos ou transferidos manualmente.

A criação e a auditoria são transacionais. Integrações devem usar
`helpdesk.encaminhamento.criar_chamado_encaminhado` com um objeto novo preparado;
`Chamado.save()`, SQL e bulk operations diretas não aplicam as regras. O serviço
recusa objetos já persistidos. A avaliação ocorre na abertura: alterações posteriores
de equipe, integrantes ou contas não movem chamados antigos automaticamente.
SQLite segue sem validação de carga concorrente real de produção.

## Atendimento por equipes — segunda etapa da v1.1.0

Antes de atualizar, faça backup do banco/uploads e interrompa todos os escritores, incluindo o serviço `alertas_sla` (ou o comando contínuo no segundo terminal). Reinicie-o depois da migração, junto da aplicação. Veja [Alertas de SLA](alertas-sla.md).
Execute `python manage.py migrate` antes de iniciar a versão nova. A migração 0015
acrescenta a equipe obrigatória e a versão de atribuição dos chamados. Ela aponta os
registros existentes para Central de Serviços — N1, preservando status, datas,
responsáveis, comentários e auditoria. Técnicos ativos já responsáveis ou autores
ativos de encerramentos passam a integrar a triagem, sem receber coordenação; vínculos
anteriores são preservados. A triagem é marcada por identificador próprio, permitindo
renomear a equipe sem quebrar a entrada de novos chamados. Se o nome original não
existir, a migração cria a equipe inicial; se estiver inativa, reativa-a. Valide
uma cópia representativa antes de atualizar bases grandes.

Após migrar, administradores revisam integrantes/coordenadores em `/equipes/`.
Não atribuímos automaticamente todo técnico a todas as equipes. Novos técnicos
precisam de vínculo explícito para atender; solicitantes mantêm seus próprios
chamados. A remoção de responsáveis com chamados ativos e a desativação de equipes
com pendências são bloqueadas. A equipe de triagem não pode ser desativada.

Coordenadores ativos distribuem somente chamados das equipes ativas que coordenam;
administradores podem distribuir qualquer chamado ativo, inclusive recuperar um
registro que tenha sido mantido em equipe inativa fora do fluxo normal. O responsável
escolhido precisa ser integrante ativo do destino, ou o chamado pode ficar na fila.
Mudanças de equipe e técnico são transacionais com motivo e auditoria. A versão de
atribuição e as comparações anteriores impedem que uma tela antiga sobrescreva outra
atribuição, inclusive após ida e volta entre equipes. Transferências não reiniciam
SLA nem mudam o status, e chamados concluídos não são transferidos.

Fila, indicadores, detalhes, comentários e anexos usam o mesmo escopo: administrador
vê todos; técnico vê suas equipes ativas e seus próprios chamados como solicitante;
cliente vê apenas seus próprios chamados. Atribuição direta por SQL sem vínculo não
concede acesso. A remoção do vínculo ou desativação da equipe revoga o acesso técnico,
mas preserva os dados para administradores e solicitantes. O ranking não inclui
pessoas de equipes alheias sem chamados visíveis; filtros não ampliam o escopo.

O Django Admin aplica o escopo aos chamados/comentários e reserva a edição de
chamados aos superusuários; equipe e técnico são somente leitura. Alterações por
SQL, bulk operations e integrações que evitem os serviços não passam por estas
regras e são responsabilidade do operador. SQLite permanece sem bloqueio de linha;
a validação funcional não constitui teste de carga concorrente de produção.

Esta entrega não publica a tag v1.1.0. Os indicadores agrupados de comparação entre
equipes e a revisão final da release ficam para a próxima etapa.

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

Com a migração 0015 aplicada, administradores e coordenadores da origem acessam
o botão nos detalhes de um chamado ativo; administradores também têm os links
de pendências na edição do técnico. Selecione uma equipe ativa e carregue seus
integrantes, depois escolha um técnico ativo do destino ou deixe na fila. O motivo
obrigatório tem até 500 caracteres e é persistido na auditoria: não inclua credenciais
ou dados sensíveis. O registro inclui ator, data e os IDs anterior/novo; sua gravação e a
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

Antes de aplicar a migração 0012, faça backup e execute `python manage.py migrate`
na janela de atualização. Ela acrescenta `ultima_interacao_em` e preenche todos os
chamados com a maior data registrada de abertura, comentário ou encerramento.
O tempo da migração depende do volume de chamados/comentários: valide uma cópia
representativa antes de atualizar uma base grande. Não usa `data_atualizacao`
para inferir uma mensagem e não reconstrói eventos de auditoria.

Novas mensagens gravadas pelo modelo `Comentario.save()` atualizam a interação
na mesma transação, sem recuar a data quando uma gravação mais antiga é processada
depois. A solução do portal é registrada como comentário e segue a mesma regra.
Bulk inserts e SQL/ORM direto que evitem `save()` não atualizam esse campo;
integrações devem manter esse contrato explicitamente. A ordenação por inatividade
mostra apenas chamados ativos e não constitui um indicador de resposta pendente
da equipe ou do cliente. O SLA e os cálculos do dashboard não foram alterados.

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
