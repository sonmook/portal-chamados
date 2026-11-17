"""Transições atômicas de situação, sem alterar o prazo ou a interação da conversa."""
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .audit import registrar
from .estados import ATIVOS, EM_ESPERA, RESOLVIDO
from .models import Chamado, HistoricoStatus


class ConflitoStatus(Exception):
    pass


@transaction.atomic
def alterar_situacao(chamado, autor, destino, motivo='', *, versao_esperada=None,
        atribuicao_esperada=None, notificar=True):
    """Permissões são verificadas pelo fluxo chamador; o compare-and-set evita tela antiga."""
    if chamado.status not in ATIVOS or destino not in (*ATIVOS, RESOLVIDO):
        raise ValueError('Transição de situação inválida.')
    motivo = motivo.strip()
    if len(motivo) > 500 or (destino in EM_ESPERA and not motivo):
        raise ValueError('Informe o motivo da espera em até 500 caracteres.')
    versao = chamado.versao_status if versao_esperada is None else versao_esperada
    atribuicao = chamado.versao_atribuicao if atribuicao_esperada is None else atribuicao_esperada
    if versao != chamado.versao_status or atribuicao != chamado.versao_atribuicao:
        raise ConflitoStatus
    if destino == chamado.status:
        return False
    anterior = chamado.status
    agora = timezone.now()
    campos = {'status': destino, 'espera_desde': agora if destino in EM_ESPERA else None,
        'motivo_espera': motivo if destino in EM_ESPERA else '', 'data_atualizacao': agora}
    alteracoes = {'status': {'antes': anterior, 'depois': destino}}
    if destino == RESOLVIDO:
        campos.update(fechado_por_id=autor.pk, data_fechamento=agora)
        alteracoes.update(
            fechado_por_id={'antes': chamado.fechado_por_id, 'depois': autor.pk},
            data_fechamento={'antes': chamado.data_fechamento.isoformat() if chamado.data_fechamento else None,
                'depois': agora.isoformat()},
        )
    atualizado = Chamado.objects.filter(pk=chamado.pk, status=anterior,
        equipe_id=chamado.equipe_id, tecnico_id=chamado.tecnico_id,
        versao_status=versao, versao_atribuicao=atribuicao).update(
            **campos, versao_status=F('versao_status') + 1)
    if not atualizado:
        raise ConflitoStatus
    HistoricoStatus.objects.create(chamado=chamado, autor=autor, status_anterior=anterior,
        status_novo=destino, motivo=motivo, criado_em=agora, versao=versao + 1)
    if motivo:
        alteracoes['motivo'] = {'alterado': True}
    registrar('helpdesk.chamado', chamado.pk, 'alterado', alteracoes)
    for campo, valor in campos.items():
        setattr(chamado, campo, valor)
    chamado.versao_status = versao + 1
    if notificar:
        from .notificacoes import notificar_status
        notificar_status(chamado, autor.pk)
    return True
