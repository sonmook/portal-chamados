from html import unescape
import re
from urllib.parse import parse_qs, urlsplit
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from .models import Chamado, Equipe, IntegranteEquipe


class MinhaFilaTests(TestCase):
    def setUp(self):
        self.tec=User.objects.create_user('tecnico-fila',is_staff=True)
        self.outro=User.objects.create_user('outro-fila',is_staff=True)
        self.cliente=User.objects.create_user('cliente-fila')
        self.admin=User.objects.create_user('admin-fila',is_staff=True,is_superuser=True)
        self.equipe=Equipe.objects.get(triagem_padrao=True)
        self.alheia=Equipe.objects.get(nome='Infraestrutura e Redes')
        IntegranteEquipe.objects.create(equipe=self.equipe,usuario=self.tec)
        self.client.force_login(self.tec);self.url=reverse('lista_chamados')

    def chamado(self,**extra):
        dados={'titulo':'Rede & acesso','descricao':'Fixture','solicitante':self.cliente,
            'tecnico':self.tec,'equipe':self.equipe,'categoria':'Rede'}
        dados.update(extra);return Chamado.objects.create(**dados)

    def test_fila_apenas_ativos_atribuidos_ao_usuario_sem_ampliar_acesso(self):
        aberto=self.chamado();andamento=self.chamado(status='Em Andamento')
        self.chamado(status='Resolvido');self.chamado(status='Fechado')
        self.chamado(tecnico=self.outro);self.chamado(tecnico=None)
        self.chamado(equipe=self.alheia)
        r=self.client.get(self.url,{'fila':'minha','tecnico':self.outro.pk})
        self.assertEqual({x.pk for x in r.context['page_obj']},{aberto.pk,andamento.pk})
        self.assertContains(r,'Minha fila: chamados ativos atribuídos a você')
        self.assertContains(r,'value="minha" selected')

    def test_combinacao_de_busca_status_categoria_equipe_e_ordenacao(self):
        esperado=self.chamado(status='Em Andamento')
        self.chamado();self.chamado(categoria='Hardware',status='Em Andamento')
        self.chamado(titulo='Impressora',status='Em Andamento')
        r=self.client.get(self.url,{'fila':'minha','q':'Rede & acesso','categoria':'Rede',
            'status':'Em Andamento','equipe':self.equipe.pk,'ordenacao':'sem_interacao'})
        self.assertEqual([x.pk for x in r.context['page_obj']],[esperado.pk])
        self.assertFalse(self.client.get(self.url,{'fila':'minha','status':'Resolvido'}).context['page_obj'])
        self.assertFalse(self.client.get(self.url,{'fila':'minha','equipe':self.alheia.pk}).context['page_obj'])

    def test_paginacao_preserva_todos_os_filtros_com_encoding(self):
        for _ in range(11):self.chamado()
        filtros={'fila':'minha','q':'Rede & acesso','categoria':'Rede','status':'Aberto',
            'equipe':str(self.equipe.pk),'ordenacao':'interacao_recente'}
        r=self.client.get(self.url,filtros)
        links=re.findall(r'href="([^"]+)"',r.content.decode())
        prox=next(x for x in links if 'page=2' in x)
        parametros=parse_qs(urlsplit(unescape(prox)).query)
        for chave,valor in filtros.items():self.assertEqual(parametros[chave],[valor])
        r=self.client.get(unescape(prox));self.assertEqual(len(r.context['page_obj']),1)

    def test_administrador_ve_so_sua_fila_e_limpar_volta_ao_padrao(self):
        meu=self.chamado(tecnico=self.admin,equipe=self.alheia)
        outro=self.chamado()
        self.client.force_login(self.admin)
        r=self.client.get(self.url,{'fila':'minha'})
        self.assertEqual([x.pk for x in r.context['page_obj']],[meu.pk])
        self.assertContains(r,'Remover todos os filtros')
        self.assertEqual({x.pk for x in self.client.get(self.url).context['page_obj']},{meu.pk,outro.pk})

    def test_cliente_nao_recebe_seletor_e_parametro_nao_vaza_atendimentos(self):
        self.chamado();self.client.force_login(self.cliente)
        self.assertNotContains(self.client.get(self.url),'name="fila"')
        self.assertFalse(self.client.get(self.url,{'fila':'minha'}).context['page_obj'])
        self.client.logout();self.assertEqual(self.client.get(self.url,{'fila':'minha'}).status_code,302)

    def test_valor_invalido_mantem_padrao_e_ausencia_de_vinculo_nao_amplia_acesso(self):
        meu=self.chamado()
        r=self.client.get(self.url,{'fila':'desconhecida'})
        self.assertEqual(r.context['fila_filter'],'')
        self.assertEqual([x.pk for x in r.context['page_obj']],[meu.pk])
        IntegranteEquipe.objects.filter(usuario=self.tec).delete()
        self.assertFalse(self.client.get(self.url,{'fila':'minha'}).context['page_obj'])
