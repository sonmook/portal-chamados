from io import BytesIO
from pathlib import Path
import tempfile
from unittest.mock import patch

from PIL import Image, PngImagePlugin
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from .forms_perfil import PerfilForm
from .models import Perfil, RegistroAuditoria, Chamado, Comentario


def foto(nome='foto.jpg', size=(800, 600), formato='JPEG'):
    out = BytesIO()
    Image.new('RGB', size, '#245cce').save(out, formato)
    return SimpleUploadedFile(nome, out.getvalue(), content_type='image/jpeg')


class PerfilTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = override_settings(MEDIA_ROOT=self.tmp.name)
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.u = User.objects.create_user('pessoa', email='pessoa@example.invalid', first_name='Nome')
        self.outro = User.objects.create_user('outro')
        self.client.force_login(self.u)
        self.url = reverse('meu_perfil')

    def dados(self, **extra):
        return {'first_name':'Maria', 'last_name':'Silva', 'cargo':'Analista',
                'departamento':'Operações', 'ramal':'204', 'versao':0, **extra}

    def salvar(self, **extra):
        return self.client.post(self.url, self.dados(**extra))

    def test_get_sem_criar_registros_inclui_conta_e_campos_acessiveis(self):
        r = self.client.get(self.url)
        self.assertContains(r, 'Meu Perfil')
        self.assertContains(r, 'pessoa@example.invalid')
        self.assertContains(r, 'for="id_first_name"')
        self.assertFalse(Perfil.objects.exists())

    def test_login_exigido_para_perfil_e_foto(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.get(reverse('foto_perfil', args=[self.u.pk])).status_code, 302)

    def test_campos_permitidos_e_redacao_na_auditoria(self):
        r = self.salvar(usuario_id=self.outro.pk, is_superuser='1', is_staff='1', is_active='',
                        username='alterado', email='novo@example.invalid', password='senha', groups='1')
        self.assertRedirects(r, self.url)
        self.u.refresh_from_db();self.outro.refresh_from_db()
        self.assertEqual(self.u.first_name, 'Maria')
        self.assertEqual(self.u.last_name, 'Silva')
        self.assertFalse(self.u.is_superuser)
        self.assertFalse(self.u.is_staff)
        self.assertTrue(self.u.is_active)
        self.assertEqual(self.u.username, 'pessoa')
        self.assertEqual(self.u.email, 'pessoa@example.invalid')
        self.assertFalse(self.u.has_usable_password())
        self.assertFalse(Perfil.objects.filter(usuario=self.outro).exists())
        audit = RegistroAuditoria.objects.get(objeto='helpdesk.perfil')
        self.assertEqual(audit.ator_id, self.u.pk)
        self.assertEqual(audit.alteracoes['cargo'], {'alterado': True})
        self.assertNotIn('Analista', str(audit.alteracoes))

    def test_upload_convertido_para_png_reduzido_e_privado(self):
        self.salvar(foto=foto())
        p = Perfil.objects.get(usuario=self.u)
        self.assertRegex(p.foto.name, r'^perfis/[a-f0-9]{32}\.png$')
        with Image.open(p.foto.path) as img:
            self.assertEqual(img.format, 'PNG')
            self.assertEqual(img.size, (512,384))
        url = reverse('foto_perfil', args=[self.u.pk])
        self.client.force_login(self.outro)
        r = self.client.get(url)
        self.assertEqual(r.status_code,200)
        self.assertEqual(r['Content-Type'],'image/png')
        self.assertEqual(r['Cache-Control'],'private, no-store')
        self.assertEqual(r['X-Content-Type-Options'],'nosniff')
        self.assertTrue(b''.join(r.streaming_content).startswith(b'\x89PNG'))
        self.assertEqual(self.client.get('/media/'+p.foto.name).status_code,404)

    def test_metadados_removidos(self):
        out=BytesIO();info=PngImagePlugin.PngInfo();info.add_text('Comment','informação privada')
        Image.new('RGB',(50,50)).save(out,'PNG',pnginfo=info)
        self.salvar(foto=SimpleUploadedFile('imagem.png',out.getvalue()))
        with Image.open(Perfil.objects.get(usuario=self.u).foto.path) as img:
            self.assertEqual(img.info,{})

    def test_conteudos_invalidos_recusados_sem_alterar_nome(self):
        for blob in [b'<svg xmlns="http://www.w3.org/2000/svg"/>', b'%PDF-1.7', b'\x89PNG\r\n\x1a\nquebrado']:
            with self.subTest(blob=blob):
                r=self.salvar(foto=SimpleUploadedFile('foto.png',blob))
                self.assertContains(r,'Envie uma imagem JPEG ou PNG válida')
                self.u.refresh_from_db();self.assertEqual(self.u.first_name,'Nome')
        self.assertFalse(Perfil.objects.exists())

    def test_limites_tamanho_dimensoes_e_animacao(self):
        for upload in [SimpleUploadedFile('grande.png',b'x'*(2*1024*1024+1)),
                       foto(size=(4097,1)),foto(size=(2100,2100))]:
            with self.subTest(upload=upload.name):
                self.assertEqual(self.salvar(foto=upload).status_code,200)
                self.assertFalse(Perfil.objects.exists())
        out=BytesIO();im=Image.new('RGB',(16,16),'red')
        im.save(out,'PNG',save_all=True,append_images=[Image.new('RGB',(16,16),'blue')],duration=100)
        self.salvar(foto=SimpleUploadedFile('animada.png',out.getvalue()))
        self.assertFalse(Perfil.objects.exists())

    def test_conflito_edicao_nao_sobrescreve_nem_grava_upload(self):
        self.salvar()
        r=self.salvar(first_name='Velho',foto=foto())
        self.assertEqual(r.status_code,409)
        self.u.refresh_from_db();self.assertEqual(self.u.first_name,'Maria')
        self.assertEqual(list(Path(self.tmp.name).rglob('*.png')),[])

    def test_troca_e_remocao_apagam_arquivo_somente_apos_commit(self):
        self.salvar(foto=foto());p=Perfil.objects.get(usuario=self.u);old=Path(p.foto.path)
        with self.captureOnCommitCallbacks(execute=True):
            self.salvar(versao=1,foto=foto())
            self.assertTrue(old.exists())
        self.assertFalse(old.exists())
        p.refresh_from_db();old=Path(p.foto.path)
        with self.captureOnCommitCallbacks(execute=True):
            self.salvar(versao=2,remover_foto='on')
        self.assertFalse(old.exists());p.refresh_from_db();self.assertFalse(p.foto)

    def test_rollback_preserva_foto_antiga_e_remove_nova(self):
        self.salvar(foto=foto());p=Perfil.objects.get(usuario=self.u);old=Path(p.foto.path)
        with patch('helpdesk.perfis.registrar',side_effect=RuntimeError('falha auditoria')):
            with self.assertRaises(RuntimeError):self.salvar(versao=1,first_name='Não salvar',foto=foto())
        p.refresh_from_db();self.u.refresh_from_db()
        self.assertEqual(p.versao,1);self.assertEqual(self.u.first_name,'Maria')
        self.assertEqual(list(Path(self.tmp.name).rglob('*.png')),[old])

    def test_remover_e_enviar_juntos_recusado(self):
        self.assertContains(self.salvar(foto=foto(),remover_foto='on'),'sem combinar')
        self.assertFalse(Perfil.objects.exists())

    def test_foto_ausente_inativa_e_arquivo_ausente(self):
        url=reverse('foto_perfil',args=[self.u.pk])
        self.assertEqual(self.client.get(url).status_code,404)
        self.salvar(foto=foto());p=Perfil.objects.get(usuario=self.u)
        User.objects.filter(pk=self.u.pk).update(is_active=False)
        self.client.force_login(self.outro);self.assertEqual(self.client.get(url).status_code,404)
        User.objects.filter(pk=self.u.pk).update(is_active=True)
        Path(p.foto.path).unlink();self.assertEqual(self.client.get(url).status_code,404)

    def test_csrf_e_metodos(self):
        c=Client(enforce_csrf_checks=True);c.force_login(self.u)
        self.assertEqual(c.post(self.url,self.dados()).status_code,403)
        self.assertEqual(self.client.delete(self.url).status_code,405)
        self.assertEqual(self.client.post(reverse('foto_perfil',args=[self.u.pk])).status_code,405)

    def test_avatares_no_cabecalho_e_comentarios_com_fallback(self):
        t=Chamado.objects.create(titulo='Teste',descricao='Teste',solicitante=self.u)
        Comentario.objects.create(chamado=t,autor=self.u,texto='Mensagem')
        self.assertNotContains(self.client.get(reverse('detalhes_chamado',args=[t.pk])),reverse('foto_perfil',args=[self.u.pk]))
        self.salvar(foto=foto())
        self.assertContains(self.client.get(reverse('detalhes_chamado',args=[t.pk])),reverse('foto_perfil',args=[self.u.pk]))
