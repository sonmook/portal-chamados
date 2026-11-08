from datetime import timedelta
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class MigracaoConquistasTests(TransactionTestCase):
    def tearDown(self):
        MigrationExecutor(connection).migrate([('helpdesk', '0025_preferencia_colunas')])
        super().tearDown()

    def test_catalogo_nao_premia_historico_nem_altera_contas_e_chamados(self):
        executor=MigrationExecutor(connection);anterior=('helpdesk','0018_enquadramento_foto')
        executor.migrate([anterior]);apps=executor.loader.project_state([anterior]).apps
        Usuario=apps.get_model('auth','User');Chamado=apps.get_model('helpdesk','Chamado');Equipe=apps.get_model('helpdesk','Equipe')
        user=Usuario.objects.create(username='historico',first_name='Preservado',is_staff=True)
        equipe,_=Equipe.objects.get_or_create(triagem_padrao=True,defaults={'nome':'Triagem histórica','ativa':True})
        chamado=Chamado.objects.create(titulo='Histórico',descricao='Não deve contar',solicitante_id=user.pk,
            tecnico_id=user.pk,fechado_por_id=user.pk,equipe_id=equipe.pk,status='Resolvido',data_fechamento=timezone.now()-timedelta(days=1))
        antes=Chamado.objects.filter(pk=chamado.pk).values().get()
        inicio=timezone.now();executor=MigrationExecutor(connection);atual=('helpdesk','0019_conquistas')
        executor.migrate([atual]);apps=executor.loader.project_state([atual]).apps
        Regra=apps.get_model('helpdesk','RegraConquista')
        self.assertEqual(Regra.objects.count(),4)
        self.assertTrue(all(r.inicio_em>=inicio for r in Regra.objects.all()))
        self.assertFalse(apps.get_model('helpdesk','Conquista').objects.exists())
        self.assertFalse(apps.get_model('helpdesk','ResolucaoConquista').objects.exists())
        self.assertEqual(apps.get_model('helpdesk','Chamado').objects.filter(pk=chamado.pk).values().get(),antes)
        self.assertEqual(apps.get_model('auth','User').objects.get(pk=user.pk).first_name,'Preservado')
