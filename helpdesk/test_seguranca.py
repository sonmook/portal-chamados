import tempfile

from allauth.account.adapter import get_adapter
from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from .forms import ChamadoForm, ComentarioForm, ResolucaoForm
from .models import Chamado, Comentario
from .validators import MAX_ATTACHMENT_SIZE, validar_anexo
from .test_helpers import integrar_triagem


class SegurancaTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        configuracao = override_settings(MEDIA_ROOT=self.media.name)
        configuracao.enable()
        self.addCleanup(configuracao.disable)
        self.dono = User.objects.create_user(username='dono', password='Valid-test-password-91')
        self.outro = User.objects.create_user(username='outro')
        self.admin = User.objects.create_user(username='admin', is_staff=True, is_superuser=True)
        integrar_triagem(self.admin)
        self.chamado = Chamado.objects.create(titulo='Privado', descricao='Dados', solicitante=self.dono)

    def pdf(self, name='arquivo.pdf'):
        return SimpleUploadedFile(name, b'%PDF-1.7\nconteudo de teste', content_type='application/pdf')

    def salvar_anexo(self):
        self.chamado.anexo.save('arquivo.pdf', self.pdf())
        return reverse('baixar_anexo', args=[self.chamado.pk])

    def test_download_exige_login(self):
        self.assertEqual(self.client.get(self.salvar_anexo()).status_code, 302)

    def test_download_privado_e_forcado(self):
        url = self.salvar_anexo()
        for usuario in [self.dono, self.admin]:
            self.client.force_login(usuario)
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 200)
            self.assertTrue(resposta['Content-Disposition'].startswith('attachment;'))
            self.assertEqual(resposta['Content-Type'], 'application/octet-stream')
            self.assertEqual(resposta['X-Content-Type-Options'], 'nosniff')
            self.assertEqual(resposta['Cache-Control'], 'private, no-store')
            self.assertEqual(b''.join(resposta.streaming_content), b'%PDF-1.7\nconteudo de teste')
        self.client.force_login(self.outro)
        self.assertEqual(self.client.get(url).status_code, 404)

    @override_settings(DEBUG=True)
    def test_media_nao_e_publica_nem_em_debug(self):
        self.salvar_anexo()
        self.assertEqual(self.client.get(self.chamado.anexo.url).status_code, 404)

    def test_comentario_nao_pode_ser_baixado_por_outro_chamado(self):
        comentario = Comentario.objects.create(chamado=self.chamado, autor=self.dono, texto='Resposta', anexo=self.pdf())
        outro = Chamado.objects.create(titulo='Outro', descricao='Dados', solicitante=self.outro)
        self.client.force_login(self.outro)
        url = reverse('baixar_anexo_comentario', args=[outro.pk, comentario.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.dono)
        resposta = self.client.get(reverse('baixar_anexo_comentario', args=[self.chamado.pk, comentario.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(b''.join(resposta.streaming_content), b'%PDF-1.7\nconteudo de teste')

    def test_anexo_ausente_retorna_404(self):
        self.client.force_login(self.dono)
        url = reverse('baixar_anexo', args=[self.chamado.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.chamado.anexo = 'nao-existe.pdf'
        self.chamado.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_links_privados_nos_detalhes(self):
        url = self.salvar_anexo()
        comentario = Comentario.objects.create(chamado=self.chamado, autor=self.dono, texto='Resposta', anexo=self.pdf())
        self.client.force_login(self.dono)
        resposta = self.client.get(reverse('detalhes_chamado', args=[self.chamado.pk]))
        self.assertContains(resposta, url)
        self.assertContains(resposta, reverse('baixar_anexo_comentario', args=[self.chamado.pk, comentario.pk]))
        self.assertNotContains(resposta, '/media/')

    def test_rejeita_html_e_extensao_disfarcada(self):
        for nome in ['pagina.html', 'pagina.svg', 'pagina.pdf', 'pagina.png', 'pagina.jpg']:
            with self.subTest(nome=nome), self.assertRaises(ValidationError):
                validar_anexo(SimpleUploadedFile(nome, b'<html>invalido</html>'))

    def test_limite_tamanho_e_posicao_stream(self):
        arquivo = self.pdf()
        arquivo.seek(3)
        validar_anexo(arquivo)
        self.assertEqual(arquivo.tell(), 3)
        arquivo.size = MAX_ATTACHMENT_SIZE + 1
        with self.assertRaises(ValidationError):
            validar_anexo(arquivo)

    def test_tres_formularios_validam_upload(self):
        for classe, dados, campo in [
            (ChamadoForm, {'titulo':'Teste','descricao':'Dados','prioridade':'Normal','categoria':'Software'}, 'anexo'),
            (ComentarioForm, {'texto':'Resposta'}, 'anexo'),
            (ResolucaoForm, {'resolucao':'Resolvido'}, 'anexo_resolucao'),
        ]:
            with self.subTest(classe=classe):
                form = classe(dados, {campo: SimpleUploadedFile('invalido.pdf', b'<html>')})
                self.assertFalse(form.is_valid())
                self.assertIn(campo, form.errors)
                self.assertTrue(classe(dados, {campo:self.pdf()}).is_valid())

    def test_resolucao_invalida_nao_encerra_nem_grava_comentario(self):
        self.chamado.tecnico = self.admin
        self.chamado.save()
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('fechar_chamado', args=[self.chamado.pk]), {
            'resolucao':'Resolvido', 'anexo_resolucao':SimpleUploadedFile('x.html', b'<html>'),
        })
        self.assertEqual(resposta.status_code, 400)
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.status, 'Aberto')
        self.assertFalse(self.chamado.comentarios.exists())

    def test_cadastro_publico_fechado_get_e_post(self):
        dados = {'email':'publico@example.invalid','password1':'Valid-test-password-91','password2':'Valid-test-password-91'}
        for metodo in [self.client.get, self.client.post]:
            resposta = metodo(reverse('account_signup'), dados)
            self.assertEqual(resposta.status_code, 200)
            self.assertTemplateUsed(resposta, 'account/signup_closed.html')
        self.assertFalse(User.objects.filter(email=dados['email']).exists())

    def test_adapters_fecham_cadastro_local_e_social(self):
        request = RequestFactory().get('/')
        self.assertFalse(get_adapter(request).is_open_for_signup(request))
        self.assertFalse(get_social_adapter(request).is_open_for_signup(request, None))

    def test_login_local_existente_continua_funcionando(self):
        self.assertTrue(self.client.login(username='dono', password='Valid-test-password-91'))
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_administrador_pode_criar_conta(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('criar_usuario'), {
            'username':'novo', 'email':'novo@example.invalid', 'password1':'Valid-test-password-91',
            'password2':'Valid-test-password-91', 'nivel_acesso':'cliente',
        })
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(User.objects.filter(username='novo').exists())

    def test_alternancia_exige_post_csrf_e_admin(self):
        url = reverse('alternar_status_usuario', args=[self.dono.pk])
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        self.assertEqual(cliente.get(url).status_code, 405)
        self.assertEqual(cliente.post(url).status_code, 403)
        self.dono.refresh_from_db()
        self.assertTrue(self.dono.is_active)
        cliente.get(reverse('gerenciar_usuarios'))
        token = cliente.cookies['csrftoken'].value
        self.assertEqual(cliente.post(url, HTTP_X_CSRFTOKEN=token).status_code, 302)
        self.dono.refresh_from_db()
        self.assertFalse(self.dono.is_active)
        self.client.force_login(self.outro)
        self.client.post(url)
        self.dono.refresh_from_db()
        self.assertFalse(self.dono.is_active)
