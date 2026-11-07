from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class MigracaoConstrutorTests(TransactionTestCase):
    def tearDown(self):
        MigrationExecutor(connection).migrate([('helpdesk','0023_notificacoes')])
        super().tearDown()

    def test_preserva_catalogo_medalhas_e_eventos_sem_inventar_trilhas(self):
        executor=MigrationExecutor(connection);anterior=('helpdesk','0020_icones_conquistas')
        executor.migrate([anterior]);apps=executor.loader.project_state([anterior]).apps
        Usuario=apps.get_model('auth','User');Regra=apps.get_model('helpdesk','RegraConquista');Conquista=apps.get_model('helpdesk','Conquista')
        user=Usuario.objects.create(username='historico-construtor')
        regra,_=Regra.objects.get_or_create(codigo='primeira-solucao',defaults={'nome':'Primeira solução','descricao':'Teste','alvo':'pessoa','metrica':'resolucoes','meta':1,'inicio_em':timezone.now(),'icone':'foguete'})
        c=Conquista.objects.create(regra=regra,usuario=user,nome='Nome original',descricao='Critério original',meta=7,versao_regra=2,icone='estrela')
        antes=Conquista.objects.filter(pk=c.pk).values().get();r_antes=Regra.objects.filter(pk=regra.pk).values().get()
        total=Regra.objects.count()
        executor=MigrationExecutor(connection);atual=('helpdesk','0021_construtor_conquistas')
        executor.migrate([atual]);apps=executor.loader.project_state([atual]).apps
        Regra=apps.get_model('helpdesk','RegraConquista');Conquista=apps.get_model('helpdesk','Conquista')
        self.assertEqual(Conquista.objects.filter(pk=c.pk).values(*antes).get(),antes)
        self.assertEqual(Regra.objects.filter(pk=regra.pk).values(*r_antes).get(),r_antes)
        self.assertEqual(Regra.objects.count(),total)
        self.assertIsNone(Regra.objects.get(pk=regra.pk).plano_id)
        self.assertEqual(Conquista.objects.get(pk=c.pk).nivel,'')
        self.assertFalse(apps.get_model('helpdesk','PlanoConquista').objects.exists())
