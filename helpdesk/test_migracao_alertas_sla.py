from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class MigracaoAlertasSLATests(TransactionTestCase):
    def tearDown(self):
        MigrationExecutor(connection).migrate([('helpdesk','0026_respostas_prontas')])
        super().tearDown()

    def test_preserva_chamados_e_notificacoes_sem_criar_alertas_na_migracao(self):
        anterior=('helpdesk','0023_notificacoes')
        executor=MigrationExecutor(connection);executor.migrate([anterior])
        apps=executor.loader.project_state([anterior]).apps
        User=apps.get_model('auth','User');Equipe=apps.get_model('helpdesk','Equipe')
        Chamado=apps.get_model('helpdesk','Chamado');Notificacao=apps.get_model('helpdesk','Notificacao')
        u=User.objects.create(username='historico-sla')
        equipe,_=Equipe.objects.get_or_create(nome='Fixture migração SLA',defaults={'ativa':True})
        t=Chamado.objects.create(titulo='Prazo antigo',descricao='Fixture',solicitante=u,equipe=equipe,data_vencimento=timezone.now())
        n=Notificacao.objects.create(chamado=t,destinatario=u,tipo='resposta',evento='fixture',lida_em=timezone.now())
        antes=Notificacao.objects.filter(pk=n.pk).values().get();chamado=Chamado.objects.filter(pk=t.pk).values().get()
        atual=('helpdesk','0024_alertas_sla');executor=MigrationExecutor(connection);executor.migrate([atual])
        apps=executor.loader.project_state([atual]).apps
        self.assertEqual(apps.get_model('helpdesk','Notificacao').objects.count(),1)
        self.assertEqual(apps.get_model('helpdesk','Notificacao').objects.values().get(),antes)
        self.assertEqual(apps.get_model('helpdesk','Chamado').objects.filter(pk=t.pk).values().get(),chamado)
