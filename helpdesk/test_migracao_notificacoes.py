from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigracaoNotificacoesTests(TransactionTestCase):
    def tearDown(self):
        MigrationExecutor(connection).migrate([('helpdesk','0024_alertas_sla')])
        super().tearDown()

    def test_adiciona_tabela_sem_gerar_alertas_retroativos_ou_alterar_chamado(self):
        anterior=('helpdesk','0022_ampliar_catalogo_conquistas')
        executor=MigrationExecutor(connection);executor.migrate([anterior])
        apps=executor.loader.project_state([anterior]).apps
        User=apps.get_model('auth','User');Equipe=apps.get_model('helpdesk','Equipe');Chamado=apps.get_model('helpdesk','Chamado')
        user=User.objects.create(username='historico-notificacoes')
        equipe,_=Equipe.objects.get_or_create(nome='Fixture migração',defaults={'ativa':True})
        t=Chamado.objects.create(titulo='Histórico preservado',descricao='Fixture',solicitante=user,equipe=equipe)
        antes=Chamado.objects.filter(pk=t.pk).values().get()
        atual=('helpdesk','0023_notificacoes');executor=MigrationExecutor(connection);executor.migrate([atual])
        apps=executor.loader.project_state([atual]).apps
        self.assertFalse(apps.get_model('helpdesk','Notificacao').objects.exists())
        self.assertEqual(apps.get_model('helpdesk','Chamado').objects.filter(pk=t.pk).values(*antes).get(),antes)
