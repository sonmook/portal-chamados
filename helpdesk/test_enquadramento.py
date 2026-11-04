from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.test import TestCase

from .test_perfil import PerfilFixtureMixin
from .models import Perfil


class EnquadramentoTests(PerfilFixtureMixin, TestCase):
    # Reutiliza a montagem de usuários e armazenamento temporário, sem duplicar testes.
    def test_recorte_horizontal_e_reajuste_sem_perder_fonte(self):
        img=Image.new('RGB',(300,100),'green');draw=ImageDraw.Draw(img)
        draw.rectangle((0,0,99,99),fill='red');draw.rectangle((200,0,299,99),fill='blue')
        out=BytesIO();img.save(out,'PNG')
        self.salvar(foto=SimpleUploadedFile('faixas.png',out.getvalue()),foto_x=0,foto_y=50,foto_zoom=100)
        perfil=Perfil.objects.get(usuario=self.u);arquivo=perfil.foto.name;original=Path(perfil.foto.path).read_bytes()
        url=reverse('foto_perfil',args=[self.u.pk])
        def pixel():
            r=self.client.get(url)
            with Image.open(BytesIO(b''.join(r.streaming_content))) as avatar:
                self.assertEqual(avatar.size,(512,512))
                return avatar.getpixel((256,256))
        self.assertEqual(pixel(),(255,0,0))
        self.salvar(versao=1,foto_x=100,foto_y=50,foto_zoom=100)
        self.assertEqual(pixel(),(0,0,255))
        perfil.refresh_from_db();self.assertEqual(perfil.foto.name,arquivo)
        self.assertEqual(Path(perfil.foto.path).read_bytes(),original)
        self.assertEqual(len(list(Path(self.tmp.name).rglob('*.png'))),1)
        self.client.force_login(self.outro)
        self.assertEqual(pixel(),(0,0,255))

    def test_zoom_e_posicao_vertical(self):
        img=Image.new('RGB',(100,100),'red');draw=ImageDraw.Draw(img);draw.rectangle((0,50,99,99),fill='blue')
        out=BytesIO();img.save(out,'PNG')
        self.salvar(foto=SimpleUploadedFile('imagem.png',out.getvalue()),foto_x=50,foto_y=100,foto_zoom=200)
        r=self.client.get(reverse('foto_perfil',args=[self.u.pk]))
        with Image.open(BytesIO(b''.join(r.streaming_content))) as avatar:
            self.assertEqual(avatar.getpixel((256,256)),(0,0,255))
        p=Perfil.objects.get(usuario=self.u)
        self.assertEqual((p.foto_x,p.foto_y,p.foto_zoom),(50,100,200))

    def test_parametros_invalidos_nao_gravam_nada(self):
        for campos in [{'foto_x':-1},{'foto_x':101},{'foto_y':101},{'foto_y':'nan'},
                       {'foto_zoom':99},{'foto_zoom':301},{'foto_zoom':'200.5'}]:
            with self.subTest(campos=campos):
                self.assertEqual(self.salvar(**campos).status_code,200)
                self.assertFalse(Perfil.objects.exists())

    def test_fonte_somente_do_usuario_autenticado(self):
        from .test_perfil import foto
        self.salvar(foto=foto(),foto_zoom=150)
        url=reverse('foto_base_perfil')
        r=self.client.get(url)
        with Image.open(BytesIO(b''.join(r.streaming_content))) as source:self.assertEqual(source.size,(512,384))
        self.client.force_login(self.outro)
        self.assertEqual(self.client.get(url,{'usuario_id':self.u.pk}).status_code,404)
        self.client.logout();self.assertEqual(self.client.get(url).status_code,302)

    def test_formulario_antigo_preserva_enquadramento(self):
        self.salvar(foto_x=20,foto_y=80,foto_zoom=180)
        self.salvar(versao=1,cargo='Novo cargo')
        p=Perfil.objects.get(usuario=self.u)
        self.assertEqual((p.foto_x,p.foto_y,p.foto_zoom),(20,80,180))
        r=self.salvar(versao=1,foto_x=90)
        self.assertEqual(r.status_code,409)
        p.refresh_from_db();self.assertEqual(p.foto_x,20)

    def test_remocao_restaura_enquadramento_padrao(self):
        self.salvar(foto_x=20,foto_y=80,foto_zoom=180)
        self.salvar(versao=1,remover_foto='on')
        p=Perfil.objects.get(usuario=self.u)
        self.assertEqual((p.foto_x,p.foto_y,p.foto_zoom),(50,50,100))

    def test_restricao_do_banco_para_dados_fora_do_formulario(self):
        p=Perfil.objects.create(usuario=self.u)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Perfil.objects.filter(pk=p.pk).update(foto_zoom=0)


