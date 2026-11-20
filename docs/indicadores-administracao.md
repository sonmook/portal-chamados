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

## Exportar resoluções para CSV (v1.16.0)

1. Acesse **Administração → Indicadores** com um administrador ativo.
2. Selecione equipe e período e clique em **Aplicar filtros**.
3. Na seção **Ciclos concluídos**, clique em **Exportar CSV**.

O download usa os filtros aplicados ao relatório. Se editar os campos, aplique-os antes de exportar. O CSV inclui **todas as páginas** das resoluções, na ordem de fechamento e identificador decrescentes. Os cards, rankings e chamados ativos não são linhas desse arquivo: cada linha representa um **ciclo concluído**, inclusive de chamados atualmente reabertos. O recorte de resoluções é compartilhado entre tela e download.

Colunas do arquivo:

| Coluna | Conteúdo |
| --- | --- |
| Chamado | Número do chamado |
| Ciclo | Número do ciclo concluído |
| Título | Título atual do chamado |
| Equipe | Equipe registrada na conclusão do ciclo, inclusive inativa |
| Resolvido por | Nome completo atual do autor registrado no ciclo, ou seu usuário; ausência histórica aparece como Não registrado |
| Status do ciclo | Resolvido ou Fechado, conforme a conclusão registrada |
| Início do ciclo | Data de início usada pelo tempo médio |
| Vencimento | Prazo preservado do ciclo; vazio quando desconhecido |
| Fechamento | Data da resolução; vazio quando desconhecido |
| SLA | Dentro do SLA, Fora do SLA ou Sem dados de SLA |

O vínculo de equipe/autor é histórico; renomear a equipe, o título ou o nome da pessoa aparece com os valores atuais. Transferir o chamado após reabertura não transfere o resultado anterior. Igualdade entre fechamento e vencimento cumpre o SLA. Sem data de fechamento, o ciclo aparece somente em **Todo o histórico**. Consulta sem resultados gera apenas o cabeçalho. Descrição, solução, conversa pública, notas internas e arquivos não são exportados.

O arquivo `nexaltri-resolucoes-AAAA-MM-DD.csv` usa UTF-8 com BOM para preservar os acentos, ponto e vírgula e todos os campos entre aspas. Datas usam ISO 8601 com segundos e deslocamento do fuso ativo, por exemplo `2026-11-20T14:30:00-03:00`. Pode ser aberto no Excel; se o separador do computador for diferente, use **Dados → De Texto/CSV**, escolha UTF-8 e ponto e vírgula. Campos que pareçam fórmulas, incluindo prefixos após espaços e variantes de largura completa, recebem uma tabulação dentro das aspas. Ela faz parte do texto exportado; a proteção é destinada à leitura em planilha, não à importação de texto idêntico ao original em outros sistemas.

A rota `/administracao/indicadores/exportar.csv` exige administrador ativo mesmo no acesso direto e aceita somente GET. Os mesmos filtros do formulário são validados; um filtro inválido mostra o formulário com erros e HTTP 400, sem `Content-Disposition` de download. A resposta do CSV usa `Cache-Control: private, no-store` e não modifica chamados ou ciclos. Não há migração nem dependência adicional de execução.

Referências técnicas: [CSV com Django](https://docs.djangoproject.com/en/6.0/howto/outputting-csv/) e [proteção contra fórmulas em CSV — OWASP](https://community.owasp.org/attacks/CSV_Injection).
