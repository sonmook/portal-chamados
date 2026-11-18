"""Transições e ciclos de atendimento com histórico transacional."""
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Coalesce, Greatest
from django.db.models import Value
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User
from django.utils import timezone

from .audit import registrar
from .estados import ABERTO, EM_ANDAMENTO, ATIVOS, EM_ESPERA, FINALIZADOS, RESOLVIDO
from .models import Chamado, HistoricoStatus, CicloAtendimento, Equipe, HORAS_SLA, calcular_prazo_util
from .acesso import integrante_ativo


class ConflitoStatus(Exception):
    pass


def registrar_ciclo_concluido(chamado):
    if chamado.status not in FINALIZADOS:
        raise ValueError('Somente ciclos concluídos podem ser registrados.')
    ciclo, _ = CicloAtendimento.objects.get_or_create(chamado=chamado, numero=chamado.ciclo_atual,
        defaults={campo: getattr(chamado, campo) for campo in (
            'equipe_id', 'fechado_por_id', 'prioridade', 'status', 'data_atualizacao',
            'data_vencimento', 'data_fechamento')} | {'data_criacao': chamado.inicio_ciclo})
    return ciclo


def pode_reabrir(usuario, chamado):
    return usuario.is_active and chamado.status in FINALIZADOS and (
        chamado.solicitante_id == usuario.pk or (
            chamado.tecnico_id == usuario.pk and integrante_ativo(usuario, chamado.equipe_id)))


@transaction.atomic
def reabrir_atendimento(chamado, autor, motivo, *, versao_esperada, atribuicao_esperada):
    motivo = motivo.strip()
    if not motivo or len(motivo) > 500:
        raise ValueError('Informe o motivo da reabertura em até 500 caracteres.')
    # Equipes em ordem antes do chamado e dos usuários, como a redistribuição.
    triagem = Equipe.objects.get(triagem_padrao=True, ativa=True)
    equipes = {e.pk: e for e in Equipe.objects.select_for_update().filter(
        pk__in=sorted({chamado.equipe_id, triagem.pk})).order_by('pk')}
    atual = Chamado.objects.select_for_update().filter(pk=chamado.pk, equipe_id=chamado.equipe_id).first()
    if (atual is None or atual.versao_status != versao_esperada
            or atual.versao_atribuicao != atribuicao_esperada or atual.status not in FINALIZADOS):
        raise ConflitoStatus
    usuarios = {u.pk: u for u in User.objects.select_for_update().filter(
        pk__in={autor.pk, atual.tecnico_id} - {None}).order_by('pk')}
    autor_atual = usuarios.get(autor.pk)
    if autor_atual is None or not pode_reabrir(autor_atual, atual):
        raise PermissionDenied
    destino = equipes[atual.equipe_id] if equipes[atual.equipe_id].ativa else equipes[triagem.pk]
    tecnico = usuarios.get(atual.tecnico_id)
    if not tecnico or not integrante_ativo(tecnico, destino.pk):
        tecnico = None
    agora = timezone.now()
    prazo = calcular_prazo_util(agora, HORAS_SLA.get(atual.prioridade, 48))
    campos = {'status': EM_ANDAMENTO if tecnico else ABERTO, 'ciclo_atual': atual.ciclo_atual + 1,
        'ciclo_iniciado_em': agora, 'data_vencimento': prazo, 'data_fechamento': None,
        'fechado_por_id': None, 'espera_desde': None, 'motivo_espera': '',
        'equipe_id': destino.pk, 'tecnico_id': tecnico.pk if tecnico else None,
        'data_atualizacao': agora}
    atualizado = Chamado.objects.filter(pk=atual.pk, status=atual.status,
        versao_status=versao_esperada, versao_atribuicao=atribuicao_esperada,
        equipe_id=atual.equipe_id, tecnico_id=atual.tecnico_id).update(**campos,
            versao_status=F('versao_status') + 1, versao_atribuicao=F('versao_atribuicao') + 1,
            ultima_interacao_em=Greatest(Coalesce('ultima_interacao_em', 'data_criacao'), Value(agora)))
    if not atualizado:
        raise ConflitoStatus
    # Importações legadas finalizadas também ganham um retrato antes de reabrir.
    registrar_ciclo_concluido(atual)
    HistoricoStatus.objects.create(chamado=atual, autor=autor, status_anterior=atual.status,
        status_novo=campos['status'], motivo=motivo, criado_em=agora, versao=versao_esperada + 1)
    registrar('helpdesk.chamado', atual.pk, 'reaberto', {
        campo: {'antes': getattr(atual, campo), 'depois': valor}
        for campo, valor in campos.items() if campo in ('status', 'ciclo_atual', 'equipe_id', 'tecnico_id')
    } | {'motivo': {'alterado': True}, 'data_vencimento': {
        'antes': atual.data_vencimento.isoformat() if atual.data_vencimento else None, 'depois': prazo.isoformat()}})
    atual.refresh_from_db()
    from .notificacoes import notificar_reabertura
    notificar_reabertura(atual, autor.pk)
    return atual


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
    if destino == RESOLVIDO:
        registrar_ciclo_concluido(chamado)
    if notificar:
        from .notificacoes import notificar_status
        notificar_status(chamado, autor.pk)
    return True
