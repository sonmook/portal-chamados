from .test_helpers import integrar_triagem
from datetime import datetime, timezone
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import Chamado, calcular_prazo_util


class AtendimentoTests(TestCase):
    def setUp(self):
        self.cliente = User.objects.create_user(username='cliente')
        self.outro_cliente = User.objects.create_user(username='outro_cliente')
        self.tecnico = User.objects.create_user(username='tecnico', is_staff=True)
        self.outro_tecnico = User.objects.create_user(username='outro_tecnico', is_staff=True)
        integrar_triagem(self.tecnico, self.outro_tecnico)
        self.chamado = Chamado.objects.create(
            titulo='Problema privado', descricao='Descrição privada', solicitante=self.cliente,
        )

    def url(self, nome):
        return reverse(nome, args=[self.chamado.pk])

    def atribuir(self):
        self.chamado.tecnico = self.tecnico
        self.chamado.save()

    def test_fluxo_completo(self):
        self.client.force_login(self.cliente)
        resposta = self.client.post(reverse('novo_chamado'), {
            'titulo': 'Novo problema', 'descricao': 'Detalhes',
            'categoria': 'Software', 'prioridade': 'Normal',
        })
        self.assertEqual(resposta.status_code, 302)
        self.chamado = Chamado.objects.get(titulo='Novo problema')
        self.assertEqual(self.chamado.solicitante, self.cliente)
        self.assertIsNotNone(self.chamado.data_vencimento)
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.post(self.url('assumir_chamado')).status_code, 302)
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.tecnico, self.tecnico)
        self.assertEqual(self.client.post(self.url('detalhes_chamado'), {'texto': 'Resposta'}).status_code, 302)
        self.assertTrue(self.chamado.comentarios.filter(autor=self.tecnico, texto='Resposta').exists())
        self.assertEqual(self.client.post(self.url('fechar_chamado'), {'resolucao': 'Solução aplicada'}).status_code, 302)
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.status, 'Resolvido')
        self.assertEqual(self.chamado.fechado_por, self.tecnico)
        self.assertIsNotNone(self.chamado.data_fechamento)
        self.assertTrue(self.chamado.comentarios.filter(texto__contains='Solução aplicada').exists())
        painel = self.client.get(reverse('dashboard'))
        self.assertEqual(painel.status_code, 200)
        self.assertEqual(painel.context['resolvidos'], 1)
        self.client.force_login(self.cliente)
        self.assertContains(self.client.get(self.url('detalhes_chamado')), 'Solução aplicada')

    def test_cliente_nao_acessa_chamado_alheio(self):
        self.client.force_login(self.outro_cliente)
        self.assertNotContains(self.client.get(reverse('lista_chamados')), self.chamado.titulo)
        self.assertEqual(self.client.get(self.url('detalhes_chamado')).status_code, 404)
        for nome, dados in [('detalhes_chamado', {'texto': 'Intrusão'}),
                            ('atualizar_status', {'status': 'Resolvido'}),
                            ('fechar_chamado', {'resolucao': 'Intrusão'}),
                            ('assumir_chamado', {}), ('devolver_chamado', {})]:
            with self.subTest(nome=nome):
                self.assertEqual(self.client.post(self.url(nome), dados).status_code, 404)
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.status, 'Aberto')
        self.assertIsNone(self.chamado.tecnico)
        self.assertFalse(self.chamado.comentarios.exists())

    def test_cliente_nao_executa_acoes_de_tecnico(self):
        self.client.force_login(self.cliente)
        for nome in ['assumir_chamado', 'devolver_chamado', 'atualizar_status', 'fechar_chamado']:
            with self.subTest(nome=nome):
                self.assertEqual(self.client.post(self.url(nome), {'status': 'Resolvido', 'resolucao': 'Texto'}).status_code, 403)
        self.chamado.refresh_from_db()
        self.assertIsNone(self.chamado.tecnico)
        self.assertEqual(self.chamado.status, 'Aberto')

    def test_outro_tecnico_nao_interage(self):
        self.atribuir()
        self.client.force_login(self.outro_tecnico)
        for nome, dados in [('detalhes_chamado', {'texto': 'Intrusão'}),
                            ('fechar_chamado', {'resolucao': 'Intrusão'}),
                            ('atualizar_status', {'status': 'Em Andamento'}), ('devolver_chamado', {})]:
            with self.subTest(nome=nome):
                self.assertEqual(self.client.post(self.url(nome), dados).status_code, 403)
        self.client.post(self.url('assumir_chamado'))
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.tecnico, self.tecnico)
        self.assertEqual(self.chamado.status, 'Aberto')
        self.assertFalse(self.chamado.comentarios.exists())

    def test_tecnico_precisa_assumir_antes_de_responder_ou_fechar(self):
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.post(self.url('detalhes_chamado'), {'texto': 'Resposta'}).status_code, 403)
        self.assertEqual(self.client.post(self.url('fechar_chamado'), {'resolucao': 'Solução'}).status_code, 403)

    def test_solicitante_pode_responder_ao_tecnico(self):
        self.atribuir()
        self.client.force_login(self.cliente)
        self.assertContains(self.client.get(self.url('detalhes_chamado')), 'Adicionar Resposta')
        self.assertEqual(self.client.post(self.url('detalhes_chamado'), {'texto': 'Mais detalhes'}).status_code, 302)
        self.assertTrue(self.chamado.comentarios.filter(autor=self.cliente).exists())

    def test_encerramento_exige_solucao(self):
        self.atribuir()
        self.client.force_login(self.tecnico)
        for dados in [{}, {'resolucao': ''}, {'resolucao': ' \n\t '}]:
            with self.subTest(dados=dados):
                self.assertEqual(self.client.post(self.url('fechar_chamado'), dados).status_code, 400)
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.status, 'Aberto')
        self.assertIsNone(self.chamado.fechado_por)
        self.assertIsNone(self.chamado.data_fechamento)
        self.assertFalse(self.chamado.comentarios.exists())

    def test_finalizados_nao_aceitam_mutacoes(self):
        self.atribuir()
        self.client.force_login(self.tecnico)
        for status in ['Resolvido', 'Fechado']:
            self.chamado.status = status
            self.chamado.save()
            for nome, dados in [('detalhes_chamado', {'texto': 'Resposta tardia'}),
                                ('fechar_chamado', {'resolucao': 'Nova solução'}),
                                ('atualizar_status', {'status': 'Aberto'}), ('devolver_chamado', {})]:
                with self.subTest(status=status, nome=nome):
                    self.assertEqual(self.client.post(self.url(nome), dados).status_code, 403)
            self.chamado.refresh_from_db()
            self.assertEqual(self.chamado.status, status)
            self.assertEqual(self.chamado.tecnico, self.tecnico)
            self.assertFalse(self.chamado.comentarios.exists())
            self.assertNotContains(self.client.get(self.url('detalhes_chamado')), 'Adicionar Resposta')

    def test_nao_assume_chamado_finalizado(self):
        self.client.force_login(self.tecnico)
        for status in ['Resolvido', 'Fechado']:
            self.chamado.status = status
            self.chamado.save()
            self.client.post(self.url('assumir_chamado'))
            self.chamado.refresh_from_db()
            self.assertIsNone(self.chamado.tecnico)

    def test_status_nao_burla_encerramento(self):
        self.atribuir()
        self.client.force_login(self.tecnico)
        for status in ['Resolvido', 'Fechado', 'Inexistente', '']:
            self.assertEqual(self.client.post(self.url('atualizar_status'), {'status': status}).status_code, 400)
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.status, 'Aberto')
        self.assertEqual(self.client.post(self.url('atualizar_status'), {'status': 'Em Andamento'}).status_code, 302)
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.status, 'Em Andamento')

    def test_acoes_exigem_post(self):
        self.atribuir()
        self.client.force_login(self.tecnico)
        for nome in ['assumir_chamado', 'devolver_chamado', 'atualizar_status', 'fechar_chamado']:
            self.assertEqual(self.client.get(self.url(nome)).status_code, 405)
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.tecnico, self.tecnico)

    def test_botoes_usam_post_e_csrf(self):
        self.client.force_login(self.tecnico)
        resposta = self.client.get(self.url('detalhes_chamado'))
        self.assertContains(resposta, f'action="{self.url("assumir_chamado")}" method="post"')
        self.assertContains(resposta, 'csrfmiddlewaretoken')
        self.atribuir()
        resposta = self.client.get(self.url('detalhes_chamado'))
        self.assertContains(resposta, f'action="{self.url("devolver_chamado")}" method="post"')
        self.client.force_login(self.cliente)
        self.assertNotContains(self.client.get(self.url('detalhes_chamado')), 'Marcar como Resolvido')

    def test_acoes_rejeitam_post_sem_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.tecnico)
        for nome in ['assumir_chamado', 'devolver_chamado', 'atualizar_status', 'fechar_chamado']:
            self.assertEqual(cliente.post(self.url(nome)).status_code, 403)
        self.chamado.refresh_from_db()
        self.assertIsNone(self.chamado.tecnico)
        self.assertEqual(self.chamado.status, 'Aberto')

    def test_devolver_e_reassumir(self):
        self.atribuir()
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.post(self.url('devolver_chamado')).status_code, 302)
        self.chamado.refresh_from_db()
        self.assertIsNone(self.chamado.tecnico)
        self.client.force_login(self.outro_tecnico)
        self.client.post(self.url('assumir_chamado'))
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.tecnico, self.outro_tecnico)

    def test_encerramento_atomico(self):
        self.atribuir()
        self.client.force_login(self.tecnico)
        with patch('helpdesk.views.Chamado.save', side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url('fechar_chamado'), {'resolucao': 'Solução'})
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.status, 'Aberto')
        self.assertFalse(self.chamado.comentarios.exists())

    def test_rotas_exigem_autenticacao(self):
        for nome in ['detalhes_chamado', 'assumir_chamado', 'devolver_chamado', 'atualizar_status', 'fechar_chamado']:
            self.assertEqual(self.client.post(self.url(nome)).status_code, 302)

    def test_cliente_nao_gerencia_usuarios(self):
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(reverse('gerenciar_usuarios')).status_code, 302)

    def test_sla_ignora_fim_de_semana(self):
        inicio = datetime(2026, 10, 30, 16, tzinfo=timezone.utc)
        self.assertEqual(calcular_prazo_util(inicio, 24), datetime(2026, 11, 2, 16, tzinfo=timezone.utc))
