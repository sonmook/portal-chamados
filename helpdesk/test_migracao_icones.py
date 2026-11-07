from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class MigracaoIconesTests(TransactionTestCase):
    def tearDown(self):
        MigrationExecutor(connection).migrate([('helpdesk','0024_alertas_sla')])
        super().tearDown()

    def test_medalhas_anteriores_recebem_icone_sem_perder_historico(self):
        executor=MigrationExecutor(connection);anterior=('helpdesk','0019_conquistas')
        executor.migrate([anterior]);apps=executor.loader.project_state([anterior]).apps
        Regra=apps.get_model('helpdesk','RegraConquista');Conquista=apps.get_model('helpdesk','Conquista')
        Usuario=apps.get_model('auth','User')
        user=Usuario.objects.create(username='historico-icone')
        regra,_=Regra.objects.get_or_create(codigo='primeira-solucao',defaults={
            'nome':'Primeira solução','descricao':'Teste','alvo':'pessoa','metrica':'resolucoes','meta':1,'inicio_em':timezone.now()})
        c=Conquista.objects.create(regra=regra,usuario=user,nome='Medalha histórica',descricao='Critério original',meta=7,versao_regra=2)
        antes=Conquista.objects.filter(pk=c.pk).values().get();regra_antes=Regra.objects.filter(pk=regra.pk).values().get()
        executor=MigrationExecutor(connection);atual=('helpdesk','0020_icones_conquistas')
        executor.migrate([atual]);apps=executor.loader.project_state([atual]).apps
        Conquista=apps.get_model('helpdesk','Conquista');Regra=apps.get_model('helpdesk','RegraConquista')
        self.assertEqual(Conquista.objects.filter(pk=c.pk).values(*antes).get(),antes)
        self.assertEqual(Regra.objects.filter(pk=regra.pk).values(*regra_antes).get(),regra_antes)
        self.assertEqual(Conquista.objects.get(pk=c.pk).icone,'foguete')
        self.assertEqual(Regra.objects.get(pk=regra.pk).icone,'foguete')
