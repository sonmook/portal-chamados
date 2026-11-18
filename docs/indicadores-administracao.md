# Administração → Indicadores

Área exclusiva para administradores ativos (`is_superuser`), inclusive no acesso direto por URL. Técnicos, coordenadores e clientes não recebem acesso. O dashboard existente mantém seu escopo atual.

O período padrão é Este mês, do primeiro dia até hoje. Hoje, Últimos 7 dias (incluindo hoje), Todo o histórico e Intervalo personalizado também estão disponíveis. As datas são inclusivas e seguem o fuso configurado no Django. Filtros inválidos exibem erros sem resultados. O filtro de equipe inclui equipes inativas para preservar a consulta histórica.

- Criados no período: chamados cuja data de criação está no intervalo.
- Resoluções no período: ciclos concluídos como Resolvido ou Fechado cuja data de fechamento está no intervalo, mesmo quando criados antes dele.
- Ativos agora: chamados atualmente não finalizados da equipe selecionada, independentemente do período.
- SLA: comparação entre fechamento e vencimento; igualdade conta dentro do prazo. Registros sem qualquer uma dessas datas não entram no percentual.
- Tempo médio: horas corridas entre início do ciclo e fechamento, excluindo datas ausentes ou fechamento anterior ao início do ciclo.

Cada ciclo concluído contribui com uma resolução, independentemente de comentários ou integrantes da equipe. Reabrir não remove o resultado anterior; concluir novamente adiciona outro ciclo. Os dois estados finais são contados juntos, sem somar eventos de auditoria. A atribuição é à equipe e ao autor preservados na conclusão do ciclo. Transferências posteriores não reescrevem esse resultado. Para legados anteriores à v1.13.0, a migração preserva a equipe já registrada no chamado, sem reconstruir transferências antigas. Resolvidos sem data de fechamento aparecem apenas em Todo o histórico, identificados como sem dados.

A tabela por equipe inclui equipes sem resoluções. O detalhamento mostra chamado, número do ciclo, equipe, autor da resolução, fechamento e SLA, com links para a consulta do chamado. A paginação de 25 registros mantém os filtros e ordena por fechamento e identificador decrescentes.

## Relatório de performance

O cabeçalho identifica equipe, período e data de geração no fuso do Django. Os cards distinguem bases diferentes: **Total de chamados** conta criações no período; **SLA violado** e **Dentro do SLA** usam resoluções com fechamento e vencimento conhecidos; **Sem responsável** conta chamados ativos agora sem técnico atribuído, independentemente do período. Os percentuais de SLA não usam o total de criações como denominador. Zero resoluções avaliáveis exibe ausência de dados, sem inventar 0% de cumprimento.

O panorama compara resoluções dentro e fora do prazo. Ativos vencidos agora aparecem separadamente e não entram nesses percentuais nem na lista de resoluções com SLA violado. Igualdade entre fechamento e vencimento cumpre o prazo.

A distribuição usa as categorias atuais do modelo, com quantidade e percentual das criações no período. O ranking de analistas agrupa pelo autor registrado em `fechado_por`, incluindo contas inativas; ausências históricas aparecem como **Não registrado**. Cada resolução conta uma vez e as barras são proporcionais ao maior volume. O top 20 solicitantes usa criações no período e desempata pelo identificador da pessoa. Ambos respeitam a equipe selecionada, sem multiplicar contagens por comentários ou integrantes.

A lista clicável de resoluções com SLA violado tem 25 itens por página e paginação independente (`page_sla`), preservando os filtros e a página do detalhamento dos resolvidos (`page`). O layout segue a identidade do Portal de TI: fundo compartilhado, cabeçalho branco com destaque azul, cards e bordas suaves, barras azuis e tabelas compactas com rolagem horizontal em telas pequenas. Vermelho e verde mantêm o significado dos estados de SLA. Os estilos ficam em `helpdesk/static/helpdesk/css/indicadores.css`, usando as variáveis compartilhadas do portal. O dashboard e suas regras de acesso permanecem com o comportamento existente.

Na v1.13.0, a migração 0028 registra os resultados de chamados já finalizados sem alterar suas datas e sem inventar dados ausentes. Novos resultados são gravados junto da resolução, na mesma transação. Os totais de criações e ativos continuam contando chamados; os totais históricos de resoluções e rankings contam ciclos. Conquistas seguem contando uma única resolução elegível por chamado. [Reabertura](reabertura-chamados.md).
