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


def dados_situacao(chamado):
    chamado.refresh_from_db()
    return {'versao_status': chamado.versao_status, 'versao_atribuicao': chamado.versao_atribuicao}


def restaurar_migracoes_atuais():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes('helpdesk'))


def registrar_resultados_fixture():
    from .atendimento import registrar_ciclo_concluido
    from .models import Chamado
    for chamado in Chamado.objects.filter(status__in=['Resolvido', 'Fechado']):
        registrar_ciclo_concluido(chamado)
