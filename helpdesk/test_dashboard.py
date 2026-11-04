from .test_helpers import integrar_triagem
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Chamado, IntegranteEquipe, Equipe


class DashboardTests(TestCase):
    def setUp(self):
        self.agora = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
        self.tecnico = User.objects.create_user('tecnico', first_name='Ana', last_name='Suporte', is_staff=True)
        self.outro = User.objects.create_user('outro', is_staff=True)
        self.sem_resolucoes = User.objects.create_user('sem-resolucoes', is_staff=True)
        self.inativo = User.objects.create_user('inativo', is_staff=True, is_active=False)
        self.cliente = User.objects.create_user('cliente')
        self.alheio = User.objects.create_user('outro-cliente')
        # categoria, status, criação (horas atrás), encerramento, prazo, responsável, solicitante
        fixtures = [
            ('Software', 'Resolvido', 4, 0, -1, self.tecnico, self.cliente),
            ('Hardware', 'Fechado', 8, 2, 3, self.outro, self.alheio),
            ('Rede', 'Resolvido', 24, None, None, None, self.cliente),
            ('Acessos', 'Em Andamento', 2, None, 1, None, self.cliente),
            ('Outros', 'Aberto', 1, None, -2, None, self.cliente),
            ('Software', 'Resolvido', 40 * 24, 39 * 24, 38 * 24, self.tecnico, self.cliente),
            ('Software', 'Resolvido', 8 * 24, 7 * 24, 6 * 24, self.outro, self.cliente),
        ]
        for categoria, status, criacao, fim, prazo, autor, solicitante in fixtures:
            chamado = Chamado.objects.create(titulo=f'{categoria} {status}', descricao='Fixture',
                categoria=categoria, status=status, solicitante=solicitante, fechado_por=autor)
            Chamado.objects.filter(pk=chamado.pk).update(
                data_criacao=self.agora - timedelta(hours=criacao), data_atualizacao=self.agora,
                data_fechamento=self.agora - timedelta(hours=fim) if fim is not None else None,
                data_vencimento=self.agora - timedelta(hours=prazo) if prazo is not None else None,
            )
        integrar_triagem(self.tecnico, self.outro, self.sem_resolucoes, self.inativo)
        self.client.force_login(self.tecnico)

    @patch('helpdesk.views.timezone.now')
    def test_metricas_e_ranking_preservados(self, now):
        now.return_value = self.agora
        contexto = self.client.get(reverse('dashboard')).context
        self.assertEqual([contexto[k] for k in ('total', 'abertos', 'resolvidos', 'vencidos')], [7, 1, 5, 1])
        self.assertEqual(contexto['dados_grafico'], [3, 1, 1, 1, 1])
        self.assertEqual(contexto['dados_sla'], [3, 1])
        self.assertEqual(contexto['sla_sem_dados'], 1)
        self.assertEqual(contexto['tmr_horas'], 16.4)
        self.assertEqual(contexto['minha_produtividade'], 2)
        self.assertEqual(contexto['produtividade_equipe'], [
            {'username': 'Ana Suporte', 'count': 2}, {'username': 'outro', 'count': 2},
            {'username': 'sem-resolucoes', 'count': 0}, {'username': 'inativo', 'count': 0},
        ])

    @patch('helpdesk.views.timezone.now')
    def test_periodos_filtram_todas_as_metricas(self, now):
        now.return_value = self.agora
        for periodo, total, resolvidos, tmr, grafico in [
            ('hoje', 4, 2, 5, [1, 1, 0, 1, 1]),
            ('7dias', 5, 3, 11.3, [1, 1, 1, 1, 1]),
            ('mes', 5, 3, 11.3, [1, 1, 1, 1, 1]),
        ]:
            with self.subTest(periodo=periodo):
                contexto = self.client.get(reverse('dashboard'), {'periodo': periodo}).context
                self.assertEqual(contexto['total'], total)
                self.assertEqual(contexto['resolvidos'], resolvidos)
                self.assertEqual(contexto['tmr_horas'], tmr)
                self.assertEqual(contexto['dados_grafico'], grafico)
                self.assertEqual(contexto['dados_sla'], [1, 1])
                self.assertEqual([p['count'] for p in contexto['produtividade_equipe']], [1, 1, 0, 0])

    def test_cliente_nao_recebe_dados_alheios_nem_metricas_da_equipe(self):
        self.client.force_login(self.cliente)
        contexto = self.client.get(reverse('dashboard')).context
        self.assertEqual(contexto['total'], 6)
        self.assertEqual(contexto['dados_grafico'], [3, 0, 1, 1, 1])
        self.assertEqual(contexto['produtividade_equipe'], [])
        self.assertEqual(contexto['minha_produtividade'], 0)
        self.assertEqual(contexto['tmr_horas'], 0)
        self.assertEqual(contexto['dados_sla'], [0, 0])
        self.assertTrue(all(t.solicitante_id == self.cliente.pk for t in contexto['ultimos_chamados']))

    def test_dashboard_vazio(self):
        Chamado.objects.all().delete()
        contexto = self.client.get(reverse('dashboard')).context
        self.assertEqual(contexto['total'], 0)
        self.assertEqual(contexto['tmr_horas'], 0)
        self.assertEqual(contexto['dados_grafico'], [0] * 5)
        self.assertEqual(contexto['dados_sla'], [0, 0])
        self.assertTrue(all(p['count'] == 0 for p in contexto['produtividade_equipe']))

    def test_numero_de_consultas_independe_da_equipe_e_do_volume(self):
        # O avatar do usuário adiciona uma consulta fixa, sem depender do volume.
        with self.assertNumQueries(7):
            resposta = self.client.get(reverse('dashboard'))
            self.assertEqual(resposta.status_code, 200)
        User.objects.bulk_create([User(username=f'extra-{i}', is_staff=True) for i in range(20)])
        IntegranteEquipe.objects.bulk_create([IntegranteEquipe(equipe=Equipe.objects.get(triagem_padrao=True), usuario=u)
            for u in User.objects.filter(username__startswith='extra-')])
        Chamado.objects.bulk_create([
            Chamado(titulo=f'Volume {i}', descricao='Fixture', solicitante=self.alheio,
                    status='Resolvido', fechado_por=self.outro, data_fechamento=self.agora)
            for i in range(40)
        ])
        with self.assertNumQueries(7):
            resposta = self.client.get(reverse('dashboard'))
            self.assertEqual(len(resposta.context['produtividade_equipe']), 24)
            self.assertEqual(len(resposta.context['ultimos_chamados']), 5)
