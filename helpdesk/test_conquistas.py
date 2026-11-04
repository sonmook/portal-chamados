from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .conquistas import registrar_resolucao
from .models import Chamado, Comentario, Conquista, Equipe, IntegranteEquipe, RegraConquista, ResolucaoConquista, RegistroAuditoria


class ConquistasTests(TestCase):
    def setUp(self):
        self.tecnico=User.objects.create_user('tecnico',is_staff=True)
        self.outro=User.objects.create_user('outro',is_staff=True)
        self.cliente=User.objects.create_user('cliente')
        self.admin=User.objects.create_superuser('admin','admin@example.invalid','senha')
        self.equipe=Equipe.objects.get(triagem_padrao=True)
        self.destino=Equipe.objects.get(nome='Infraestrutura e Redes')
        IntegranteEquipe.objects.create(equipe=self.equipe,usuario=self.tecnico,coordenador=True)
        IntegranteEquipe.objects.create(equipe=self.equipe,usuario=self.outro)
        self.client.force_login(self.tecnico)
        self.regra=RegraConquista.objects.get(codigo='primeira-solucao')
        self.url=reverse('minhas_conquistas')

    def chamado(self, **extra):
        return Chamado.objects.create(titulo='Solicitação',descricao='Descrição',solicitante=self.cliente,
            tecnico=self.tecnico,equipe=self.equipe,**extra)

    def fechar(self,t):
        return self.client.post(reverse('fechar_chamado',args=[t.pk]),{'resolucao':'Configuração corrigida e validada com solicitante.'})

    def regra_dados(self,regra,**extra):
        return {'nome':regra.nome,'descricao':regra.descricao,'meta':regra.meta,
                'ativa':'on','versao_atual':regra.versao,**extra}

    def test_primeira_solucao_concedida_apenas_uma_vez_no_fluxo_real(self):
        t=self.chamado();r=self.fechar(t)
        self.assertEqual(r.status_code,302)
        evento=ResolucaoConquista.objects.get(chamado=t)
        self.assertEqual(evento.usuario,self.tecnico);self.assertEqual(evento.equipe,self.equipe)
        self.assertTrue(evento.no_prazo)
        c=Conquista.objects.get(usuario=self.tecnico)
        self.assertEqual(c.nome,'Primeira solução')
        self.assertEqual(c.meta,1)
        self.assertTrue(RegistroAuditoria.objects.filter(objeto='helpdesk.conquista',ator=self.tecnico,acao='concedido').exists())
        self.assertEqual(registrar_resolucao(t),[])
        self.assertEqual(self.fechar(t).status_code,403)
        self.fechar(self.chamado())
        self.assertEqual(Conquista.objects.filter(regra=self.regra,usuario=self.tecnico).count(),1)
        self.assertEqual(ResolucaoConquista.objects.count(),2)

    def test_metas_pessoais_e_coletivas_independentes_por_criterio(self):
        RegraConquista.objects.filter(codigo__in=['vinte-solucoes','no-prazo','equipe-no-prazo']).update(meta=2)
        a=self.chamado(data_vencimento=timezone.now()-timedelta(hours=1));self.fechar(a)
        self.fechar(self.chamado())
        self.assertTrue(Conquista.objects.filter(usuario=self.tecnico,regra__codigo='vinte-solucoes').exists())
        self.assertFalse(Conquista.objects.filter(regra__codigo='no-prazo').exists())
        self.fechar(self.chamado())
        self.assertTrue(Conquista.objects.filter(usuario=self.tecnico,regra__codigo='no-prazo').exists())
        self.assertTrue(Conquista.objects.filter(equipe=self.equipe,usuario__isnull=True,regra__codigo='equipe-no-prazo').exists())
        self.assertEqual(Conquista.objects.count(),4)

    def test_conquista_coletiva_soma_tecnicos_da_mesma_equipe(self):
        RegraConquista.objects.filter(codigo='equipe-no-prazo').update(meta=2)
        self.fechar(self.chamado())
        t=self.chamado();Chamado.objects.filter(pk=t.pk).update(tecnico=self.outro)
        self.client.force_login(self.outro);self.fechar(t)
        self.assertEqual(Conquista.objects.filter(equipe=self.equipe).count(),1)
        self.assertEqual(ResolucaoConquista.objects.filter(equipe=self.equipe).count(),2)

    def test_proprio_chamado_nao_conta(self):
        t=self.chamado();Chamado.objects.filter(pk=t.pk).update(solicitante=self.tecnico)
        self.assertEqual(self.fechar(t).status_code,302)
        self.assertFalse(ResolucaoConquista.objects.exists());self.assertFalse(Conquista.objects.exists())

    def test_sem_solucao_ou_sem_responsabilidade_nao_conta(self):
        t=self.chamado()
        self.assertEqual(self.client.post(reverse('fechar_chamado',args=[t.pk]),{'resolucao':' '}).status_code,400)
        self.client.force_login(self.outro);self.assertEqual(self.fechar(t).status_code,403)
        self.assertFalse(ResolucaoConquista.objects.exists())
        self.assertEqual(registrar_resolucao(t),[])

    def test_transferencia_nao_conta_e_equipe_do_encerramento_fica_registrada(self):
        IntegranteEquipe.objects.create(equipe=self.destino,usuario=self.tecnico)
        t=self.chamado()
        dados={'equipe':self.destino.pk,'tecnico':self.tecnico.pk,'motivo':'Especialização',
               'equipe_anterior':self.equipe.pk,'responsavel_anterior':self.tecnico.pk,'versao_atribuicao':0}
        self.assertEqual(self.client.post(reverse('redistribuir_chamado',args=[t.pk]),dados).status_code,302)
        self.assertFalse(ResolucaoConquista.objects.exists())
        self.fechar(t)
        self.assertEqual(ResolucaoConquista.objects.get().equipe,self.destino)

    def test_orm_e_historico_anterior_nao_geram_contagem_retroativa(self):
        t=self.chamado(status='Resolvido',fechado_por=self.tecnico,data_fechamento=timezone.now()-timedelta(days=20))
        self.assertFalse(ResolucaoConquista.objects.exists())
        registrar_resolucao(t)
        self.assertFalse(Conquista.objects.exists())
        r=self.client.get(self.url)
        self.assertEqual(r.context['pessoais'][0]['total'],0)

    def test_comparacao_sla_inclusive_no_limite(self):
        agora=timezone.now()
        t=self.chamado(status='Resolvido',fechado_por=self.tecnico,data_fechamento=agora,data_vencimento=agora)
        registrar_resolucao(t)
        self.assertTrue(ResolucaoConquista.objects.get().no_prazo)

    def test_sem_prazo_nao_conta_como_no_prazo(self):
        t=self.chamado(status='Resolvido',fechado_por=self.tecnico,data_fechamento=timezone.now())
        Chamado.objects.filter(pk=t.pk).update(data_vencimento=None)
        registrar_resolucao(t)
        self.assertFalse(ResolucaoConquista.objects.get().no_prazo)

    def test_pausa_preserva_contagem_e_reativacao_reavalia(self):
        RegraConquista.objects.filter(pk=self.regra.pk).update(ativa=False)
        self.fechar(self.chamado())
        self.assertEqual(ResolucaoConquista.objects.count(),1);self.assertFalse(Conquista.objects.exists())
        self.client.force_login(self.admin)
        self.regra.refresh_from_db()
        r=self.client.post(reverse('editar_conquista',args=[self.regra.pk]),self.regra_dados(self.regra))
        self.assertEqual(r.status_code,302)
        self.assertTrue(Conquista.objects.filter(regra=self.regra,usuario=self.tecnico).exists())

    def test_editar_meta_nao_altera_medalha_concedida_e_nao_altera_criterio_por_post(self):
        self.fechar(self.chamado());c=Conquista.objects.get()
        self.client.force_login(self.admin)
        r=self.client.post(reverse('editar_conquista',args=[self.regra.pk]),self.regra_dados(self.regra,
            nome='Novo nome',meta=5,alvo='equipe',metrica='no_prazo',inicio_em='2000-01-01',codigo='outro'))
        self.assertEqual(r.status_code,302)
        c.refresh_from_db();self.regra.refresh_from_db()
        self.assertEqual(c.nome,'Primeira solução');self.assertEqual(c.meta,1)
        self.assertEqual(self.regra.alvo,'pessoa');self.assertEqual(self.regra.metrica,'resolucoes')
        self.assertEqual(self.regra.codigo,'primeira-solucao')
        self.assertEqual(self.regra.nome,'Novo nome')

    def test_meta_reduzida_reavalia_sem_duplicar(self):
        self.fechar(self.chamado());r=RegraConquista.objects.get(codigo='vinte-solucoes')
        self.client.force_login(self.admin)
        self.client.post(reverse('editar_conquista',args=[r.pk]),self.regra_dados(r,meta=1))
        self.assertTrue(Conquista.objects.filter(regra=r,usuario=self.tecnico).exists())
        r.refresh_from_db();self.client.post(reverse('editar_conquista',args=[r.pk]),self.regra_dados(r))
        self.assertEqual(Conquista.objects.filter(regra=r,usuario=self.tecnico).count(),1)

    def test_permissoes_de_gestao_e_csrf(self):
        editar=reverse('editar_conquista',args=[self.regra.pk])
        for usuario in [self.tecnico,self.cliente]:
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse('gerenciar_conquistas')).status_code,403)
            self.assertEqual(self.client.post(editar,self.regra_dados(self.regra)).status_code,403)
        c=Client(enforce_csrf_checks=True);c.force_login(self.admin)
        self.assertEqual(c.post(editar,self.regra_dados(self.regra)).status_code,403)
        self.client.logout();self.assertEqual(self.client.get(self.url).status_code,302)

    def test_isolamento_de_progresso_e_equipes(self):
        self.fechar(self.chamado())
        self.client.force_login(self.outro)
        r=self.client.get(self.url)
        self.assertEqual(r.context['pessoais'][0]['total'],0)
        self.assertIsNone(r.context['pessoais'][0]['conquista'])
        self.assertEqual(r.context['coletivas'][0]['total'],1)
        self.assertEqual(self.client.get(self.url,{'equipe':self.destino.pk}).status_code,404)
        self.client.force_login(self.cliente);r=self.client.get(self.url)
        self.assertEqual(r.context['coletivas'],[])
        self.assertEqual(self.client.get(self.url,{'equipe':self.equipe.pk}).status_code,404)
        self.assertEqual(self.client.get(self.url,{'equipe':'invalida'}).status_code,404)

    def test_get_nao_grava_e_vitrine_e_notificacao_apos_encerramento(self):
        antes=(Conquista.objects.count(),ResolucaoConquista.objects.count(),RegistroAuditoria.objects.count())
        self.client.get(self.url)
        self.assertEqual(antes,(Conquista.objects.count(),ResolucaoConquista.objects.count(),RegistroAuditoria.objects.count()))
        r=self.client.post(reverse('fechar_chamado',args=[self.chamado().pk]),{'resolucao':'Corrigido e validado.'},follow=True)
        self.assertContains(r,'Conquista desbloqueada: Primeira solução!')
        self.assertContains(self.client.get(reverse('meu_perfil')),'Primeira solução')

    def test_conflito_de_versao_e_limites_de_meta(self):
        self.client.force_login(self.admin)
        url=reverse('editar_conquista',args=[self.regra.pk])
        self.client.post(url,self.regra_dados(self.regra,meta=2))
        self.assertEqual(self.client.post(url,self.regra_dados(self.regra,meta=3)).status_code,409)
        self.regra.refresh_from_db();self.assertEqual(self.regra.meta,2)
        for meta in [0,-1,100001,'abc']:
            self.assertEqual(self.client.post(url,self.regra_dados(self.regra,meta=meta)).status_code,200)
        self.regra.refresh_from_db();self.assertEqual(self.regra.meta,2)

    def test_falha_de_auditoria_reverte_encerramento_evento_e_conquista(self):
        t=self.chamado()
        with patch('helpdesk.conquistas.registrar',side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):self.fechar(t)
        t.refresh_from_db();self.assertEqual(t.status,'Aberto')
        self.assertFalse(Conquista.objects.exists());self.assertFalse(ResolucaoConquista.objects.exists())
        self.assertFalse(Comentario.objects.filter(chamado=t).exists())

    def test_falha_de_reavaliacao_reverte_regra(self):
        self.client.force_login(self.admin)
        with patch('helpdesk.conquistas.reavaliar_regra',side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):self.client.post(reverse('editar_conquista',args=[self.regra.pk]),self.regra_dados(self.regra,meta=2))
        self.regra.refresh_from_db();self.assertEqual(self.regra.meta,1);self.assertEqual(self.regra.versao,0)

    def test_restricoes_de_destinatario_e_unicidade(self):
        self.fechar(self.chamado())
        with self.assertRaises(IntegrityError),transaction.atomic():
            Conquista.objects.create(regra=self.regra,usuario=self.tecnico,nome='Duplicada',descricao='Teste',meta=1,versao_regra=0)
        with self.assertRaises(IntegrityError),transaction.atomic():
            Conquista.objects.create(regra=self.regra,nome='Sem dono',descricao='Teste',meta=1,versao_regra=0)
        with self.assertRaises(IntegrityError),transaction.atomic():
            Conquista.objects.create(regra=self.regra,usuario=self.outro,equipe=self.equipe,nome='Ambígua',descricao='Teste',meta=1,versao_regra=0)
