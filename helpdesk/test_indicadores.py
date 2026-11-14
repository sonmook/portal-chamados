from datetime import datetime, timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Chamado, Comentario, Equipe, IntegranteEquipe


class IndicadoresTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('gestor', password=None)
        self.tecnico = User.objects.create_user('tecnico', is_staff=True)
        self.equipe = Equipe.objects.get(triagem_padrao=True)
        IntegranteEquipe.objects.create(usuario=self.tecnico, equipe=self.equipe, coordenador=True)
        self.url = reverse('indicadores_administracao')
        self.client.force_login(self.admin)

    def chamado(self, status='Resolvido', equipe=None, fechamento=None):
        chamado = Chamado.objects.create(titulo='Teste', descricao='Detalhes', solicitante=self.admin,
            equipe=equipe or self.equipe, status=status, fechado_por=self.tecnico)
        fechamento = fechamento or timezone.now()
        Chamado.objects.filter(pk=chamado.pk).update(data_criacao=fechamento-timedelta(days=20),
            data_fechamento=fechamento, data_vencimento=fechamento+timedelta(hours=1))
        return chamado

    def test_apenas_administradores_por_url_direta(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        for usuario in (self.tecnico, User.objects.create_user('cliente')):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.admin.is_active = False
        self.admin.save()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_resolucao_unica_sem_multiplicar_comentarios_ou_integrantes(self):
        chamado = self.chamado()
        self.chamado(status='Fechado')
        self.chamado(status='Aberto')
        IntegranteEquipe.objects.create(usuario=self.admin, equipe=self.equipe)
        for i in range(3):
            Comentario.objects.create(chamado=chamado, autor=self.admin, texto=str(i))
        r = self.client.get(self.url, {'periodo': 'hoje'})
        self.assertEqual(r.context['resumo']['resolvidos'], 2)
        self.assertEqual(r.context['resumo']['criados'], 0)
        self.assertEqual(r.context['resumo']['ativos'], 1)
        self.assertEqual(r.context['pagina'].paginator.count, 2)
        self.assertEqual(sum(l['total'] for l in r.context['equipes']), 2)
        self.assertEqual(r.context['resumo']['tmr_horas'], 480)

    def test_limites_inclusivos_e_filtro_por_equipe_inativa(self):
        equipe = Equipe.objects.create(nome='Histórica', ativa=False)
        for instante in (datetime(2025, 3, 1), datetime(2025, 3, 2, 23, 59, 59), datetime(2025, 3, 3)):
            self.chamado(equipe=equipe, fechamento=timezone.make_aware(instante))
        self.chamado(fechamento=timezone.make_aware(datetime(2025, 3, 1)))
        r = self.client.get(self.url, {'periodo': 'personalizado', 'inicio': '2025-03-01', 'fim': '2025-03-02', 'equipe': equipe.pk})
        self.assertEqual(r.context['resumo']['resolvidos'], 2)
        self.assertEqual(len(r.context['equipes']), 1)
        self.assertContains(r, 'Inativa')

    def test_dados_ausentes_sla_e_tempo_invalido(self):
        chamado = self.chamado()
        outro = self.chamado()
        Chamado.objects.filter(pk=chamado.pk).update(data_fechamento=None)
        Chamado.objects.filter(pk=outro.pk).update(data_vencimento=None, data_criacao=timezone.now()+timedelta(days=1))
        r = self.client.get(self.url, {'periodo': 'sempre'})
        self.assertEqual(r.context['resumo']['resolvidos'], 2)
        self.assertEqual(r.context['resumo']['sem_sla'], 2)
        self.assertIsNone(r.context['resumo']['tmr_horas'])
        self.assertEqual(self.client.get(self.url, {'periodo': 'hoje'}).context['resumo']['resolvidos'], 1)

    def test_filtros_invalidos_nao_exibem_resultados_enganosos(self):
        for dados in ({'periodo': 'invalido'}, {'periodo': 'personalizado'},
                      {'periodo': 'personalizado', 'inicio': '2025-03-03', 'fim': '2025-03-01'},
                      {'periodo': 'personalizado', 'inicio': '2025-02-30', 'fim': '2025-03-01'},
                      {'equipe': '99999999'}):
            r = self.client.get(self.url, dados)
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.context['form'].errors)
            self.assertNotIn('resumo', r.context)

    def test_periodos_predefinidos_e_sla_fora_do_prazo(self):
        from unittest.mock import patch
        agora = timezone.make_aware(datetime(2025, 3, 15, 12))
        for dias in (0, 6, 7, 14, 15):
            chamado = self.chamado(fechamento=agora-timedelta(days=dias))
            Chamado.objects.filter(pk=chamado.pk).update(data_vencimento=agora-timedelta(days=dias, hours=1))
        with patch('helpdesk.indicadores.timezone.localdate', return_value=agora.date()):
            for periodo, esperado in (('hoje', 1), ('7dias', 2), ('mes', 4), ('sempre', 5)):
                r = self.client.get(self.url, {'periodo': periodo})
                self.assertEqual(r.context['resumo']['resolvidos'], esperado)
                self.assertEqual(r.context['resumo']['fora_sla'], esperado)
                self.assertEqual(r.context['resumo']['dentro_sla'], 0)

    def test_paginacao_preserva_filtros_e_ordem(self):
        for _ in range(26):
            self.chamado()
        r = self.client.get(self.url, {'periodo': 'sempre', 'equipe': self.equipe.pk})
        self.assertEqual(len(r.context['pagina']), 25)
        self.assertContains(r, 'periodo=sempre')
        segunda = self.client.get(self.url, {'periodo': 'sempre', 'page': 2})
        self.assertEqual(len(segunda.context['pagina']), 1)
        self.assertTrue(set(c.pk for c in r.context['pagina']).isdisjoint(c.pk for c in segunda.context['pagina']))
