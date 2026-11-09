from unittest.mock import patch
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse
from .models import Chamado, Comentario, Equipe, IntegranteEquipe, Notificacao, RegistroAuditoria, RespostaPronta


class RespostasProntasTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_superuser('respostas-admin','admin@example.invalid',None)
        self.tec=User.objects.create_user('respostas-tecnico',is_staff=True)
        self.outro=User.objects.create_user('respostas-outro',is_staff=True)
        self.cliente=User.objects.create_user('respostas-cliente')
        self.equipe=Equipe.objects.get(triagem_padrao=True)
        IntegranteEquipe.objects.create(equipe=self.equipe,usuario=self.tec)
        IntegranteEquipe.objects.create(equipe=self.equipe,usuario=self.outro,coordenador=True)
        self.chamado=Chamado.objects.create(titulo='Fixture modelos',descricao='Descrição',solicitante=self.cliente,tecnico=self.tec,equipe=self.equipe)
        self.modelo=RespostaPronta.objects.get(nome='Atendimento iniciado')
        self.lista=reverse('gerenciar_respostas_prontas');self.nova=reverse('criar_resposta_pronta')
        self.editar=reverse('editar_resposta_pronta',args=[self.modelo.pk])
        self.url=reverse('detalhes_chamado',args=[self.chamado.pk])
        self.obter=reverse('obter_resposta_pronta',args=[self.chamado.pk,self.modelo.pk])
        self.client.force_login(self.admin)

    def dados(self,**extra):
        self.modelo.refresh_from_db()
        dados={'nome':self.modelo.nome,'texto':self.modelo.texto,'ativa':'on','versao_atual':self.modelo.versao}
        dados.update(extra);return dados

    def test_catalogo_inicial_e_link_na_administracao(self):
        self.assertEqual(RespostaPronta.objects.count(),3)
        self.assertContains(self.client.get(reverse('central_administracao')),'href="'+self.lista+'"')
        r=self.client.get(self.lista)
        self.assertContains(r,'Atendimento iniciado');self.assertContains(r,'Aguardando validação')
        self.assertContains(r,'Localização na administração')
        self.assertContains(r,'class="nav-link active" aria-current="page" href="'+reverse('central_administracao')+'"')

    def test_gestao_exige_admin_inclusive_post_por_url(self):
        self.assertEqual(Client().get(self.lista).status_code,302)
        for user in (self.tec,self.outro,self.cliente):
            self.client.force_login(user)
            for url in (self.lista,self.nova,self.editar):
                self.assertEqual(self.client.get(url).status_code,403)
                self.assertEqual(self.client.post(url,self.dados()).status_code,405 if url==self.lista else 403)

    def test_criar_editar_desativar_e_auditar_sem_copiar_texto(self):
        r=self.client.post(self.nova,{'nome':'Orientação inicial','texto':'Texto de modelo de teste','ativa':'on','versao_atual':0})
        self.assertRedirects(r,self.lista)
        nova=RespostaPronta.objects.get(nome='Orientação inicial')
        self.assertTrue(nova.ativa)
        audit=RegistroAuditoria.objects.get(objeto='helpdesk.respostapronta',objeto_id=nova.pk)
        self.assertEqual(audit.ator_id,self.admin.pk);self.assertEqual(audit.origem,'portal')
        self.assertNotIn('Texto de modelo',str(audit.alteracoes))
        r=self.client.post(self.editar,self.dados(texto='Modelo revisado',ativa=''))
        self.assertRedirects(r,self.lista)
        self.modelo.refresh_from_db()
        self.assertFalse(self.modelo.ativa);self.assertEqual(self.modelo.versao,1)
        a=RegistroAuditoria.objects.filter(objeto='helpdesk.respostapronta',objeto_id=self.modelo.pk).latest('pk')
        self.assertEqual(a.alteracoes['ativa'],{'antes':True,'depois':False})

    def test_validacao_de_nome_texto_limites_e_duplicacao(self):
        for extra in ({'nome':'  '},{'texto':' '},{'nome':'n'*101},{'texto':'x'*4001},{'nome':'Aguardando validação'}):
            r=self.client.post(self.editar,self.dados(**extra))
            self.assertEqual(r.status_code,200);self.assertTrue(r.context['form'].errors)
        self.modelo.refresh_from_db();self.assertEqual(self.modelo.versao,0)

    def test_formulario_desatualizado_nao_sobrescreve(self):
        dados=self.dados(texto='Primeira edição')
        self.assertEqual(self.client.post(self.editar,dados).status_code,302)
        dados['texto']='Edição antiga'
        self.assertEqual(self.client.post(self.editar,dados).status_code,409)
        self.modelo.refresh_from_db();self.assertEqual(self.modelo.texto,'Primeira edição')
        self.assertEqual(self.modelo.versao,1)

    def test_formulario_sem_mudanca_nao_cria_auditoria_ou_versao(self):
        antes=RegistroAuditoria.objects.count()
        self.assertEqual(self.client.post(self.editar,self.dados()).status_code,302)
        self.modelo.refresh_from_db();self.assertEqual(self.modelo.versao,0)
        self.assertEqual(RegistroAuditoria.objects.count(),antes)

    def test_falha_de_auditoria_reverte_edicao(self):
        original=self.modelo.texto
        with patch('helpdesk.respostas_prontas.registrar',side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError):self.client.post(self.editar,self.dados(texto='Novo texto'))
        self.modelo.refresh_from_db();self.assertEqual(self.modelo.texto,original)
        self.assertEqual(self.modelo.versao,0)

    def test_integrityerror_retorna_formulario_utilizavel(self):
        with patch('helpdesk.respostas_prontas.RespostaPronta.save',side_effect=IntegrityError('fixture')):
            r=self.client.post(self.nova,{'nome':'Nome concorrente','texto':'Texto','ativa':'on','versao_atual':0})
        self.assertEqual(r.status_code,200);self.assertTrue(r.context['form'].errors)
        self.assertFalse(RespostaPronta.objects.filter(nome='Nome concorrente').exists())

    def test_filtro_nome_estado_e_paginacao_preservam_filtros(self):
        RespostaPronta.objects.filter(pk=self.modelo.pk).update(ativa=False)
        r=self.client.get(self.lista,{'q':'Atendimento','estado':'inativas'})
        self.assertEqual([m.pk for m in r.context['page_obj']],[self.modelo.pk])
        self.assertFalse(self.client.get(self.lista,{'q':'Atendimento','estado':'ativas'}).context['page_obj'])
        for i in range(22):RespostaPronta.objects.create(nome=f'Modelo paginado {i:02}',texto='Texto',ativa=False)
        r=self.client.get(self.lista,{'q':'Modelo paginado','estado':'inativas','page':2})
        self.assertEqual(len(r.context['page_obj']),2)
        self.assertContains(r,'q=Modelo+paginado');self.assertContains(r,'estado=inativas')

    def test_apenas_responsavel_ativo_tem_seletor_e_acesso_ao_texto(self):
        self.client.force_login(self.tec)
        r=self.client.get(self.url);self.assertContains(r,'id="resposta-pronta"')
        self.assertEqual(self.client.get(self.obter).json()['texto'],self.modelo.texto)
        self.assertIn('no-store',self.client.get(self.obter).headers['Cache-Control'])
        for user in (self.cliente,self.outro,self.admin):
            self.client.force_login(user)
            self.assertNotContains(self.client.get(self.url),'id="resposta-pronta"')
            self.assertEqual(self.client.get(self.obter).status_code,403)
        externo=User.objects.create_user('externo-respostas',is_staff=True)
        self.client.force_login(externo)
        self.assertEqual(self.client.get(self.obter).status_code,404)

    def test_desativacao_encerramento_e_perda_de_vinculo_impedem_leitura(self):
        self.client.force_login(self.tec)
        RespostaPronta.objects.filter(pk=self.modelo.pk).update(ativa=False)
        self.assertNotContains(self.client.get(self.url),f'<option value="{self.modelo.pk}"')
        self.assertEqual(self.client.get(self.obter).status_code,404)
        RespostaPronta.objects.filter(pk=self.modelo.pk).update(ativa=True)
        Chamado.objects.filter(pk=self.chamado.pk).update(status='Resolvido')
        self.assertEqual(self.client.get(self.obter).status_code,403)
        self.assertNotContains(self.client.get(self.url),'id="resposta-pronta"')
        Chamado.objects.filter(pk=self.chamado.pk).update(status='Aberto')
        IntegranteEquipe.objects.filter(usuario=self.tec).delete()
        self.assertEqual(self.client.get(self.obter).status_code,404)

    def test_selecionar_modelo_nao_envia_comentario_e_envio_usa_texto_revisado(self):
        self.client.force_login(self.tec)
        antes=(Comentario.objects.count(),Notificacao.objects.count(),RegistroAuditoria.objects.count())
        self.client.get(self.url);self.client.get(self.obter)
        self.assertEqual((Comentario.objects.count(),Notificacao.objects.count(),RegistroAuditoria.objects.count()),antes)
        texto='Resposta adaptada pelo técnico após revisão.'
        self.assertEqual(self.client.post(self.url,{'texto':texto}).status_code,302)
        self.assertEqual(Comentario.objects.get(chamado=self.chamado).texto,texto)
        self.assertEqual(Notificacao.objects.filter(chamado=self.chamado,tipo='resposta').count(),1)
        self.client.force_login(self.admin)
        self.client.post(self.editar,self.dados(texto='Novo modelo',ativa=''))
        self.assertEqual(Comentario.objects.get(chamado=self.chamado).texto,texto)

    def test_sem_modelos_ativos_nao_exibe_seletor_e_post_get_sao_protegidos(self):
        RespostaPronta.objects.update(ativa=False)
        self.client.force_login(self.tec)
        self.assertNotContains(self.client.get(self.url),'id="resposta-pronta"')
        self.assertEqual(self.client.post(self.obter,{}).status_code,405)
        self.assertEqual(Client().get(self.obter).status_code,302)
        User.objects.filter(pk=self.tec.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.obter).status_code,302)

    def test_csrf_exigido_na_edicao_e_html_tratado_como_texto(self):
        estrito=Client(enforce_csrf_checks=True);estrito.force_login(self.admin)
        self.assertEqual(estrito.post(self.editar,self.dados(texto='Tentativa')).status_code,403)
        RespostaPronta.objects.filter(pk=self.modelo.pk).update(nome='<script>nome</script>',texto='<script>alert(1)</script>')
        self.assertNotContains(self.client.get(self.lista),'<script>nome</script>')
        self.client.force_login(self.tec)
        self.assertNotContains(self.client.get(self.url),'<script>nome</script>')
        self.assertEqual(self.client.get(self.obter).json()['texto'],'<script>alert(1)</script>')
