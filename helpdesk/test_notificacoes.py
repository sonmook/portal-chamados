from unittest.mock import patch
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from .models import Chamado, Comentario, Equipe, IntegranteEquipe, Notificacao
from .notificacoes import notificar_atribuicao, notificar_resposta, notificar_resolucao
from .test_helpers import dados_atribuicao


class NotificacoesTests(TestCase):
    def setUp(self):
        self.tec=User.objects.create_user('tecnico-notif',is_staff=True)
        self.outro=User.objects.create_user('outro-notif',is_staff=True)
        self.cliente=User.objects.create_user('cliente-notif')
        self.alheio=User.objects.create_user('alheio-notif')
        self.admin=User.objects.create_superuser('admin-notif','admin@example.invalid',None)
        self.equipe=Equipe.objects.get(triagem_padrao=True)
        self.destino=Equipe.objects.get(nome='Infraestrutura e Redes')
        self.coord=User.objects.create_user('coord-notif',is_staff=True)
        IntegranteEquipe.objects.create(usuario=self.tec,equipe=self.equipe)
        IntegranteEquipe.objects.create(usuario=self.outro,equipe=self.equipe)
        IntegranteEquipe.objects.create(usuario=self.coord,equipe=self.destino,coordenador=True)
        self.t=Chamado.objects.create(titulo='Solicitação de teste',descricao='Descrição',
            solicitante=self.cliente,tecnico=self.tec,equipe=self.equipe)
        self.url=reverse('listar_notificacoes')
        self.client.force_login(self.tec)

    def resposta(self,pessoa=None,texto='Mensagem de teste'):
        if pessoa:self.client.force_login(pessoa)
        return self.client.post(reverse('detalhes_chamado',args=[self.t.pk]),{'texto':texto})

    def distribuir(self,tecnico,equipe=None,**extra):
        self.client.force_login(self.admin)
        return self.client.post(reverse('redistribuir_chamado',args=[self.t.pk]),{
            **dados_atribuicao(self.t),'equipe':(equipe or self.equipe).pk,
            'tecnico':tecnico.pk if tecnico else '', 'responsavel_anterior':self.t.tecnico_id or '',
            'motivo':'Redistribuição de validação',**extra})

    def aviso(self,pessoa=None,evento='manual'):
        return Notificacao.objects.create(destinatario=pessoa or self.tec,chamado=self.t,tipo='resposta',evento=evento)

    def test_resposta_notifica_somente_interlocutor_sem_copiar_conteudo(self):
        self.assertEqual(self.resposta().status_code,302)
        aviso=Notificacao.objects.get();self.assertEqual(aviso.destinatario,self.cliente)
        self.assertEqual(aviso.tipo,'resposta')
        self.assertNotIn('Mensagem de teste', str(aviso.__dict__))
        self.resposta(self.cliente)
        self.assertEqual(set(Notificacao.objects.values_list('destinatario_id',flat=True)),{self.tec.pk,self.cliente.pk})
        self.assertFalse(Notificacao.objects.filter(destinatario=self.outro).exists())

    def test_atribuicao_notifica_destino_solicitante_e_anterior_ainda_autorizado(self):
        self.assertEqual(self.distribuir(self.outro).status_code,302)
        self.assertEqual(set(Notificacao.objects.values_list('destinatario_id',flat=True)),{self.tec.pk,self.outro.pk,self.cliente.pk})
        self.assertTrue(all(n.tipo=='atribuicao' for n in Notificacao.objects.all()))
        quantidade=Notificacao.objects.count()
        self.distribuir(self.outro)
        self.assertEqual(Notificacao.objects.count(),quantidade)

    def test_transferencia_sem_responsavel_notifica_coordenador_destino_e_solicitante(self):
        self.assertEqual(self.distribuir(None,self.destino).status_code,302)
        self.assertEqual(set(Notificacao.objects.values_list('destinatario_id',flat=True)),{self.coord.pk,self.cliente.pk})
        self.assertTrue(all(n.tipo=='transferencia' for n in Notificacao.objects.all()))

    def test_assumir_e_devolver_nao_enviam_aviso_sobre_a_propria_acao(self):
        Chamado.objects.filter(pk=self.t.pk).update(tecnico=None)
        self.assertEqual(self.client.post(reverse('assumir_chamado',args=[self.t.pk])).status_code,302)
        self.assertEqual(set(Notificacao.objects.values_list('destinatario_id',flat=True)),{self.cliente.pk})
        total=Notificacao.objects.count()
        self.client.post(reverse('assumir_chamado',args=[self.t.pk]))
        self.assertEqual(Notificacao.objects.count(),total)
        self.assertEqual(self.client.post(reverse('devolver_chamado',args=[self.t.pk])).status_code,302)
        self.assertEqual(Notificacao.objects.count(),total+1)
        self.assertFalse(Notificacao.objects.filter(destinatario=self.tec).exists())

    def test_resolucao_gera_um_aviso_e_nao_uma_resposta_duplicada(self):
        url=reverse('fechar_chamado',args=[self.t.pk])
        self.assertEqual(self.client.post(url,{'resolucao':'Funcionamento corrigido e validado.'}).status_code,302)
        aviso=Notificacao.objects.get();self.assertEqual(aviso.tipo,'resolucao');self.assertEqual(aviso.destinatario,self.cliente)
        self.assertEqual(self.client.post(url,{'resolucao':'Novamente'}).status_code,403)
        notificar_resolucao(self.t,self.tec.pk)
        self.assertEqual(Notificacao.objects.count(),1)

    def test_eventos_repetidos_nao_duplicam_notificacoes(self):
        self.resposta()
        comentario=Comentario.objects.get(chamado=self.t)
        notificar_resposta(comentario);notificar_resposta(comentario)
        self.assertEqual(Notificacao.objects.count(),1)
        self.distribuir(self.outro);total=Notificacao.objects.count()
        notificar_atribuicao(self.t,self.admin.pk,self.tec.pk,self.equipe.pk)
        self.assertEqual(Notificacao.objects.count(),total)

    def test_usuario_inativo_e_ator_nao_recebem_avisos(self):
        User.objects.filter(pk=self.cliente.pk).update(is_active=False)
        self.resposta();self.assertFalse(Notificacao.objects.exists())
        self.t.solicitante=self.tec;self.t.save(update_fields=['solicitante'])
        self.resposta();self.assertFalse(Notificacao.objects.exists())

    def test_perda_de_acesso_oculta_titulo_contador_e_leitura_por_id(self):
        aviso=self.aviso()
        self.assertContains(self.client.get(self.url),'Solicitação de teste')
        Chamado.objects.filter(pk=self.t.pk).update(equipe=self.destino)
        r=self.client.get(self.url);self.assertNotContains(r,'Solicitação de teste')
        self.assertEqual(r.context['notificacoes_nao_lidas'],0)
        self.assertEqual(self.client.post(reverse('ler_notificacao',args=[aviso.pk])).status_code,404)
        aviso.refresh_from_db();self.assertIsNone(aviso.lida_em)

    def test_retirar_papel_ou_vinculo_tambem_oculta_avisos(self):
        self.aviso();IntegranteEquipe.objects.filter(usuario=self.tec).delete()
        self.assertEqual(self.client.get(self.url).context['notificacoes_nao_lidas'],0)
        IntegranteEquipe.objects.create(usuario=self.tec,equipe=self.equipe)
        User.objects.filter(pk=self.tec.pk).update(is_staff=False)
        self.assertEqual(self.client.get(self.url).context['notificacoes_nao_lidas'],0)

    def test_consulta_e_sino_nao_marcam_leitura_nem_criam_avisos(self):
        aviso=self.aviso();r=self.client.get(self.url)
        self.assertEqual(r.context['notificacoes_nao_lidas'],1)
        self.assertContains(r,'Notificações, 1 não lida')
        self.assertEqual(self.client.get(reverse('detalhes_chamado',args=[self.t.pk])).status_code,200)
        aviso.refresh_from_db();self.assertIsNone(aviso.lida_em)
        self.assertEqual(Notificacao.objects.count(),1)
        self.assertIn('no-store',r['Cache-Control'])

    def test_marcar_individual_preserva_primeira_data_e_abrir_redireciona_ao_chamado(self):
        aviso=self.aviso();url=reverse('ler_notificacao',args=[aviso.pk])
        self.assertEqual(self.client.get(url).status_code,405)
        self.assertRedirects(self.client.post(url),self.url)
        aviso.refresh_from_db();lida=aviso.lida_em;self.assertIsNotNone(lida)
        r=self.client.post(url,{'abrir':'1','next':'https://example.invalid'})
        self.assertRedirects(r,reverse('detalhes_chamado',args=[self.t.pk]))
        aviso.refresh_from_db();self.assertEqual(aviso.lida_em,lida)

    def test_outras_pessoas_nao_listam_ou_marcam_avisos_alheios(self):
        aviso=self.aviso(self.cliente)
        self.assertNotContains(self.client.get(self.url),'Solicitação de teste')
        self.assertEqual(self.client.post(reverse('ler_notificacao',args=[aviso.pk])).status_code,404)
        self.assertEqual(self.client.get(self.url,{'destinatario':self.cliente.pk}).context['notificacoes_nao_lidas'],0)

    def test_marcar_todas_afeta_somente_avisos_visiveis_do_destinatario(self):
        meu=self.aviso();alheio=self.aviso(self.cliente,'outro')
        oculto=Chamado.objects.create(titulo='Oculto',descricao='Fixture',solicitante=self.alheio,equipe=self.destino)
        invisivel=Notificacao.objects.create(destinatario=self.tec,chamado=oculto,tipo='resposta',evento='oculto')
        url=reverse('ler_todas_notificacoes');self.assertEqual(self.client.get(url).status_code,405)
        self.assertRedirects(self.client.post(url),self.url)
        for aviso in [meu,alheio,invisivel]:aviso.refresh_from_db()
        self.assertIsNotNone(meu.lida_em);self.assertIsNone(alheio.lida_em);self.assertIsNone(invisivel.lida_em)
        self.assertEqual(self.client.get(self.url,{'filtro':'nao_lidas'}).context['page_obj'].paginator.count,0)

    def test_csrf_e_login_exigidos(self):
        aviso=self.aviso();c=Client(enforce_csrf_checks=True);c.force_login(self.tec)
        self.assertEqual(c.post(reverse('ler_notificacao',args=[aviso.pk])).status_code,403)
        self.assertEqual(c.post(reverse('ler_todas_notificacoes')).status_code,403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code,302)
        self.assertEqual(self.client.post(reverse('ler_notificacao',args=[aviso.pk])).status_code,302)

    def test_paginacao_filtro_ordenacao_e_contador_limitado_no_visual(self):
        Notificacao.objects.bulk_create([Notificacao(destinatario=self.tec,chamado=self.t,tipo='resposta',evento=f'lote-{i}') for i in range(101)])
        r=self.client.get(self.url,{'filtro':'nao_lidas'})
        self.assertEqual(len(r.context['page_obj']),20);self.assertEqual(r.context['notificacoes_nao_lidas'],101)
        self.assertContains(r,'99+');self.assertContains(r,'Notificações, 101 não lidas')
        self.assertContains(r,'filtro=nao_lidas&amp;page=2')
        self.assertEqual(r.context['page_obj'][0].evento,'lote-100')
        self.assertEqual(self.client.get(self.url,{'filtro':'invalido'}).context['filtro'],'')

    def test_falha_na_notificacao_reverte_resposta_e_interacao(self):
        with patch('helpdesk.notificacoes.Notificacao.objects.get_or_create',side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):self.resposta()
        self.t.refresh_from_db();self.assertIsNone(self.t.ultima_interacao_em)
        self.assertFalse(Comentario.objects.filter(chamado=self.t).exists());self.assertFalse(Notificacao.objects.exists())

    def test_falha_reverte_atribuicao_e_resolucao(self):
        with patch('helpdesk.notificacoes.Notificacao.objects.get_or_create',side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):self.distribuir(self.outro)
        self.t.refresh_from_db();self.assertEqual(self.t.tecnico,self.tec);self.assertEqual(self.t.versao_atribuicao,0)
        self.client.force_login(self.tec)
        with patch('helpdesk.notificacoes.Notificacao.objects.get_or_create',side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):self.client.post(reverse('fechar_chamado',args=[self.t.pk]),{'resolucao':'Corrigido e validado.'})
        self.t.refresh_from_db();self.assertEqual(self.t.status,'Aberto');self.assertIsNone(self.t.data_fechamento)
        self.assertFalse(Comentario.objects.filter(chamado=self.t).exists())

    def test_banco_impede_destinatario_evento_duplicado_e_tipo_invalido(self):
        self.aviso()
        with self.assertRaises(IntegrityError),transaction.atomic():self.aviso()
        with self.assertRaises(IntegrityError),transaction.atomic():
            Notificacao.objects.create(destinatario=self.tec,chamado=self.t,tipo='invalido',evento='tipo')

    def test_resposta_sem_responsavel_avisa_apenas_coordenadores_ativos(self):
        Chamado.objects.filter(pk=self.t.pk).update(tecnico=None)
        IntegranteEquipe.objects.filter(usuario=self.outro,equipe=self.equipe).update(coordenador=True)
        self.resposta(self.cliente)
        self.assertEqual(list(Notificacao.objects.values_list('destinatario_id',flat=True)),[self.outro.pk])

    def test_requisicao_proibida_e_formulario_desatualizado_nao_geram_eventos(self):
        self.assertEqual(self.resposta(self.outro).status_code,403)
        self.assertFalse(Notificacao.objects.exists())
        dados={**dados_atribuicao(self.t),'tecnico':self.outro.pk,'responsavel_anterior':self.tec.pk,
               'motivo':'Alteração controlada'}
        self.client.force_login(self.admin);url=reverse('redistribuir_chamado',args=[self.t.pk])
        self.assertEqual(self.client.post(url,dados).status_code,302)
        total=Notificacao.objects.count();r=self.client.post(url,dados)
        self.assertEqual(r.status_code,200);self.assertTrue(r.context['form'].errors)
        self.assertEqual(Notificacao.objects.count(),total)

    def test_titulo_do_chamado_e_escapado_nos_avisos(self):
        Chamado.objects.filter(pk=self.t.pk).update(titulo='<script>alert(1)</script>')
        self.aviso();r=self.client.get(self.url)
        self.assertNotContains(r,'<script>alert(1)</script>')
        self.assertContains(r,'&lt;script&gt;alert(1)&lt;/script&gt;')
