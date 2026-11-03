from .models import Equipe, IntegranteEquipe


def integrar_triagem(*usuarios):
    """Técnicos das fixtures de atendimento pertencem explicitamente à mesma equipe."""
    equipe = Equipe.objects.get(triagem_padrao=True)
    for usuario in usuarios:
        IntegranteEquipe.objects.get_or_create(equipe=equipe, usuario=usuario)
    return equipe


def dados_atribuicao(chamado):
    chamado.refresh_from_db()
    return {'equipe': chamado.equipe_id, 'equipe_anterior': chamado.equipe_id,
            'versao_atribuicao': chamado.versao_atribuicao}
