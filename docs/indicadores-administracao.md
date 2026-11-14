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
