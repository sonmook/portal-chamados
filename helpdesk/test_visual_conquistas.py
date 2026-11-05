from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Conquista, RegraConquista, ResolucaoConquista, Equipe, Chamado, IntegranteEquipe
from .conquistas import RegraConquistaForm, registrar_resolucao
from .visual_conquistas import ICONES, visual


class VisualConquistasTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_superuser('admin-visual','admin@example.invalid',None)
        self.user=User.objects.create_user('tecnico-visual',is_staff=True)
        self.cliente=User.objects.create_user('cliente-visual')
        self.equipe=Equipe.objects.get(triagem_padrao=True)
        IntegranteEquipe.objects.create(equipe=self.equipe,usuario=self.user)
        self.regra=RegraConquista.objects.get(codigo='primeira-solucao')

    def resolver(self):
        agora=timezone.now()
        t=Chamado.objects.create(titulo='Teste',descricao='Teste',solicitante=self.cliente,tecnico=self.user,
            fechado_por=self.user,equipe=self.equipe,status='Resolvido',data_fechamento=agora,data_vencimento=agora+timedelta(hours=1))
        registrar_resolucao(t)
        return t

    def dados(self,**extra):
        return {'nome':self.regra.nome,'descricao':self.regra.descricao,'meta':self.regra.meta,
                'ativa':'on','icone':self.regra.icone,'versao_atual':self.regra.versao,**extra}

    def test_icones_iniciais_distintos(self):
        self.assertEqual(list(RegraConquista.objects.filter(codigo__in=['primeira-solucao','vinte-solucoes','no-prazo','equipe-no-prazo']).order_by('pk').values_list('icone',flat=True)),
                         ['foguete','trofeu','cronometro','equipe'])

    def test_validacao_de_catalogo_fechado(self):
        for icone in ['<img src=x onerror=alert(1)>','bi-person','arquivo.svg','']:
            self.assertFalse(RegraConquistaForm(self.dados(icone=icone),instance=self.regra).is_valid())
        self.assertEqual(visual('desconhecido'),ICONES['trofeu'])

    def test_icone_novo_nao_reescreve_medalha_concedida(self):
        self.resolver();c=Conquista.objects.get(usuario=self.user)
        self.assertEqual(c.icone,'foguete')
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('editar_conquista',args=[self.regra.pk]),self.dados(icone='estrela')).status_code,302)
        self.regra.refresh_from_db();c.refresh_from_db()
        self.assertEqual(self.regra.icone,'estrela');self.assertEqual(c.icone,'foguete')
        outro=User.objects.create_user('outro-visual',is_staff=True)
        IntegranteEquipe.objects.create(equipe=self.equipe,usuario=outro)
        self.user=outro;self.resolver()
        self.assertEqual(Conquista.objects.get(usuario=outro).icone,'estrela')

    def test_editor_de_icones_so_para_administrador(self):
        url=reverse('editar_conquista',args=[self.regra.pk])
        self.client.force_login(self.user);self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.admin)
        r=self.client.get(url)
        self.assertContains(r,'name="icone"',count=8)
        self.assertContains(r,'id="icone-foguete"')

    def test_tela_tem_icones_progresso_textual_e_estado_pausado(self):
        self.client.force_login(self.user)
        r=self.client.get(reverse('minhas_conquistas'))
        self.assertContains(r,'bi-rocket-takeoff-fill');self.assertContains(r,'bi-trophy-fill')
        self.assertContains(r,'bi-stopwatch-fill');self.assertContains(r,'bi-people-fill')
        self.assertContains(r,'Falta só 1 resolução elegível')
        RegraConquista.objects.filter(pk=self.regra.pk).update(ativa=False)
        self.assertContains(self.client.get(reverse('minhas_conquistas')),'Pausada')
        self.assertFalse(ResolucaoConquista.objects.exists())

    def test_rollback_da_edicao_preserva_icone(self):
        self.client.force_login(self.admin)
        with patch('helpdesk.conquistas.registrar',side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):self.client.post(reverse('editar_conquista',args=[self.regra.pk]),self.dados(icone='raio'))
        self.regra.refresh_from_db();self.assertEqual(self.regra.icone,'foguete')
