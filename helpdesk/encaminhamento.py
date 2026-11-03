from django.db import transaction

from .audit import registrar
from .models import Equipe, IntegranteEquipe, RegraEncaminhamento


@transaction.atomic
def criar_chamado_encaminhado(chamado):
    """Escolhe o destino no servidor, sem alterar o roteamento de chamados existentes."""
    if not chamado._state.adding:
        raise ValueError('O encaminhamento automático só pode ser aplicado a novos chamados.')
    triagem = Equipe.objects.get(triagem_padrao=True, ativa=True)
    regra = RegraEncaminhamento.objects.filter(categoria=chamado.categoria).first()
    ids = {triagem.pk}
    if regra:
        ids.add(regra.equipe_id)
    # Compartilha os bloqueios com edição de equipe e remoção de integrantes.
    equipes = {e.pk: e for e in Equipe.objects.select_for_update().filter(pk__in=ids).order_by('pk')}
    destino = triagem
    motivo = 'sem_regra'
    if regra:
        if not regra.ativa:
            motivo = 'regra_inativa'
        elif not RegraEncaminhamento.objects.filter(pk=regra.pk, ativa=True, versao=regra.versao,
                                                    equipe_id=regra.equipe_id).exists():
            motivo = 'regra_alterada'
        else:
            candidata = equipes.get(regra.equipe_id)
            if candidata is None or not candidata.ativa:
                motivo = 'equipe_inativa'
            elif not candidata.triagem_padrao and not IntegranteEquipe.objects.filter(
                equipe_id=candidata.pk, usuario__is_active=True, usuario__is_staff=True,
            ).exists():
                motivo = 'sem_tecnico_ativo'
            else:
                destino = candidata
                motivo = None
    chamado.equipe_id = destino.pk
    chamado.tecnico_id = None
    chamado.save()
    registrar('helpdesk.chamado', chamado.pk, 'encaminhado', {
        'categoria': chamado.categoria,
        'equipe_id': destino.pk,
        'regra_id': regra.pk if regra else None,
        'versao_regra': regra.versao if regra else None,
        'modo': 'triagem' if motivo else 'categoria',
        'motivo_triagem': motivo,
    })
    return chamado
