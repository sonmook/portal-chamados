from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from .models import Equipe, IntegranteEquipe, RegistroAuditoria
from .administracao import FERRAMENTAS


class AdministracaoTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_superuser('admin-central','admin@example.invalid',None)
        self.tecnico=User.objects.create_user('tecnico-central',is_staff=True)
        self.cliente=User.objects.create_user('cliente-central')
        IntegranteEquipe.objects.create(usuario=self.tecnico,equipe=Equipe.objects.get(triagem_padrao=True),coordenador=True)
        self.url=reverse('central_administracao')

    def test_central_exige_login_e_administrador_mesmo_por_url_direta(self):
        self.assertRedirects(self.client.get(self.url),reverse('login')+'?next='+self.url)
        for usuario in (self.tecnico,self.cliente):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(self.url).status_code,403)
            r=self.client.get(reverse('lista_chamados'))
            self.assertNotContains(r,'href="'+self.url+'"')

    def test_central_reune_ferramentas_com_destinos_acessiveis_sem_escrever(self):
        self.client.force_login(self.admin)
        antes=RegistroAuditoria.objects.count()
        r=self.client.get(self.url)
        self.assertContains(r,'<h1>Administração</h1>',html=True)
        for ferramenta in FERRAMENTAS:
            url=reverse(ferramenta['url'])
            self.assertContains(r,'href="'+url+'"')
            self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(RegistroAuditoria.objects.count(),antes)
        self.assertEqual(self.client.post(self.url,{}).status_code,405)

    def test_cabecalho_tem_um_unico_acesso_administrativo(self):
        self.client.force_login(self.admin)
        r=self.client.get(reverse('lista_chamados'))
        self.assertContains(r,'href="'+self.url+'"',count=1)
        self.assertNotContains(r,'Gerenciar Usuários')
        self.assertNotContains(r,'Gerenciar Equipes')
        self.assertContains(r,'href="'+reverse('minhas_conquistas')+'"')

    def test_secao_ativa_e_retorno_a_central_nas_telas_de_gestao(self):
        self.client.force_login(self.admin)
        for pagina in ('gerenciar_usuarios','gerenciar_equipes','listar_regras_encaminhamento','gerenciar_conquistas'):
            r=self.client.get(reverse(pagina))
            self.assertTrue(r.context['secao_administrativa'])
            self.assertContains(r,'Localização na administração')
            self.assertContains(r,'class="nav-link active" aria-current="page" href="'+self.url+'"')
            self.assertNotContains(r,'class="nav-link active" aria-current="page" href="'+reverse('minhas_conquistas')+'"')
        r=self.client.get(reverse('minhas_conquistas'))
        self.assertFalse(r.context['secao_administrativa'])
        self.assertNotContains(r,'Localização na administração')

    def test_links_diretos_continuam_protegidos_para_coordenador(self):
        self.client.force_login(self.tecnico)
        for pagina in ('gerenciar_equipes','gerenciar_conquistas','listar_regras_encaminhamento'):
            self.assertEqual(self.client.get(reverse(pagina)).status_code,403)
        self.assertEqual(self.client.get(reverse('minhas_conquistas')).status_code,200)

    def test_auditoria_permanece_somente_consulta(self):
        self.client.force_login(self.admin)
        registro=RegistroAuditoria.objects.create(objeto='helpdesk.equipe',objeto_id=1,acao='alterado')
        url=reverse('admin:helpdesk_registroauditoria_delete',args=[registro.pk])
        self.assertEqual(self.client.post(url,{'post':'yes'}).status_code,403)
        self.assertTrue(RegistroAuditoria.objects.filter(pk=registro.pk).exists())
