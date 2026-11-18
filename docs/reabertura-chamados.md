# Reabertura de chamados e ciclos de atendimento

A v1.13.0 permite retomar um chamado Resolvido ou Fechado sem criar outro número e sem apagar conversa, anexos, solução ou resultados anteriores. Não há prazo máximo para reabrir nesta versão.

## Quem pode reabrir

O solicitante ou o técnico responsável ativo e integrante da equipe pode usar **Reabrir chamado** no detalhe. Ter acesso administrativo ou coordenar a equipe, por si só, não concede essa ação. O servidor revalida acesso e permissão em cada pedido. É obrigatório explicar o motivo em até 500 caracteres; o texto fica visível a quem já tem acesso ao chamado. Não é uma nota interna.

O envio é POST com CSRF e versões da situação/atribuição. Formulário inválido retorna HTTP 400 preservando o texto. Versões antigas retornam HTTP 409 sem gravação. Um segundo envio após reabertura é recusado porque o chamado já está ativo. A resolução também exige essas versões; uma solução enviada de uma tela anterior à reabertura não pode encerrar o novo ciclo. Integrações devem enviar `versao_status` e `versao_atribuicao` atuais, disponíveis nos formulários.

## Responsável e notificações

- Responsável ativo, técnico e integrante da equipe de destino: retorna para Em Andamento.
- Sem responsável elegível: retorna para Aberto, na fila da equipe.
- Equipe anterior inativa: encaminha à triagem ativa. Mantém o técnico somente se ele também for elegível nessa equipe.

A atribuição recebe uma nova versão, invalidando também transferências antigas. O portal avisa os participantes elegíveis, excluindo o autor. Sem técnico, avisa a coordenação ativa; sem coordenação elegível, avisa administradores ativos. Não cria uma cópia do motivo na notificação nem um comentário duplicado. O motivo e a transição ficam no Histórico de situações; a reabertura conta como interação do atendimento.

## Prazo e resultados de cada ciclo

O ciclo 1 começa na abertura original. Cada reabertura incrementa o número do ciclo e registra outro início. O prazo do novo ciclo usa a prioridade e o calendário vigentes na reabertura (Crítica 4 h, Alta 24 h, Normal 48 h, Baixa 120 h). A data original de criação permanece. Campos de fechamento e espera atuais são limpos; comentários e anexos de soluções anteriores permanecem.

Cada conclusão guarda início do ciclo, vencimento, fechamento, equipe, autor, prioridade e situação final. Os resultados ficam disponíveis em **Ciclos concluídos e resultados de SLA**, com dez por página, e não oferecem edição/exclusão no portal ou Admin. Um chamado legado sem fechamento ou vencimento conhecido mantém essa ausência; não se inventa uma data ou resultado de SLA.

**Indicadores administrativos:** aberturas contam chamados; ativos usam a situação atual; resoluções, SLA, tempo médio e rankings contam ciclos concluídos no período de fechamento e na equipe da conclusão. Reabrir não remove a resolução anterior. O tempo de um novo ciclo começa na reabertura, excluindo o intervalo em que o chamado estava encerrado.

**Dashboard:** contagens de chamados por situação continuam atuais. SLA, TMR e produtividade usam os ciclos concluídos dos chamados criados no período selecionado, conforme acesso atual ao chamado; o filtro de equipe desses resultados usa a equipe da conclusão. O dashboard mantém seu fallback histórico de TMR para registros sem data de fechamento; o relatório administrativo usa somente datas válidas.

**Conquistas:** permanece um evento elegível por chamado. Reabrir e encerrar repetidamente não concede novas contagens pelo mesmo chamado. Avisos de resolução e SLA, em contraste, têm identidade por ciclo; leituras dos ciclos anteriores são preservadas. Os estados de espera continuam consumindo o prazo do ciclo, sem pausa.

## Atualização e validação

1. Pare portal, alertas e demais escritores; faça backup do banco e uploads.
2. Atualize o código aprovado e execute `python manage.py migrate` para aplicar **0028_reabertura_ciclos**.
3. Execute `python scripts/validar_atualizacao.py`. Em produção, colete estáticos e reinicie os serviços.
4. No Windows use o Python da venv e o inicializador habitual.

A migração registra o ciclo 1 dos chamados já finalizados com os valores existentes, inclusive ausências históricas. Mantém chamados ativos, datas, avisos e leituras; não cria reaberturas, comentários, conquistas ou notificações retroativas. Resultados, ciclos atuais e histórico entram no backup completo; a homologação confirma restauração em destino separado.

Sem dependência nova. Após usar ciclos adicionais, uma recuperação para código anterior requer backup compatível com aquela versão; reverter a migração removeria os resultados históricos dos ciclos.

Desde a v1.14.0, [notas internas](notas-internas.md) acompanham o chamado e são consultadas conforme o acesso técnico atual. Não alteram o ciclo nem seus resultados. Em chamados finalizados, o histórico pode ser consultado, mas novas notas exigem reabertura.
