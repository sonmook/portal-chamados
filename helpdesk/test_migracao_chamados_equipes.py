from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigracaoChamadosEquipeTests(TransactionTestCase):
    def tearDown(self):
        MigrationExecutor(connection).migrate([('helpdesk', '0015_chamados_por_equipe')])
        super().tearDown()

    def test_upgrade_preserva_chamados_e_inclui_responsaveis_ativos(self):
        executor = MigrationExecutor(connection)
        anterior = ('helpdesk', '0014_merge_0012_ultima_interacao_0013_equipes_cadastro')
        executor.migrate([anterior])
        apps = executor.loader.project_state([anterior]).apps
        Usuario = apps.get_model('auth', 'User')
        Chamado = apps.get_model('helpdesk', 'Chamado')
        Equipe = apps.get_model('helpdesk', 'Equipe')
        Integrante = apps.get_model('helpdesk', 'IntegranteEquipe')
        cliente = Usuario.objects.create(username='cliente-migracao', is_active=True)
        tecnico = Usuario.objects.create(username='tecnico-migracao', is_active=True, is_staff=True)
        resolutor = Usuario.objects.create(username='resolutor-migracao', is_active=True, is_staff=True)
        inativo = Usuario.objects.create(username='inativo-migracao', is_active=False, is_staff=True)
        equipe, _ = Equipe.objects.get_or_create(nome='Central de Serviços — N1')
        equipe.ativa = False
        equipe.save()
        Integrante.objects.get_or_create(equipe=equipe, usuario=tecnico, defaults={'coordenador': True})
        chamados = [
            Chamado.objects.create(titulo='Aberto anterior', descricao='Preservar', solicitante=cliente, tecnico=tecnico),
            Chamado.objects.create(titulo='Resolvido anterior', descricao='Preservar', solicitante=cliente,
                                   tecnico=inativo, fechado_por=resolutor, status='Resolvido'),
        ]
        campos = ('id', 'status', 'solicitante_id', 'tecnico_id', 'fechado_por_id', 'data_criacao', 'data_atualizacao',
                  'data_vencimento', 'data_fechamento', 'ultima_interacao_em')
        ids = [c.pk for c in chamados]
        antes = list(Chamado.objects.filter(pk__in=ids).order_by('pk').values(*campos))
        executor = MigrationExecutor(connection)
        executor.migrate([('helpdesk', '0015_chamados_por_equipe')])
        apps = executor.loader.project_state([('helpdesk', '0015_chamados_por_equipe')]).apps
        Chamado = apps.get_model('helpdesk', 'Chamado')
        Equipe = apps.get_model('helpdesk', 'Equipe')
        Integrante = apps.get_model('helpdesk', 'IntegranteEquipe')
        self.assertEqual(list(Chamado.objects.filter(pk__in=ids).order_by('pk').values(*campos)), antes)
        triagem = Equipe.objects.get(triagem_padrao=True)
        self.assertTrue(triagem.ativa)
        self.assertEqual(set(Chamado.objects.filter(pk__in=ids).values_list('equipe_id', flat=True)), {triagem.pk})
        self.assertTrue(Integrante.objects.get(equipe=triagem, usuario_id=tecnico.pk).coordenador)
        self.assertFalse(Integrante.objects.get(equipe=triagem, usuario_id=resolutor.pk).coordenador)
        self.assertFalse(Integrante.objects.filter(equipe=triagem, usuario_id=inativo.pk).exists())
