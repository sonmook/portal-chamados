from unittest.mock import patch
from django.core import signing
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from .construtor_conquistas import PlanoForm, previsao, SALT
from .models import PlanoConquista, RegraConquista, Conquista, RegistroAuditoria
from .test_conquistas import ConquistasFixtureMixin


class ConstrutorTests(ConquistasFixtureMixin, TestCase):
    def plano(self, **extra):
        dados={'nome':'Guardião do SLA','descricao':'Atendimento com cuidado.','icone':'escudo',
               'alvo':'pessoa','metrica':'no_prazo','bronze':1,'prata':2,'ouro':3}
        dados.update(extra)
        return PlanoConquista.objects.create(**dados)

    def dados(self, **extra):
        return {'nome':'Guardião do SLA','descricao':'Atendimento com cuidado.','icone':'escudo','alvo':'pessoa',
                'metrica':'no_prazo','bronze':1,'prata':2,'ouro':3,'contagem':'publicacao','ativa':'on','versao_atual':0,**extra}

    def publicar(self, plano, token=None):
        self.client.force_login(self.admin)
        if token is None:
            token=self.client.get(reverse('prever_plano',args=[plano.pk])).context['impacto']['token']
        return self.client.post(reverse('publicar_plano',args=[plano.pk]),{'confirmacao':token})

    def test_catalogo_nao_permite_criacao_por_get_ou_post(self):
        self.client.force_login(self.admin)
        for metodo in ('get','post'):
            r=getattr(self.client,metodo)(reverse('criar_plano'),self.dados() if metodo=='post' else {})
            self.assertEqual(r.status_code,403)
        self.assertFalse(PlanoConquista.objects.exists())
        self.assertEqual(RegraConquista.objects.count(),12)
        self.assertFalse(Conquista.objects.exists())
        r=self.client.get(reverse('gerenciar_conquistas'))
        self.assertContains(r,'Catálogo de conquistas')
        self.assertNotContains(r,'Criar conquista')
        self.assertNotContains(r,'Configurações existentes')

    def test_ordem_e_limites_dos_niveis_e_metricas_fechadas(self):
        for extra in [{'prata':1},{'ouro':2},{'bronze':0},{'ouro':100001},{'prata':''},{'ouro':''},
                      {'metrica':'tempo_um_minuto'},{'alvo':'todos'},{'contagem':'mensal'},{'icone':'<script>'}]:
            with self.subTest(extra=extra):
                self.assertFalse(PlanoForm(self.dados(**extra)).is_valid())
        self.assertFalse(PlanoConquista.objects.exists())

    def test_previa_get_sem_mutacao_e_criterios_gerados(self):
        p=self.plano(contagem='historico')
        antes=(Conquista.objects.count(),RegraConquista.objects.count(),RegistroAuditoria.objects.count())
        self.client.force_login(self.admin);r=self.client.get(reverse('prever_plano',args=[p.pk]))
        self.assertContains(r,'Quem recebe');self.assertContains(r,'O que conta')
        self.assertContains(r,'Confirmar publicação')
        self.assertEqual(antes,(Conquista.objects.count(),RegraConquista.objects.count(),RegistroAuditoria.objects.count()))

    def test_publicar_historico_preve_e_concede_exatamente_por_nivel(self):
        self.fechar(self.chamado());self.fechar(self.chamado())
        p=self.plano(contagem='historico');prev=previsao(p)
        self.assertEqual([e['novas'] for e in prev['etapas']],[1,1,0])
        self.assertEqual(self.publicar(p).status_code,302)
        p.refresh_from_db();self.assertEqual(p.estado,'publicada');self.assertIsNotNone(p.publicada_em)
        self.assertEqual(p.niveis.count(),3)
        self.assertEqual(set(Conquista.objects.filter(regra__plano=p).values_list('nivel',flat=True)),{'bronze','prata'})
        self.assertEqual(set(Conquista.objects.filter(regra__plano=p).values_list('nome',flat=True)),{'Guardião do SLA'})

    def test_publicacao_sem_historico_inicia_contagem_nova(self):
        self.fechar(self.chamado());self.fechar(self.chamado())
        p=self.plano();self.assertEqual(previsao(p)['total'],0)
        self.publicar(p);self.assertFalse(Conquista.objects.filter(regra__plano=p).exists())
        self.client.force_login(self.tecnico);self.fechar(self.chamado())
        self.assertEqual(list(Conquista.objects.filter(regra__plano=p).values_list('nivel',flat=True)),['bronze'])

    def test_publicacao_idempotente(self):
        self.fechar(self.chamado());p=self.plano(contagem='historico')
        token=previsao(p)['token'];self.publicar(p,token);antes=Conquista.objects.count()
        self.publicar(p,token)
        self.assertEqual(Conquista.objects.count(),antes);self.assertEqual(p.niveis.count(),3)

    def test_confirmacao_invalida_ou_expirada_recusada(self):
        p=self.plano()
        self.assertEqual(self.publicar(p,'invalido').status_code,400)
        original_loads=signing.loads
        def expirado(*args,**kwargs):
            if kwargs.get('salt')==SALT:
                raise signing.SignatureExpired('expirado')
            return original_loads(*args,**kwargs)
        with patch('helpdesk.construtor_conquistas.signing.loads',side_effect=expirado):
            self.assertEqual(self.publicar(p,previsao(p)['token']).status_code,400)
        self.assertFalse(p.niveis.exists());p.refresh_from_db();self.assertEqual(p.estado,'rascunho')

    def test_eventos_novos_alterando_impacto_exigem_nova_previa(self):
        p=self.plano(contagem='historico');token=previsao(p)['token']
        self.fechar(self.chamado())
        r=self.publicar(p,token);self.assertEqual(r.status_code,409)
        self.assertFalse(p.niveis.exists())
        self.assertEqual(self.publicar(p).status_code,302)

    def test_token_de_outro_plano_e_de_rascunho_antigo_nao_publica(self):
        p=self.plano();outro=self.plano()
        self.assertEqual(self.publicar(p,previsao(outro)['token']).status_code,409)
        token=previsao(p)['token'];PlanoConquista.objects.filter(pk=p.pk).update(versao=1)
        self.assertEqual(self.publicar(p,token).status_code,409)

    def test_falha_de_concessao_reverte_publicacao_e_regras(self):
        self.fechar(self.chamado());p=self.plano(contagem='historico')
        with patch('helpdesk.conquistas.conceder',side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):self.publicar(p)
        p.refresh_from_db();self.assertEqual(p.estado,'rascunho');self.assertFalse(p.niveis.exists())
        self.assertFalse(Conquista.objects.filter(regra__plano=p).exists())

    def test_save_de_rascunho_stale_e_publicado_imutavel(self):
        p=self.plano();self.client.force_login(self.admin)
        url=reverse('editar_plano',args=[p.pk])
        self.assertEqual(self.client.post(url,self.dados()).status_code,302)
        self.assertEqual(self.client.post(url,self.dados(bronze=2,prata=3,ouro=4)).status_code,409)
        p.refresh_from_db();self.assertEqual(p.bronze,1)
        self.publicar(p);p.refresh_from_db()
        self.assertEqual(self.client.post(url,self.dados(bronze=10,prata=20,ouro=30)).status_code,302)
        p.refresh_from_db();self.assertEqual(p.bronze,1)

    def test_permissoes_e_csrf_em_todas_as_acoes(self):
        p=self.plano()
        urls=[reverse('criar_plano'),reverse('editar_plano',args=[p.pk]),reverse('prever_plano',args=[p.pk]),
              reverse('publicar_plano',args=[p.pk]),reverse('pausar_plano',args=[p.pk]),reverse('aparencia_plano',args=[p.pk])]
        for usuario in [self.tecnico,self.cliente]:
            self.client.force_login(usuario)
            for url in urls:
                resposta=self.client.get(url) if url==reverse('prever_plano',args=[p.pk]) else self.client.post(url,{})
                self.assertEqual(resposta.status_code,403)
        c=Client(enforce_csrf_checks=True);c.force_login(self.admin)
        self.assertEqual(c.post(reverse('publicar_plano',args=[p.pk]),{'confirmacao':previsao(p)['token']}).status_code,403)
        self.client.logout();self.assertEqual(self.client.get(reverse('criar_plano')).status_code,302)

    def test_regras_filhos_nao_podem_ter_metadados_de_criterio_alterados_individualmente(self):
        p=self.plano();self.publicar(p);r=p.niveis.get(nivel='bronze')
        self.client.post(reverse('editar_conquista',args=[r.pk]),self.regra_dados(r,meta=999,ativa=''))
        r.refresh_from_db();self.assertEqual(r.meta,1);self.assertTrue(r.ativa)

    def test_aparencia_nao_reavalia_e_preserva_medalhas(self):
        self.fechar(self.chamado());p=self.plano(contagem='historico');self.publicar(p);p.refresh_from_db()
        c=Conquista.objects.get(regra__plano=p,nivel='bronze');antes=c.nome;icone=c.icone;total=Conquista.objects.count()
        with patch('helpdesk.conquistas.reavaliar_regra',side_effect=AssertionError('não deve reavaliar')):
            r=self.client.post(reverse('aparencia_plano',args=[p.pk]),{'nome':'Novo nome','descricao':'Outra apresentação','icone':'estrela','versao_atual':p.versao})
        self.assertEqual(r.status_code,302);self.assertEqual(Conquista.objects.count(),total)
        c.refresh_from_db();self.assertEqual(c.nome,antes);self.assertEqual(c.icone,icone)
        p.refresh_from_db();self.assertEqual(p.nome,'Novo nome');self.assertTrue(all(r.icone=='estrela' for r in p.niveis.all()))

    def test_pausa_e_retomada_com_previa_sem_apagar_progresso(self):
        p=self.plano();self.publicar(p);p.refresh_from_db()
        r=self.client.post(reverse('pausar_plano',args=[p.pk]),{'versao':p.versao});self.assertEqual(r.status_code,302)
        self.assertFalse(p.niveis.filter(ativa=True).exists())
        self.client.force_login(self.tecnico);self.fechar(self.chamado())
        self.assertFalse(Conquista.objects.filter(regra__plano=p).exists())
        self.client.force_login(self.admin)
        prev=self.client.get(reverse('prever_plano',args=[p.pk]))
        self.assertEqual(prev.context['impacto']['total'],1)
        self.assertContains(prev,'Confirmar retomada')
        self.publicar(p,prev.context['impacto']['token']);p.refresh_from_db()
        self.assertTrue(p.ativa);self.assertEqual(Conquista.objects.filter(regra__plano=p).count(),1)

    def test_pausa_e_aparencia_stale_nao_sobrescrevem(self):
        p=self.plano();self.publicar(p);p.refresh_from_db()
        self.assertEqual(self.client.post(reverse('pausar_plano',args=[p.pk]),{'versao':0}).status_code,409)
        self.assertEqual(self.client.post(reverse('aparencia_plano',args=[p.pk]),{'nome':'X','descricao':'X','icone':'raio','versao_atual':0}).status_code,409)
        p.refresh_from_db();self.assertTrue(p.ativa);self.assertEqual(p.nome,'Guardião do SLA')

    def test_progressao_agrupada_e_vitrine_com_niveis(self):
        p=self.plano();self.publicar(p)
        self.client.force_login(self.tecnico)
        self.fechar(self.chamado())
        r=self.client.get(reverse('minhas_conquistas'))
        trilha=next(c for c in r.context['pessoais'] if c['plano'] and c['plano'].pk==p.pk)
        self.assertEqual(trilha['regra'].nivel,'prata');self.assertEqual(trilha['desbloqueadas'],1)
        self.assertContains(r,'Próximo nível: Prata')
        self.assertContains(self.client.get(reverse('meu_perfil')),'Bronze')
        self.fechar(self.chamado());self.fechar(self.chamado())
        self.assertEqual(Conquista.objects.filter(regra__plano=p).count(),3)
        self.assertContains(self.client.get(reverse('minhas_conquistas')),'Trilha completa!')

    def test_trilha_coletiva_nao_expoe_progresso_a_solicitante_ou_outra_equipe(self):
        p=self.plano(alvo='equipe');self.publicar(p)
        self.client.force_login(self.tecnico);self.fechar(self.chamado())
        r=self.client.get(reverse('minhas_conquistas'))
        self.assertTrue(any(c['plano'] and c['plano'].pk==p.pk for c in r.context['coletivas']))
        self.client.force_login(self.cliente);self.assertEqual(self.client.get(reverse('minhas_conquistas')).context['coletivas'],[])

    def test_banco_rejeita_metas_invalidas_e_niveis_duplicados(self):
        with self.assertRaises(IntegrityError),transaction.atomic():self.plano(prata=1)
        p=self.plano();self.publicar(p);regra=p.niveis.get(nivel='bronze')
        with self.assertRaises(IntegrityError),transaction.atomic():
            RegraConquista.objects.create(codigo='outra',plano=p,nivel='bronze',nome='X',descricao='X',alvo='pessoa',metrica='resolucoes',meta=5)

    def test_revisao_legacy_stale_precisa_reabrir_e_revisar(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('editar_conquista',args=[self.regra.pk]),self.regra_dados(self.regra,meta=2))
        p=PlanoConquista.objects.get(regra_origem=self.regra);token=previsao(p)['token']
        RegraConquista.objects.filter(pk=self.regra.pk).update(versao=1,nome='Mudou')
        self.assertEqual(self.publicar(p,token).status_code,409)
        p.refresh_from_db()
        dados=self.dados(nome=p.nome,descricao=p.descricao,icone=p.icone,bronze=2,prata='',ouro='',versao_atual=p.versao,origem_versao=1)
        self.assertEqual(self.client.post(reverse('editar_plano',args=[p.pk]),dados).status_code,302)
        self.assertEqual(self.publicar(p).status_code,302)
        self.regra.refresh_from_db();self.assertEqual(self.regra.meta,2)

    def test_regra_legacy_visual_nao_reavalia_mesmo_com_meta_atingida(self):
        self.fechar(self.chamado());Conquista.objects.filter(usuario=self.tecnico).delete()
        self.client.force_login(self.admin)
        with patch('helpdesk.conquistas.reavaliar_regra',side_effect=AssertionError('não reavaliar')):
            self.client.post(reverse('editar_conquista',args=[self.regra.pk]),self.regra_dados(self.regra,icone='estrela'))
        self.assertFalse(Conquista.objects.filter(usuario=self.tecnico).exists())

    def test_publicacao_concede_somente_destinatarios_da_previa_validada(self):
        from .construtor_conquistas import conceder_previa
        from .models import ResolucaoConquista
        from django.utils import timezone
        self.fechar(self.chamado());p=self.plano(contagem='historico')
        chamadas=[]
        def depois_da_validacao(regra, etapa):
            if not chamadas:
                t=self.chamado()
                ResolucaoConquista.objects.create(chamado=t,usuario=self.outro,equipe=self.equipe,
                    concluido_em=timezone.now(),no_prazo=True)
            chamadas.append(regra.nivel)
            return conceder_previa(regra,etapa)
        with patch('helpdesk.construtor_conquistas.conceder_previa',side_effect=depois_da_validacao):
            self.publicar(p)
        self.assertEqual(Conquista.objects.filter(regra__plano=p).count(),1)
        self.assertFalse(Conquista.objects.filter(regra__plano=p,usuario=self.outro).exists())

    def test_configuracoes_anteriores_continuam_acessiveis_sem_criacao(self):
        p=self.plano();self.publicar(p)
        r=self.client.get(reverse('gerenciar_conquistas'))
        self.assertContains(r,'Configurações existentes')
        self.assertContains(r,p.nome)
        self.assertNotContains(r,'Criar conquista')
        self.assertEqual(self.client.get(reverse('prever_plano',args=[p.pk])).status_code,200)

    def test_revisao_publicada_pausada_nao_pode_ser_retomada_como_trilha(self):
        p=self.plano(regra_origem=self.regra,base_versao=self.regra.versao,
            prata=None,ouro=None,ativa=False,contagem='historico')
        self.publicar(p);p.refresh_from_db()
        r=self.client.get(reverse('prever_plano',args=[p.pk]))
        self.assertNotContains(r,'Confirmar retomada')
        self.assertContains(r,'Editar a regra original')
        self.publicar(p);self.regra.refresh_from_db();self.assertFalse(self.regra.ativa)
