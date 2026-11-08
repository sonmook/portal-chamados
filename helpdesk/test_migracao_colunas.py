from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigracaoColunasTests(TransactionTestCase):
    def tearDown(self):
        MigrationExecutor(connection).migrate([('helpdesk','0025_preferencia_colunas')])
        super().tearDown()

    def test_adiciona_preferencia_sem_alterar_usuarios_ou_registros_existentes(self):
        anterior=('helpdesk','0024_alertas_sla')
        executor=MigrationExecutor(connection);executor.migrate([anterior])
        apps=executor.loader.project_state([anterior]).apps
        Usuario=apps.get_model('auth','User');Auditoria=apps.get_model('helpdesk','RegistroAuditoria')
        u=Usuario.objects.create(username='historico-colunas',is_active=True)
        registro=Auditoria.objects.create(ator=u,objeto='auth.user',objeto_id=u.pk,acao='alterado',alteracoes={'is_active':{'antes':False,'depois':True}})
        antes=Auditoria.objects.filter(pk=registro.pk).values().get()
        atual=('helpdesk','0025_preferencia_colunas');executor=MigrationExecutor(connection);executor.migrate([atual])
        apps=executor.loader.project_state([atual]).apps
        self.assertFalse(apps.get_model('helpdesk','PreferenciaListaChamados').objects.exists())
        self.assertEqual(apps.get_model('helpdesk','RegistroAuditoria').objects.filter(pk=registro.pk).values().get(),antes)
        self.assertTrue(apps.get_model('auth','User').objects.filter(pk=u.pk,username='historico-colunas',is_active=True).exists())
