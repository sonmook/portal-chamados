# Estados de espera do atendimento

A v1.12.0 permite indicar de quem depende a próxima ação. Os estados de espera continuam sendo chamados ativos, com responsável e prazo.

## Alterar situação

O técnico responsável, ativo e integrante da equipe, encontra **Alterar situação** nos detalhes do chamado. Pode selecionar Aberto, Em Andamento, Aguardando solicitante ou Aguardando fornecedor. Para aguardar, é obrigatório registrar um motivo de até 500 caracteres.

O motivo aparece para quem já tem acesso ao chamado. Ele não é uma nota interna; não inclua senhas ou informações que não devam ser compartilhadas com esses participantes. O administrador ou coordenador que não é responsável deve usar o fluxo de distribuição existente antes de atuar como responsável.

Ao salvar, o portal registra situação anterior/nova, motivo, autor e instante. A faixa de espera mostra desde quando o chamado aguarda e a próxima ação. O solicitante recebe aviso de situação atualizada; o próprio autor não recebe seu aviso. A notificação não armazena uma cópia do motivo.

O formulário inclui versões da situação e da atribuição. Uma tela anterior a uma alteração devolve **HTTP 409** com orientação para reabrir a página, sem mudar a situação atual. Integrações que usam a rota de status devem enviar `versao_status` e `versao_atribuicao`, obtidos da tela atual. POST sem os campos ou com motivo inválido devolve HTTP 400 no formulário. Selecionar novamente a situação atual, com versões válidas, não gera evento nem aviso.

## Retomar atendimento

| Situação | Ação | Resultado |
| --- | --- | --- |
| Aguardando solicitante | Solicitante envia resposta válida | Em Andamento, com registro da retomada no histórico |
| Aguardando solicitante | Técnico envia resposta | Permanece aguardando solicitante |
| Aguardando fornecedor | Solicitante ou técnico responde | Permanece aguardando fornecedor |
| Qualquer espera | Responsável seleciona Em Andamento | Retoma atendimento e limpa os metadados da espera atual |
| Qualquer espera | Responsável registra uma solução válida | Resolvido, com a solução e o evento de conclusão existentes |

A retomada por mensagem do solicitante usa o aviso de resposta já existente; não cria um segundo aviso de situação para o mesmo retorno. Mensagem inválida não retoma o atendimento. Falha na mensagem ou na transação reverte também a transição.

Transferir ou devolver à fila preserva a situação e o histórico: a equipe de destino continua vendo a pendência. Chamados aguardando permanecem pendências para remoção de integrante, desativação de técnico ou equipe. Resolvido e Fechado exigem o fluxo explícito de [reabertura](reabertura-chamados.md), disponível desde a v1.13.0.

## SLA e indicadores

**O SLA continua contando durante a espera.** Aguarde e retome sem alterar o vencimento, a prioridade, a data de abertura ou resultados históricos. Não há pausa de relógio nesta entrega. Os avisos de proximidade/vencimento continuam, inclusive para chamados aguardando.

Os dois estados aparecem no filtro da fila, combinam com Minha fila, categoria, equipe e prazo, e contam no resumo operacional. O dashboard informa a quantidade em espera no recorte de abertura selecionado. Indicadores administrativos os incluem nos ativos atuais, não nas resoluções.

A mudança de situação não é uma mensagem: não atualiza a última interação da conversa. A resposta do solicitante atualiza a última interação pelo fluxo normal de comentários.

## Histórico e privacidade

Abra **Histórico de situações** no chamado. A consulta mostra 20 eventos por página, com data, autor, origem/destino e motivo; não oferece edição ou exclusão. Solicitantes acessam os próprios chamados; técnicos seguem o acesso às equipes e às próprias solicitações. Nenhum evento retroativo é inventado para chamados antigos.

O Django Admin permite consulta do histórico somente a administradores. Campos da situação atual são somente leitura nesse painel para preservar o fluxo e impedir que uma tela antiga do admin reverta uma alteração do atendimento. A auditoria administrativa registra quais situações mudaram e que houve um motivo, sem copiar seu texto.

## Atualização

1. Pare portal, alertas e demais escritores.
2. Faça backup de banco e uploads conforme o procedimento operacional.
3. Atualize o código aprovado e execute `python manage.py migrate` para aplicar **0027_estados_espera**.
4. Execute `python scripts/validar_atualizacao.py`, colete estáticos em produção e reinicie os processos.

No Windows, use o Python da venv nos comandos e depois `iniciar-portal.cmd`. Não abra o novo código contra um banco ainda sem a migração.

A migração adiciona campos e tabela, amplia o tamanho da situação e permite o novo tipo de aviso. Preserva situações, prazos, responsáveis, comentários, avisos e leituras existentes; os novos metadados começam vazios e a versão em zero. O backup inclui o banco completo e preserva os novos registros; a homologação verifica a restauração em diretório separado.

Sem nova dependência. Para voltar a uma versão anterior após usar os novos estados, prefira o procedimento de recuperação com um backup compatível; o código antigo não conhece as novas situações.
