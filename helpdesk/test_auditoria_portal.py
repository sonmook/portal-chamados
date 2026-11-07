from datetime import timedelta
from html import unescape
import re
from urllib.parse import parse_qs, urlsplit
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import RegistroAuditoria


class AuditoriaPortalTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_superuser('auditor-demo','audit@example.invalid',None)
        self.tecnico=User.objects.create_user('tecnico-audit',is_staff=True)
        self.cliente=User.objects.create_user('cliente-audit')
        self.r=RegistroAuditoria.objects.create(ator=self.admin,objeto='helpdesk.chamado',objeto_id=81,
            origem='portal',acao='alterado',alteracoes={'status':{'antes':'Aberto','depois':'Em Andamento'}})
        self.url=reverse('listar_auditoria');self.detalhe=reverse('detalhe_auditoria',args=[self.r.pk])
        self.client.force_login(self.admin)

    def test_rotas_protegidas_mesmo_por_id_direto(self):
        self.client.logout()
        for url in (self.url,self.detalhe):self.assertEqual(self.client.get(url).status_code,302)
        for usuario in (self.tecnico,self.cliente):
            self.client.force_login(usuario)
            for url in (self.url,self.detalhe):self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.admin)
        User.objects.filter(pk=self.admin.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.url).status_code,302)

    def test_leitura_lista_detalhe_sem_mutacao_e_post_bloqueado(self):
        antes=list(RegistroAuditoria.objects.values())
        for url in (self.url,self.detalhe):
            r=self.client.get(url);self.assertEqual(r.status_code,200)
            self.assertIn('no-store',r.headers['Cache-Control'])
            self.assertContains(r,'href="'+reverse('central_administracao')+'"')
            self.assertContains(r,'Localização na administração')
            self.assertEqual(self.client.post(url,{'acao':'excluido'}).status_code,405)
        self.assertEqual(list(RegistroAuditoria.objects.values()),antes)
        self.assertEqual(self.client.get(reverse('detalhe_auditoria',args=[999999])).status_code,404)

    def test_central_aponta_para_portal_e_destaca_administracao(self):
        self.assertContains(self.client.get(reverse('central_administracao')),'href="'+self.url+'"')
        for url in (self.url,self.detalhe):
            r=self.client.get(url)
            self.assertNotContains(r,'/admin/helpdesk/registroauditoria/')
            self.assertContains(r,'class="nav-link active" aria-current="page" href="'+reverse('central_administracao')+'"')

    def test_filtros_combinados_data_responsavel_tipo_acao_origem(self):
        self.r.criado_em=timezone.now()-timedelta(days=5);self.r.save(update_fields=['criado_em'])
        RegistroAuditoria.objects.create(objeto='helpdesk.equipe',objeto_id=15,origem='sistema',acao='criado')
        data=timezone.localtime(self.r.criado_em).date().isoformat()
        filtros={'inicio':data,'fim':data,'q':'auditor-demo','objeto':'helpdesk.chamado','acao':'alterado','origem':'portal'}
        r=self.client.get(self.url,filtros)
        self.assertEqual([x.pk for x in r.context['page_obj']],[self.r.pk])
        self.assertContains(r,'Chamado');self.assertContains(r,'Alteração')
        filtros['origem']='admin'
        self.assertFalse(self.client.get(self.url,filtros).context['page_obj'])

    def test_busca_id_e_entradas_numericas_extremas_nao_falham(self):
        for valor in (str(self.r.pk),'81'):
            self.assertIn(self.r.pk,[x.pk for x in self.client.get(self.url,{'q':valor}).context['page_obj']])
        for valor in ('9'*99,'9223372036854775808','١٢٣'):
            self.assertEqual(self.client.get(self.url,{'q':valor}).status_code,200)

    def test_filtros_invalidos_apresentam_erro_sem_lista_ampla(self):
        for filtros in ({'inicio':'nao-data'},{'inicio':'2026-11-08','fim':'2026-11-01'},{'origem':'inventada'}):
            r=self.client.get(self.url,filtros)
            self.assertContains(r,'Revise os filtros informados.')
            self.assertTrue(r.context['form'].errors)
            self.assertFalse(r.context['page_obj'])
        self.assertFalse(self.client.get(self.url,{'objeto':'helpdesk.perfil'}).context['page_obj'])

    def test_paginacao_preserva_filtros_e_ordem_estavel(self):
        for _ in range(25):RegistroAuditoria.objects.create(ator=self.admin,objeto='helpdesk.chamado',objeto_id=81,origem='portal',acao='alterado')
        filtros={'q':'auditor-demo','objeto':'helpdesk.chamado','acao':'alterado','origem':'portal'}
        r=self.client.get(self.url,filtros)
        self.assertEqual(len(r.context['page_obj']),20)
        pks=[x.pk for x in r.context['page_obj']];self.assertEqual(pks,sorted(pks,reverse=True))
        link=next(x for x in re.findall(r'href="([^"]+)"',r.content.decode()) if 'page=2' in x)
        parametros=parse_qs(urlsplit(unescape(link)).query)
        for chave,valor in filtros.items():self.assertEqual(parametros[chave],[valor])
        self.assertEqual(len(self.client.get(self.url+unescape(link)).context['page_obj']),6)

    def test_detalhes_legiveis_mascarados_sem_injetar_html(self):
        self.r.alteracoes={'is_active':{'antes':False,'depois':True},'password':{'alterado':True},
            'motivo':'<script>alert(1)</script>','integrantes':[1,2]}
        self.r.save(update_fields=['alteracoes'])
        r=self.client.get(self.detalhe)
        self.assertContains(r,'Conta ativa');self.assertContains(r,'Não');self.assertContains(r,'Sim')
        self.assertContains(r,'Os valores anterior e novo não foram armazenados.')
        self.assertNotContains(r,'<script>alert(1)</script>')
        self.assertContains(r,'&lt;script&gt;alert(1)&lt;/script&gt;')
        self.r.alteracoes={};self.r.ator=None;self.r.save(update_fields=['alteracoes','ator'])
        r=self.client.get(self.detalhe)
        self.assertContains(r,'Não há detalhes adicionais');self.assertContains(r,'Sistema')
