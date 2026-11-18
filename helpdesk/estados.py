"""Situações do atendimento e agrupamentos usados por fila, SLA e permissões."""
ABERTO = 'Aberto'
EM_ANDAMENTO = 'Em Andamento'
AGUARDANDO_SOLICITANTE = 'Aguardando solicitante'
AGUARDANDO_FORNECEDOR = 'Aguardando fornecedor'
RESOLVIDO = 'Resolvido'
FECHADO = 'Fechado'

EM_ESPERA = (AGUARDANDO_SOLICITANTE, AGUARDANDO_FORNECEDOR)
ATIVOS = (ABERTO, EM_ANDAMENTO, *EM_ESPERA)
FINALIZADOS = (RESOLVIDO, FECHADO)
STATUS_CHOICES = tuple((status, status) for status in (*ATIVOS, *FINALIZADOS))
