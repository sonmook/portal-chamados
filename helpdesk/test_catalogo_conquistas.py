from datetime import timedelta
from importlib import import_module
from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from .models import RegraConquista, Conquista, ResolucaoConquista
from .test_conquistas import ConquistasFixtureMixin


class CatalogoConquistasTests(ConquistasFixtureMixin, TestCase):
    def test_catalogo_pronto_com_diferentes_destinatarios_metricas_e_icones(self):
        self.assertEqual(RegraConquista.objects.count(),12)
        self.assertEqual(RegraConquista.objects.filter(alvo='pessoa').count(),8)
        self.assertEqual(RegraConquista.objects.filter(alvo='equipe').count(),4)
        self.assertEqual(RegraConquista.objects.values('icone').distinct().count(),8)

    def test_marcos_individuais_pontuais_e_coletivos_no_fluxo_de_encerramento(self):
        for _ in range(5):self.fechar(self.chamado())
        codigos=set(Conquista.objects.filter(usuario=self.tecnico).values_list('regra__codigo',flat=True))
        self.assertEqual(codigos,{'primeira-solucao','missao-cumprida','ritmo-certo'})
        for _ in range(5):self.fechar(self.chamado())
        self.assertTrue(Conquista.objects.filter(equipe=self.equipe,regra__codigo='sintonia-equipe').exists())
        self.assertEqual(Conquista.objects.filter(regra__codigo='missao-cumprida').count(),1)

    def test_atrasos_nao_premiam_pontualidade_e_eventos_anteriores_nao_contam(self):
        RegraConquista.objects.filter(codigo__in=['missao-cumprida','ritmo-certo']).update(inicio_em=timezone.now()+timedelta(days=1))
        for _ in range(5):self.fechar(self.chamado(data_vencimento=timezone.now()-timedelta(hours=1)))
        self.assertFalse(Conquista.objects.filter(regra__codigo__in=['missao-cumprida','ritmo-certo']).exists())
        RegraConquista.objects.filter(codigo__in=['missao-cumprida','ritmo-certo']).update(inicio_em=timezone.now())
        for _ in range(5):self.fechar(self.chamado(data_vencimento=timezone.now()-timedelta(hours=1)))
        self.assertTrue(Conquista.objects.filter(regra__codigo='missao-cumprida').exists())
        self.assertFalse(Conquista.objects.filter(regra__codigo='ritmo-certo').exists())


class MigracaoCatalogoTests(TransactionTestCase):
    def tearDown(self):
        MigrationExecutor(connection).migrate([('helpdesk','0022_ampliar_catalogo_conquistas')])
        super().tearDown()

    def test_migracao_aditiva_idempotente_sem_concessao_e_sem_modificar_regra_existente(self):
        anterior=('helpdesk','0021_construtor_conquistas')
        executor=MigrationExecutor(connection);executor.migrate([anterior])
        historico=executor.loader.project_state([anterior]).apps
        Regra=historico.get_model('helpdesk','RegraConquista')
        catalogo=import_module('helpdesk.migrations.0022_ampliar_catalogo_conquistas')
        # A reversão preserva dados; removemos apenas o catálogo novo desta fixture.
        Regra.objects.filter(codigo__in=[linha[0] for linha in catalogo.CATALOGO]).delete()
        regra,_=Regra.objects.get_or_create(codigo='primeira-solucao',defaults={
            'nome':'Personalizada','descricao':'Preservar','alvo':'pessoa','metrica':'resolucoes','meta':7,'icone':'escudo'})
        Regra.objects.filter(pk=regra.pk).update(meta=7,ativa=False)
        antes=Regra.objects.filter(pk=regra.pk).values().get()
        inicio=timezone.now()
        MigrationExecutor(connection).migrate([('helpdesk','0022_ampliar_catalogo_conquistas')])
        self.assertEqual(RegraConquista.objects.filter(pk=regra.pk).values(*antes).get(),antes)
        novas=RegraConquista.objects.exclude(pk__in=Regra.objects.filter(pk=regra.pk).values('pk')).filter(codigo='missao-cumprida')
        self.assertEqual(novas.count(),1);self.assertGreaterEqual(novas.get().inicio_em,inicio)
        self.assertFalse(Conquista.objects.exists());self.assertFalse(ResolucaoConquista.objects.exists())
        total=RegraConquista.objects.count()
        inicio_original=novas.get().inicio_em
        import_module('helpdesk.migrations.0022_ampliar_catalogo_conquistas').ampliar_catalogo(apps,connection.schema_editor())
        self.assertEqual(RegraConquista.objects.count(),total)
        self.assertEqual(RegraConquista.objects.get(codigo='missao-cumprida').inicio_em,inicio_original)
