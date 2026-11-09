from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigracaoRespostasProntasTests(TransactionTestCase):
    def tearDown(self):
        MigrationExecutor(connection).migrate([('helpdesk','0026_respostas_prontas')])
        super().tearDown()

    def test_cria_tres_modelos_sem_enviar_mensagens_ou_alterar_historico(self):
        anterior=('helpdesk','0025_preferencia_colunas')
        executor=MigrationExecutor(connection);executor.migrate([anterior])
        apps=executor.loader.project_state([anterior]).apps
        User=apps.get_model('auth','User');Pref=apps.get_model('helpdesk','PreferenciaListaChamados')
        Audit=apps.get_model('helpdesk','RegistroAuditoria')
        user=User.objects.create(username='historico-respostas')
        ordem=['ticket','assunto','abertura','status','prioridade','sla','interacao','solicitante','tecnico','acoes']
        Pref.objects.create(usuario=user,ordem=ordem)
        audit=Audit.objects.create(ator=user,objeto='auth.user',objeto_id=user.pk,acao='alterado')
        antes=Audit.objects.filter(pk=audit.pk).values().get()
        atual=('helpdesk','0026_respostas_prontas');executor=MigrationExecutor(connection);executor.migrate([atual])
        apps=executor.loader.project_state([atual]).apps
        Modelo=apps.get_model('helpdesk','RespostaPronta')
        self.assertEqual(set(Modelo.objects.values_list('nome',flat=True)),{'Atendimento iniciado','Solicitar mais informações','Aguardando validação'})
        self.assertEqual(Modelo.objects.filter(ativa=True,versao=0).count(),3)
        self.assertFalse(apps.get_model('helpdesk','Comentario').objects.exists())
        self.assertFalse(apps.get_model('helpdesk','Notificacao').objects.exists())
        self.assertEqual(apps.get_model('helpdesk','PreferenciaListaChamados').objects.get(usuario=user.pk).ordem,ordem)
        self.assertEqual(apps.get_model('helpdesk','RegistroAuditoria').objects.filter(pk=audit.pk).values().get(),antes)
