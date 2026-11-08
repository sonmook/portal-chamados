from datetime import timedelta
from urllib.parse import urlsplit,parse_qs
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Chamado, Equipe, IntegranteEquipe, Notificacao, RegistroAuditoria
from .operacao import resumo_operacional
from .acesso import chamados_acessiveis


class ResumoOperacionalTests(TestCase):
    def setUp(self):
        self.agora=timezone.now()
        self.tec=User.objects.create_user('resumo-tecnico',is_staff=True)
        self.outro=User.objects.create_user('resumo-outro',is_staff=True)
        self.cliente=User.objects.create_user('resumo-cliente')
        self.admin=User.objects.create_superuser('resumo-admin','admin@example.invalid',None)
        self.equipe=Equipe.objects.get(triagem_padrao=True)
        self.alheia=Equipe.objects.get(nome='Infraestrutura e Redes')
        IntegranteEquipe.objects.create(equipe=self.equipe,usuario=self.tec,coordenador=True)
        self.client.force_login(self.tec);self.url=reverse('lista_chamados')

    def chamado(self,minutos=180,**extra):
        dados=dict(titulo='Rede & acesso',descricao='Fixture operacional',solicitante=self.cliente,
            equipe=self.equipe,tecnico=self.tec,data_vencimento=self.agora+timedelta(minutes=minutos))
        dados.update(extra);return Chamado.objects.create(**dados)

    def cards(self,r):return {x['chave']:x for x in r.context['resumo_operacional']}

    def get(self,params=None):
        with patch('helpdesk.views.timezone.now',return_value=self.agora):
            return self.client.get(self.url,params or {})

    def test_contadores_e_links_correspondem_a_lista_sem_ampliar_acesso(self):
        self.chamado();self.chamado(30);self.chamado(-1)
        self.chamado(30,tecnico=None);self.chamado(-1,tecnico=self.outro)
        self.chamado(-1,status='Resolvido');self.chamado(-1,status='Fechado',tecnico=None)
        self.chamado(-1,equipe=self.alheia)
        self.chamado(-1,equipe=self.alheia,tecnico=None)
        esperado={'minha':3,'sem_responsavel':1,'proximos':2,'vencidos':2}
        cards=self.cards(self.get())
        for chave,card in cards.items():
            self.assertEqual(card['total'],esperado[chave])
            with patch('helpdesk.views.timezone.now',return_value=self.agora):r=self.client.get(card['url'])
            self.assertEqual(r.context['page_obj'].paginator.count,card['total'])
            self.assertTrue(self.cards(r)[chave]['ativo'])

    def test_limites_de_sla_e_prazo_nulo(self):
        self.chamado(60);self.chamado(0);self.chamado(-1)
        fora=self.chamado(60)
        Chamado.objects.filter(pk=fora.pk).update(data_vencimento=self.agora+timedelta(hours=1,microseconds=1))
        sem=self.chamado(tecnico=None);Chamado.objects.filter(pk=sem.pk).update(data_vencimento=None)
        cards=self.cards(self.get())
        self.assertEqual(cards['proximos']['total'],2)
        self.assertEqual(cards['vencidos']['total'],1)
        self.assertEqual(cards['sem_responsavel']['total'],1)

    def test_equipe_selecionada_preservada_e_demais_filtros_limpos(self):
        self.chamado(-1,tecnico=None);self.chamado(30)
        r=self.get({'equipe':str(self.equipe.pk),'q':'Nao existe & acesso','status':'Fechado',
            'categoria':'Hardware','fila':'minha','sla':'vencidos','page':9})
        self.assertFalse(r.context['page_obj'])
        cards=self.cards(r)
        self.assertEqual(cards['sem_responsavel']['total'],1)
        self.assertFalse(any(c['ativo'] for c in cards.values()))
        for c in cards.values():
            params=parse_qs(urlsplit(c['url']).query)
            self.assertEqual(params['equipe'],[str(self.equipe.pk)])
            self.assertFalse(set(params)&{'q','status','categoria','page','ordenacao'})
            with patch('helpdesk.views.timezone.now',return_value=self.agora):destino=self.client.get(c['url'])
            self.assertEqual(destino.context['page_obj'].paginator.count,c['total'])

    def test_admin_pode_resumir_todas_e_cada_equipe(self):
        self.chamado(-1,tecnico=None)
        self.chamado(30,equipe=self.alheia,tecnico=self.admin)
        self.client.force_login(self.admin)
        cards=self.cards(self.get())
        self.assertEqual(cards['minha']['total'],1);self.assertEqual(cards['vencidos']['total'],1)
        cards=self.cards(self.get({'equipe':str(self.alheia.pk)}))
        self.assertEqual(cards['minha']['total'],1);self.assertEqual(cards['vencidos']['total'],0)

    def test_solicitacoes_proprias_respeitam_acesso_e_equipes_invalidas_nao_vazam(self):
        self.chamado(-1,equipe=self.alheia,solicitante=self.tec,tecnico=None)
        self.assertEqual(self.cards(self.get())['sem_responsavel']['total'],1)
        self.assertEqual(self.cards(self.get({'equipe':str(self.alheia.pk)}))['vencidos']['total'],1)
        self.chamado(-1,equipe=self.alheia)
        for valor in ('invalida','9'*100,'-1','999999'):
            cards=self.cards(self.get({'equipe':valor}))
            self.assertTrue(all(c['total']==0 for c in cards.values()))

    def test_clientes_nao_recebem_resumo_nem_fila_operacional(self):
        self.chamado(tecnico=None)
        self.client.force_login(self.cliente)
        r=self.get();self.assertEqual(r.context['resumo_operacional'],[])
        self.assertNotContains(r,'Resumo operacional da fila')
        self.assertFalse(self.get({'fila':'sem_responsavel'}).context['page_obj'])
        self.assertEqual(resumo_operacional(chamados_acessiveis(self.cliente),self.cliente,self.agora),[])

    def test_sem_responsavel_combina_sla_busca_e_paginacao(self):
        for _ in range(11):self.chamado(-1,tecnico=None)
        self.chamado(-1);self.chamado(30,tecnico=None);self.chamado(-1,status='Resolvido',tecnico=None)
        r=self.get({'fila':'sem_responsavel','sla':'vencidos','q':'Rede & acesso','page':2})
        self.assertEqual(r.context['page_obj'].paginator.count,11)
        self.assertEqual(len(r.context['page_obj']),1)
        self.assertContains(r,'Fila: chamados ativos sem responsável')
        self.assertFalse(any(c['ativo'] for c in self.cards(r).values()))

    def test_resumo_vazio_nao_cria_chamados_alertas_ou_auditoria(self):
        antes=(Chamado.objects.count(),Notificacao.objects.count(),RegistroAuditoria.objects.count())
        r=self.get()
        self.assertTrue(all(c['total']==0 for c in self.cards(r).values()))
        self.assertEqual((Chamado.objects.count(),Notificacao.objects.count(),RegistroAuditoria.objects.count()),antes)

    def test_perda_de_vinculo_remove_dados_da_equipe(self):
        self.chamado(-1,tecnico=None)
        IntegranteEquipe.objects.filter(usuario=self.tec).delete()
        self.assertTrue(all(c['total']==0 for c in self.cards(self.get()).values()))

    def test_contadores_usam_uma_consulta_agregada(self):
        self.chamado(-1)
        with self.assertNumQueries(1):
            cards=resumo_operacional(chamados_acessiveis(self.tec),self.tec,self.agora)
        self.assertEqual(next(c for c in cards if c['chave']=='vencidos')['total'],1)
