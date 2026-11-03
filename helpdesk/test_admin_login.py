from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import JanelaLogin


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AdminLoginTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('gestor', password='test-only-password')
        self.url = reverse('admin:login')
        self.dados = {'username': 'gestor', 'password': 'errada', 'next': reverse('admin:index')}

    @patch('helpdesk.login.time.time', return_value=1800000001)
    def test_limite_admin_e_expiracao(self, clock):
        for _ in range(10):
            self.assertEqual(self.client.post(self.url, self.dados).status_code, 200)
        # Uma senha válida também não contorna o limite.
        resposta = self.client.post(self.url, {**self.dados, 'password': 'test-only-password'})
        self.assertEqual(resposta.status_code, 429)
        self.assertEqual(int(resposta['Retry-After']), 899)
        self.assertIn('no-store', resposta['Cache-Control'])
        self.assertNotIn('_auth_user_id', self.client.session)
        clock.return_value += 900
        self.assertEqual(self.client.post(self.url, self.dados).status_code, 200)

    @patch('helpdesk.login.time.time', return_value=1800000001)
    def test_alternar_portal_admin_nao_renova_cota(self, clock):
        for _ in range(5):
            self.client.post(reverse('login'), self.dados)
            self.client.post(self.url, self.dados)
        self.assertEqual(self.client.post(self.url, self.dados).status_code, 429)
        self.assertEqual(self.client.post(reverse('login'), self.dados).status_code, 429)

    @patch('helpdesk.login.time.time', return_value=1800000001)
    def test_limite_ip_compartilhado_com_outros_clientes_e_contas(self, clock):
        for i in range(50):
            url = self.url if i % 2 else reverse('login')
            self.assertEqual(self.client.post(url, {'username': f'inexistente-{i}', 'password': 'x'}).status_code, 200)
        outro = Client()
        resposta = outro.post(self.url, self.dados, HTTP_X_FORWARDED_FOR='192.0.2.1', HTTP_X_REAL_IP='192.0.2.2')
        self.assertEqual(resposta.status_code, 429)
        self.assertEqual(outro.post(self.url, self.dados, REMOTE_ADDR='192.0.2.3').status_code, 200)

    @patch('helpdesk.login.time.time', return_value=1800000001)
    def test_normalizacao_da_conta_para_contagem(self, clock):
        for _ in range(10):
            self.client.post(self.url, {**self.dados, 'username': ' GESTOR '})
        self.assertEqual(self.client.post(self.url, self.dados).status_code, 429)

    def test_csrf_antes_do_limitador_e_get_sem_contagem(self):
        cliente = Client(enforce_csrf_checks=True)
        self.assertEqual(cliente.get(self.url).status_code, 200)
        self.assertEqual(cliente.post(self.url, self.dados).status_code, 403)
        self.assertEqual(JanelaLogin.objects.count(), 0)
        token = cliente.cookies['csrftoken'].value
        self.assertEqual(cliente.post(self.url, {**self.dados, 'csrfmiddlewaretoken': token}).status_code, 200)
        self.assertEqual(JanelaLogin.objects.count(), 2)

    def test_login_admin_e_registros_preservados(self):
        resposta = self.client.post(self.url, {**self.dados, 'password': 'test-only-password'})
        self.assertRedirects(resposta, reverse('admin:index'))
        self.assertEqual(self.client.get(reverse('admin:auth_user_changelist')).status_code, 200)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_admin_continua_recusando_cliente_e_conta_inativa(self):
        cliente = User.objects.create_user('cliente', password='test-only-password')
        self.admin.is_active = False
        self.admin.save()
        for user in (cliente, self.admin):
            with self.subTest(user=user.username):
                resposta = self.client.post(self.url, {'username': user.username, 'password': 'test-only-password'})
                self.assertEqual(resposta.status_code, 200)
                self.assertNotIn('_auth_user_id', self.client.session)
