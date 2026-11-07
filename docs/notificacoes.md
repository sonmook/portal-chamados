# Notificações

O sino no cabeçalho abre **Notificações**. Ele mostra a quantidade de avisos pessoais não lidos; acima de 99, o indicador visual exibe **99+**, e o nome acessível mantém a quantidade completa. O sino também fica disponível no cabeçalho móvel, sem abrir o menu.

## Quando um aviso é enviado

| Evento | Destinatários envolvidos |
| --- | --- |
| Atribuição ou devolução à fila | Solicitante, responsável atual e anterior, quando ainda têm acesso. Sem responsável, coordenadores ativos da equipe são incluídos. |
| Nova resposta | Solicitante e responsável atual. Sem responsável, coordenadores ativos da equipe. |
| Transferência de equipe | Participantes acima, considerando o destino. O responsável anterior só recebe se ainda tiver acesso. |
| Resolução | Solicitante e responsável atual. |
| SLA próximo (até 1h) ou vencido | Responsável ativo e integrante da equipe; sem responsável, coordenadores ativos da equipe. |
| Chamado sem responsável | Coordenadores ativos da equipe, enquanto o chamado estiver ativo. |

Nos avisos de ações, a pessoa que realizou a ação é excluída. Contas inativas nunca recebem avisos. Alertas automáticos de SLA não têm autor e podem avisar quem abriu o próprio chamado, se essa pessoa for o responsável ou coordenador destinatário. Outros técnicos e administradores não envolvidos não recebem cópias gerais. Uma solução gera somente o aviso de resolução, sem aviso de resposta duplicado. Novos chamados sem responsável podem gerar aviso aos coordenadores na próxima verificação periódica.

Os avisos de atribuição, resposta, transferência e resolução são gerados somente por ações bem-sucedidas pelos fluxos do portal. Edições diretas no ORM/Admin, GETs, formulários inválidos e conflitos de atribuição não geram esses quatro avisos. A migração não cria avisos antigos. O processo de SLA analisa os chamados ativos existentes, inclusive os já vencidos, na primeira execução; não reconstitui avisos de chamados finalizados. [Execução e deduplicação](alertas-sla.md).

## Ler e acompanhar

- **Todas / Não lidas:** alterna a lista, com 20 avisos por página, dos mais recentes para os mais antigos.
- **Clique no aviso:** marca como lido e abre o chamado correspondente.
- **Marcar como lida:** registra a leitura sem abrir o chamado.
- **Marcar todas como lidas:** afeta somente avisos atualmente acessíveis da própria conta.

Abrir a central ou abrir o chamado por outro caminho não marca os avisos. Repetir uma marcação preserva a primeira data de leitura. Não há exclusão ou envio por e-mail nesta etapa. Lista e contador são atualizados ao navegar/recarregar, sem polling ou serviço externo.

## Acesso e integridade

Cada consulta combina o destinatário autenticado com as permissões atuais do chamado. Se um técnico perde vínculo, papel ou acesso após uma transferência, esses avisos deixam de aparecer, inclusive no contador, e não podem ser marcados nem abertos pelo ID. O solicitante mantém acesso aos próprios chamados conforme as regras do portal.

As notificações não guardam cópias de comentários, soluções ou títulos: o título é carregado somente de chamados acessíveis. A identidade do destinatário nunca é escolhida pelo navegador. Abrir e marcar leitura exigem POST com CSRF; GET não altera dados. Os dados também são somente consultáveis no Django Admin por administradores.

Os avisos integram a transação da ação do chamado. Falhas revertem a ação e seus avisos juntos. Uma chave de evento e destinatário impede duplicação do mesmo evento persistido; duas respostas realmente gravadas são eventos diferentes.

## Atualização

Faça backup, atualize o código, execute `python manage.py migrate` para aplicar a **0024**, colete estáticos em produção e reinicie. As notificações e datas de leitura ficam no banco SQLite e são incluídas no backup/restauração existente. Não há nova dependência ou credencial externa.

![Central com avisos fictícios](imagens/notificacoes.png)

![Notificações no celular](imagens/notificacoes-mobile.png)
