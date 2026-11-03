from .test_helpers import integrar_triagem
from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from .admin import UsuarioProtegidoForm
from .forms import EditarUsuarioForm, NovoUsuarioForm
from .models import Chamado, JanelaLogin


class AutenticacaoTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='gestor', is_staff=True, is_superuser=True)

    def dados(self, **extras):
        dados = {'username':'gestor','email':'gestor@example.invalid','nivel_acesso':'admin','is_active':'on'}
        dados.update(extras)
        return dados

    def test_senhas_fracas_rejeitadas(self):
        for senha in ['1', 'password', 'gestor']:
            form = NovoUsuarioForm(self.dados(password1=senha, password2=senha))
            self.assertFalse(form.is_valid())
            self.assertIn('password2', form.errors)

    def test_senha_forte_aceita(self):
        form = NovoUsuarioForm(self.dados(username='novo', password1='Secure-test-219!pass', password2='Secure-test-219!pass'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.save().check_password('Secure-test-219!pass'))

    def test_ultimo_admin_nao_perde_acesso(self):
        for dados in [self.dados(nivel_acesso='cliente'), self.dados(is_active='')]:
            form = EditarUsuarioForm(dados, instance=User.objects.get(pk=self.admin.pk))
            self.assertFalse(form.is_valid())
            self.assertIn('administrador ativo', str(form.errors))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser and self.admin.is_active)

    def test_rebaixamento_permitido_com_outro_admin(self):
        User.objects.create_user(username='reserva', is_staff=True, is_superuser=True)
        form = EditarUsuarioForm(self.dados(nivel_acesso='cliente'), instance=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.save().is_superuser)

    def test_view_exibe_erro_e_preserva_admin(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('editar_usuario', args=[self.admin.pk]), self.dados(nivel_acesso='cliente'))
        self.assertContains(resposta, 'administrador ativo')
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)

    def test_admin_django_nao_remove_ultimo_admin(self):
        form = UsuarioProtegidoForm({'username':'gestor', 'is_active':'on', 'is_staff':'on'}, instance=self.admin)
        self.assertFalse(form.is_valid())
        self.assertIn('administrador ativo', str(form.errors))

    def test_admin_django_nao_exclui_admin_ativo(self):
        request = RequestFactory().get('/admin/')
        request.user = self.admin
        modeladmin = admin.site._registry[User]
        self.assertFalse(modeladmin.has_delete_permission(request, self.admin))
        with self.assertRaises(PermissionDenied):
            modeladmin.delete_queryset(request, User.objects.filter(pk=self.admin.pk))
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    @patch('helpdesk.login.time.time', return_value=1800000001)
    def test_limite_conta_ip_e_expiracao(self, clock):
        dados = {'username':'inexistente','password':'errada'}
        for _ in range(10):
            self.assertEqual(self.client.post(reverse('login'), dados).status_code, 200)
        resposta = self.client.post(reverse('login'), dados)
        self.assertEqual(resposta.status_code, 429)
        self.assertGreater(int(resposta['Retry-After']), 0)
        self.assertFalse(JanelaLogin.objects.filter(chave__contains='inexistente').exists())
        clock.return_value += 900
        self.assertEqual(self.client.post(reverse('login'), dados).status_code, 200)

    @patch('helpdesk.login.time.time', return_value=1800000001)
    def test_limite_ip_nao_burlado_trocando_conta(self, clock):
        with patch('helpdesk.login.LoginView.post') as autenticar:
            from django.http import HttpResponse
            autenticar.return_value = HttpResponse('test')
            for i in range(50):
                self.assertEqual(self.client.post(reverse('login'), {'username':str(i)}).status_code, 200)
            self.assertEqual(self.client.post(reverse('login'), {'username':'outra'}).status_code, 429)

    @patch('helpdesk.login.time.time', return_value=1800000001)
    def test_cliente_nao_forja_ip_e_contadores_compartilhados(self, clock):
        dados = {'username':'inexistente', 'password':'x'}
        with patch('helpdesk.login.LoginView.post') as autenticar:
            from django.http import HttpResponse
            autenticar.return_value = HttpResponse('test')
            for _ in range(10):
                self.client.post(reverse('login'), dados)
            outro = Client()
            self.assertEqual(outro.post(reverse('login'), dados, HTTP_X_FORWARDED_FOR='1.2.3.4').status_code, 429)
            self.assertEqual(outro.post(reverse('login'), dados, REMOTE_ADDR='192.0.2.1').status_code, 200)

    def test_csrf_rejeitado_antes_de_contar(self):
        cliente = Client(enforce_csrf_checks=True)
        self.assertEqual(cliente.post(reverse('login'), {'username':'x'}).status_code, 403)
        self.assertEqual(JanelaLogin.objects.count(), 0)

    def test_login_funciona_sem_google(self):
        self.admin.set_password('Secure-test-219!pass');self.admin.save()
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)
        resposta = self.client.post(reverse('login'), {'username':'gestor','password':'Secure-test-219!pass'})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.client.get('/').status_code, 200)


class MetricasTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tecnico', is_staff=True)
        integrar_triagem(self.user)
        self.client.force_login(self.user)
        self.agora = timezone.now()

    def chamado(self, status, prazo, fechamento):
        return Chamado.objects.create(titulo='Teste',descricao='Dados',solicitante=self.user,
            status=status, data_vencimento=prazo, data_fechamento=fechamento)

    def test_sla_historico_e_igualdade(self):
        for status in ['Resolvido', 'Fechado']:
            prazo = self.agora - timedelta(days=1)
            self.chamado(status, prazo, prazo-timedelta(hours=1))
            self.chamado(status, prazo, prazo)
            self.chamado(status, prazo, prazo+timedelta(hours=1))
        contexto = self.client.get(reverse('dashboard')).context
        self.assertEqual(contexto['dados_sla'], [4,2])
        self.assertEqual(contexto['resolvidos'], 6)
        self.assertEqual(contexto['vencidos'], 0)

    def test_terminais_nao_estouram_sla(self):
        for status in ['Resolvido','Fechado']:
            chamado = self.chamado(status,self.agora-timedelta(days=1),self.agora)
            self.assertFalse(chamado.sla_estourado)
        aberto = self.chamado('Aberto', self.agora-timedelta(days=1),None)
        self.assertTrue(aberto.sla_estourado)
        self.assertEqual(self.client.get(reverse('dashboard')).context['vencidos'], 1)

    def test_sem_data_nao_inventa_classificacao_sla_e_tmr_tem_fallback(self):
        chamado = self.chamado('Resolvido', self.agora-timedelta(hours=1),None)
        Chamado.objects.filter(pk=chamado.pk).update(data_criacao=self.agora-timedelta(hours=4),data_atualizacao=self.agora)
        contexto = self.client.get(reverse('dashboard')).context
        self.assertEqual(contexto['dados_sla'], [0,0])
        self.assertEqual(contexto['tmr_horas'],4)
