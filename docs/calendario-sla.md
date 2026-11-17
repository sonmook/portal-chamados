# Calendário de SLA e cobertura da triagem

A v1.11.0 corrige o uso do fuso no cálculo e permite definir o calendário de atendimento da instalação. Não recalcula vencimentos já gravados.

## Regra padrão

- Fuso: **America/Sao_Paulo**.
- Atendimento: **segunda a sexta, das 00:00 às 24:00**. Mantém a contagem de 24 horas em cada dia útil; não presume expediente comercial.
- Prioridades: Crítica 4h, Alta 24h, Normal 48h e Baixa 120h.
- Nenhum feriado é incluído automaticamente. As datas dependem da operação e da localidade.

No padrão, sexta às 18h com prazo de quatro horas vence sexta às 22h. Sexta às 23h30 vence segunda às 03h30. Uma abertura no sábado começa a contar na segunda às 00h. O vencimento exatamente às 24h representa o fim do último dia de atendimento, sem consumir horas do dia seguinte.

Instantes continuam armazenados em UTC. O calendário é aplicado no fuso configurado e as telas passam a usar esse mesmo fuso. O padrão anterior das telas era UTC; a apresentação em São Paulo fica três horas atrás, sem alterar os instantes armazenados. Para manter a apresentação anterior, defina DJANGO_TIME_ZONE=UTC, sabendo que o calendário também seguirá UTC.

## Configuração da instalação

Variáveis de ambiente, também exemplificadas em `deploy/.env.example`:

| Variável | Padrão | Significado |
| --- | --- | --- |
| `DJANGO_TIME_ZONE` | `America/Sao_Paulo` | Fuso IANA para o portal e o calendário |
| `DJANGO_SLA_INICIO` | `00:00` | Início do atendimento em HH:MM |
| `DJANGO_SLA_FIM` | `24:00` | Fim, posterior ao início; 24:00 permitido somente aqui |
| `DJANGO_SLA_DIAS` | `0,1,2,3,4` | Dias sem repetição: 0=segunda até 6=domingo |
| `DJANGO_SLA_FERIADOS` | vazio | Datas YYYY-MM-DD separadas por vírgula |

Exemplo de expediente das 08h às 18h, de segunda a sexta, com uma data sem atendimento:

```dotenv
DJANGO_TIME_ZONE=America/Sao_Paulo
DJANGO_SLA_INICIO=08:00
DJANGO_SLA_FIM=18:00
DJANGO_SLA_DIAS=0,1,2,3,4
DJANGO_SLA_FERIADOS=2026-11-20
```

Esse é um exemplo, não uma configuração aplicada automaticamente. Com esse expediente, sexta às 17h e quatro horas de SLA consomem uma hora na sexta e as três restantes no próximo dia de atendimento às 11h.

Para 24×7, mantenha 00:00–24:00 e use `DJANGO_SLA_DIAS=0,1,2,3,4,5,6`. O calendário tem uma janela contínua por dia e é global para a instalação; intervalos de almoço, turnos que cruzam a meia-noite e calendários por equipe não são configurados nesta versão.

No Docker, coloque as variáveis no arquivo de ambiente usado pelo Compose e recrie app e alertas após validar. No Windows, defina as variáveis antes de executar o inicializador; o projeto não carrega arquivos `.env` automaticamente fora do Compose. Pare e reinicie os dois processos para aplicar a nova configuração.

Execute `python manage.py check --fail-level WARNING` ou o comando de validação da atualização. Calendários com horário inválido, fim anterior/igual ao início, lista vazia de dias, dias repetidos/fora do intervalo ou feriados inválidos são recusados pelo check `helpdesk.E001`.

## Histórico e alterações

O novo cálculo é usado quando um vencimento precisa ser gerado. Vencimentos já preenchidos permanecem iguais ao editar ou ao mudar o calendário. Alterar prioridade não reescreve o prazo existente. Essa política preserva os compromissos e indicadores históricos; uma futura revisão manual de prazo deve registrar motivo e valores anterior/novo.

O prazo conta horas reais dentro das janelas locais. Minutos e segundos são preservados, e a duração entre instantes é calculada em UTC. Datas de entrada precisam ter fuso. As duas funções públicas de cálculo usam o mesmo serviço.

O aviso de proximidade continua sendo de até **uma hora corrida** antes do vencimento. Os estados de espera da v1.12.0 continuam consumindo SLA; veja [Estados de espera](estados-espera.md). Não há SLA separado de primeira resposta nem reabertura nesta entrega.

## Avisos quando falta coordenação

1. Para chamado atribuído, o técnico responsável continua sendo o destinatário dos avisos de prazo, desde que ativo e integrante da equipe.
2. Para chamado sem responsável, recebem os coordenadores ativos com papel de técnico e vínculo com a equipe ativa.
3. Se não houver coordenador elegível, recebem os administradores ativos (`is_active`, `is_staff` e `is_superuser`). Eles já possuem acesso global; nenhum acesso novo é concedido.
4. Se também não houver administrador elegível, não é criada notificação e o comando registra o chamado no contador `sem_destinatario`.

O substituto recebe aviso de falta de responsável e, quando pertinente, proximidade/vencimento de SLA. As chaves de deduplicação existentes são preservadas. Ler avisos não permite reenviar o mesmo evento. Um novo coordenador passa a receber os avisos elegíveis, sem repetir avisos para administradores já notificados.

A Administração sinaliza equipes ativas sem coordenador elegível e mostra até cinco links, com acesso à lista completa. A lista de equipes destaca também ausência de técnico ativo. Essas consultas não criam avisos nem registros de auditoria.

Os primeiros ciclos após a atualização podem notificar administradores sobre pendências que antes não tinham destinatário. Os avisos permanecem internos ao portal; não há envio de e-mail nesta entrega.
