"""Filtros e processamento periódico de avisos de prazo, sem efeitos colaterais em GETs."""
from datetime import timedelta, timezone as timezone_utc
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import Chamado, Equipe, IntegranteEquipe
from .notificacoes import gerar

ATIVOS = ('Aberto', 'Em Andamento')
ANTECEDENCIA = timedelta(hours=1)


def filtrar_sla(chamados, filtro, agora=None):
    if filtro not in ('proximos', 'vencidos'):
        return chamados
    agora = agora or timezone.now()
    ativos = chamados.filter(status__in=ATIVOS)
    if filtro == 'vencidos':
        return ativos.filter(data_vencimento__lt=agora)
    return ativos.filter(data_vencimento__gte=agora, data_vencimento__lte=agora + ANTECEDENCIA)


def contadores():
    return {'verificados': 0, 'sla_proximo': 0, 'sla_vencido': 0, 'sem_responsavel': 0}


@transaction.atomic
def processar_chamado(chamado_id, equipe_id, agora):
    resultado = contadores()
    # Mesma ordem de bloqueios dos fluxos de atribuição, encerramento e edição de equipe.
    if not Equipe.objects.select_for_update().filter(pk=equipe_id, ativa=True).first():
        return resultado
    chamado = Chamado.objects.select_for_update().filter(pk=chamado_id, equipe_id=equipe_id).first()
    if not chamado or chamado.status not in ATIVOS:
        return resultado
    resultado['verificados'] = 1
    membros = IntegranteEquipe.objects.filter(equipe_id=equipe_id, equipe__ativa=True)
    if chamado.tecnico_id:
        ids = User.objects.filter(pk=chamado.tecnico_id, is_active=True, is_staff=True,
            pk__in=membros.values('usuario_id')).values_list('pk', flat=True)
    else:
        ids = User.objects.filter(is_active=True, is_staff=True,
            pk__in=membros.filter(coordenador=True).values('usuario_id')).values_list('pk', flat=True)
    destinatarios = set(ids)
    if not destinatarios:
        return resultado
    if chamado.tecnico_id is None:
        evento = f'sem_responsavel:{chamado.pk}:{equipe_id}:{chamado.versao_atribuicao}'
        resultado['sem_responsavel'] = gerar(chamado, None, 'sem_responsavel', evento, destinatarios)
    prazo = chamado.data_vencimento
    if prazo is None or prazo > agora + ANTECEDENCIA:
        return resultado
    tipo = 'sla_vencido' if prazo < agora else 'sla_proximo'
    # Um aviso de cada tipo por prazo e destinatário; trocar o responsável não perde o aviso do novo técnico.
    prazo_chave = prazo.astimezone(timezone_utc.utc).isoformat(timespec='microseconds')
    evento = f'{tipo}:{chamado.pk}:{prazo_chave}'
    resultado[tipo] = gerar(chamado, None, tipo, evento, destinatarios)
    return resultado


def processar_alertas_sla(agora=None):
    inicio = agora or timezone.now()
    candidatos = Chamado.objects.filter(status__in=ATIVOS, equipe__ativa=True).filter(
        Q(tecnico__isnull=True) | Q(data_vencimento__lte=inicio + ANTECEDENCIA)
    ).order_by('pk').values_list('pk', 'equipe_id')
    total = contadores()
    for chamado_id, equipe_id in candidatos.iterator(chunk_size=200):
        resultado = processar_chamado(chamado_id, equipe_id, agora or timezone.now())
        for chave in total:
            total[chave] += resultado[chave]
    return total
