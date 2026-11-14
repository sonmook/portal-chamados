# Administração → Indicadores

Área exclusiva para administradores ativos (`is_superuser`), inclusive no acesso direto por URL. Técnicos, coordenadores e clientes não recebem acesso. O dashboard existente mantém seu escopo atual.

O período padrão é Este mês, do primeiro dia até hoje. Hoje, Últimos 7 dias (incluindo hoje), Todo o histórico e Intervalo personalizado também estão disponíveis. As datas são inclusivas e seguem o fuso configurado no Django. Filtros inválidos exibem erros sem resultados. O filtro de equipe inclui equipes inativas para preservar a consulta histórica.

- Criados no período: chamados cuja data de criação está no intervalo.
- Resolvidos no período: chamados em estado Resolvido ou Fechado cuja data de fechamento está no intervalo, mesmo quando criados antes dele.
- Ativos agora: chamados atualmente não finalizados da equipe selecionada, independentemente do período.
- SLA: comparação entre fechamento e vencimento; igualdade conta dentro do prazo. Registros sem qualquer uma dessas datas não entram no percentual.
- Tempo médio: horas corridas entre criação e fechamento, excluindo datas ausentes ou fechamento anterior à criação.

Cada chamado contribui com uma resolução, independentemente de comentários, integrantes da equipe ou responsável. Os dois estados finais são contados juntos, sem somar eventos de auditoria. A atribuição é à equipe registrada no chamado; não há reconstrução de equipes anteriores a transferências. Resolvidos sem data de fechamento aparecem apenas em Todo o histórico, identificados como sem dados.

A tabela por equipe inclui equipes sem resoluções. O detalhamento mostra chamado, equipe, autor da resolução, fechamento e SLA, com links para a consulta do chamado. A paginação de 25 registros mantém os filtros e ordena por fechamento e identificador decrescentes.

## Relatório de performance

O cabeçalho identifica equipe, período e data de geração no fuso do Django. Os cards distinguem bases diferentes: **Total de chamados** conta criações no período; **SLA violado** e **Dentro do SLA** usam resoluções com fechamento e vencimento conhecidos; **Sem responsável** conta chamados ativos agora sem técnico atribuído, independentemente do período. Os percentuais de SLA não usam o total de criações como denominador. Zero resoluções avaliáveis exibe ausência de dados, sem inventar 0% de cumprimento.

O panorama compara resoluções dentro e fora do prazo. Ativos vencidos agora aparecem separadamente e não entram nesses percentuais nem na lista de resoluções com SLA violado. Igualdade entre fechamento e vencimento cumpre o prazo.

A distribuição usa as categorias atuais do modelo, com quantidade e percentual das criações no período. O ranking de analistas agrupa pelo autor registrado em `fechado_por`, incluindo contas inativas; ausências históricas aparecem como **Não registrado**. Cada resolução conta uma vez e as barras são proporcionais ao maior volume. O top 20 solicitantes usa criações no período e desempata pelo identificador da pessoa. Ambos respeitam a equipe selecionada, sem multiplicar contagens por comentários ou integrantes.

A lista clicável de resoluções com SLA violado tem 25 itens por página e paginação independente (`page_sla`), preservando os filtros e a página do detalhamento dos resolvidos (`page`). O layout usa cards claros, cabeçalho escuro e tabelas compactas com rolagem horizontal em telas pequenas. O dashboard e suas regras de acesso permanecem com o comportamento existente.
