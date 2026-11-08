"""Indicadores da fila calculados sobre o mesmo escopo de acesso da listagem."""
from urllib.parse import urlencode
from django.db.models import Count, Q
from django.urls import reverse
from .sla import ATIVOS, ANTECEDENCIA


def resumo_operacional(chamados, usuario, agora, equipe='', fila='', sla='', outros_filtros=False):
    if not (usuario.is_staff or usuario.is_superuser):
        return []
    totais = chamados.filter(status__in=ATIVOS).aggregate(
        minha=Count('pk', filter=Q(tecnico_id=usuario.pk)),
        sem_responsavel=Count('pk', filter=Q(tecnico__isnull=True)),
        proximos=Count('pk', filter=Q(data_vencimento__gte=agora, data_vencimento__lte=agora+ANTECEDENCIA)),
        vencidos=Count('pk', filter=Q(data_vencimento__lt=agora)),
    )
    definicoes = [
        ('minha', 'Minha fila', 'person-check', {'fila': 'minha'}, fila == 'minha' and not sla),
        ('sem_responsavel', 'Sem responsável', 'person-dash', {'fila': 'sem_responsavel'}, fila == 'sem_responsavel' and not sla),
        ('proximos', 'Próximos do prazo', 'hourglass-split', {'sla': 'proximos'}, sla == 'proximos' and not fila),
        ('vencidos', 'SLA vencido', 'alarm', {'sla': 'vencidos'}, sla == 'vencidos' and not fila),
    ]
    cards = []
    for chave, nome, icone, filtros, ativo in definicoes:
        parametros = {'equipe': equipe, **filtros} if equipe else filtros
        cards.append({'chave': chave, 'nome': nome, 'icone': icone, 'total': totais[chave],
            'url': reverse('lista_chamados')+'?'+urlencode(parametros), 'ativo': ativo and not outros_filtros})
    return cards
