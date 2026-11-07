from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.db import OperationalError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Chamado, Equipe, IntegranteEquipe, Notificacao
from .notificacoes import notificacoes_visiveis
from .sla import filtrar_sla, processar_alertas_sla, processar_chamado, contadores
from .test_helpers import dados_atribuicao


class AlertasSLATests(TestCase):
    def setUp(self):
        self.agora=timezone.now()
        self.equipe=Equipe.objects.get(triagem_padrao=True)
        self.tec=User.objects.create_user('sla-tecnico',is_staff=True)
        self.coord=User.objects.create_user('sla-coord',is_staff=True)
        self.cliente=User.objects.create_user('sla-cliente')
        self.admin=User.objects.create_superuser('sla-admin','sla@example.invalid',None)
        IntegranteEquipe.objects.create(equipe=self.equipe,usuario=self.tec)
        IntegranteEquipe.objects.create(equipe=self.equipe,usuario=self.coord,coordenador=True)

    def chamado(self, minutos=30, **extra):
        dados=dict(titulo='Rede & acesso',descricao='Fixture SLA',solicitante=self.cliente,
            tecnico=self.tec,equipe=self.equipe,data_vencimento=self.agora+timedelta(minutes=minutos),categoria='Rede')
        dados.update(extra)
        return Chamado.objects.create(**dados)

    def processar(self):
        return processar_alertas_sla(self.agora)

    def test_limites_da_janela_e_transicao_para_vencido(self):
        fora=self.chamado(60);Chamado.objects.filter(pk=fora.pk).update(data_vencimento=self.agora+timedelta(hours=1,microseconds=1))
        limite=self.chamado(60);exato=self.chamado(0);vencido=self.chamado(-1)
        resultado=self.processar()
        self.assertEqual(resultado['sla_proximo'],2);self.assertEqual(resultado['sla_vencido'],1)
        self.assertEqual(set(Notificacao.objects.filter(tipo='sla_proximo').values_list('chamado_id',flat=True)),{limite.pk,exato.pk})
        self.assertEqual(Notificacao.objects.get(tipo='sla_vencido').chamado_id,vencido.pk)
        self.assertEqual(processar_alertas_sla(self.agora+timedelta(seconds=1))['sla_vencido'],1)

    def test_somente_responsavel_ativo_recebe_aviso_de_prazo(self):
        self.chamado();self.processar()
        self.assertEqual(list(Notificacao.objects.values_list('destinatario_id',flat=True)),[self.tec.pk])

    def test_sem_responsavel_avisa_coordenadores_e_nao_todos_os_membros(self):
        t=self.chamado(2880,tecnico=None);self.processar()
        aviso=Notificacao.objects.get();self.assertEqual((aviso.tipo,aviso.destinatario_id),('sem_responsavel',self.coord.pk))
        Chamado.objects.filter(pk=t.pk).update(data_vencimento=self.agora-timedelta(seconds=1))
        self.processar()
        self.assertEqual(set(Notificacao.objects.values_list('tipo',flat=True)),{'sem_responsavel','sla_vencido'})
        self.assertFalse(Notificacao.objects.exclude(destinatario=self.coord).exists())

    def test_coordenador_inativo_sem_papel_ou_sem_vinculo_nao_recebe(self):
        self.chamado(tecnico=None)
        User.objects.filter(pk=self.coord.pk).update(is_active=False)
        self.processar();self.assertFalse(Notificacao.objects.exists())
        User.objects.filter(pk=self.coord.pk).update(is_active=True,is_staff=False)
        self.processar();self.assertFalse(Notificacao.objects.exists())
        User.objects.filter(pk=self.coord.pk).update(is_staff=True)
        IntegranteEquipe.objects.filter(usuario=self.coord).delete()
        self.processar();self.assertFalse(Notificacao.objects.exists())

    def test_tecnico_inativo_sem_papel_ou_sem_vinculo_nao_recebe(self):
        self.chamado()
        User.objects.filter(pk=self.tec.pk).update(is_active=False)
        self.processar();self.assertFalse(Notificacao.objects.exists())
        User.objects.filter(pk=self.tec.pk).update(is_active=True,is_staff=False)
        self.processar();self.assertFalse(Notificacao.objects.exists())
        User.objects.filter(pk=self.tec.pk).update(is_staff=True)
        IntegranteEquipe.objects.filter(usuario=self.tec).delete()
        self.processar();self.assertFalse(Notificacao.objects.exists())

    def test_finalizados_e_equipes_inativas_nao_geram_alertas(self):
        self.chamado(-10,status='Resolvido');self.chamado(-10,status='Fechado',tecnico=None)
        self.assertEqual(self.processar(),contadores())
        self.chamado(-10)
        Equipe.objects.filter(pk=self.equipe.pk).update(ativa=False)
        self.assertEqual(self.processar(),contadores())

    def test_prazo_nulo_nao_gera_sla_mas_permite_aviso_sem_responsavel(self):
        t=self.chamado(tecnico=None)
        Chamado.objects.filter(pk=t.pk).update(data_vencimento=None)
        self.processar();self.assertEqual(Notificacao.objects.get().tipo,'sem_responsavel')

    def test_repeticao_e_leitura_nao_duplicam_avisos(self):
        self.chamado();self.processar()
        Notificacao.objects.update(lida_em=self.agora)
        self.assertEqual(self.processar()['sla_proximo'],0)
        self.assertEqual(Notificacao.objects.count(),1)

    def test_prazo_alterado_e_novo_responsavel_recebem_novo_aviso(self):
        t=self.chamado();self.processar()
        Chamado.objects.filter(pk=t.pk).update(data_vencimento=self.agora+timedelta(minutes=45))
        self.processar();self.assertEqual(Notificacao.objects.count(),2)
        Chamado.objects.filter(pk=t.pk).update(tecnico=self.coord)
        self.processar();self.assertEqual(Notificacao.objects.filter(destinatario=self.coord).count(),1)
        Chamado.objects.filter(pk=t.pk).update(tecnico=self.tec)
        self.assertEqual(self.processar()['sla_proximo'],0)

    def redistribuir(self,t,tecnico):
        self.client.force_login(self.admin)
        return self.client.post(reverse('redistribuir_chamado',args=[t.pk]),{
            **dados_atribuicao(t),'tecnico':tecnico.pk if tecnico else '',
            'responsavel_anterior':t.tecnico_id or '', 'motivo':'Validação de ciclo de atribuição'})

    def test_novo_ciclo_sem_responsavel_avisa_novamente_e_noop_nao(self):
        t=self.chamado(2880,tecnico=None);self.processar()
        self.assertEqual(self.redistribuir(t,None).status_code,200)
        t.refresh_from_db();self.assertEqual(t.versao_atribuicao,0)
        self.processar();self.assertEqual(Notificacao.objects.filter(tipo='sem_responsavel').count(),1)
        self.assertEqual(self.redistribuir(t,self.tec).status_code,302)
        self.assertEqual(self.redistribuir(t,None).status_code,302)
        self.processar();self.assertEqual(Notificacao.objects.filter(tipo='sem_responsavel').count(),2)

    def test_transferencia_avisa_coordenador_destino_e_oculta_aviso_antigo(self):
        t=self.chamado(tecnico=None);self.processar()
        destino=Equipe.objects.get(nome='Infraestrutura e Redes')
        IntegranteEquipe.objects.create(equipe=destino,usuario=self.tec,coordenador=True)
        Chamado.objects.filter(pk=t.pk).update(equipe=destino)
        self.processar()
        self.assertEqual(Notificacao.objects.filter(destinatario=self.tec).count(),2)
        self.assertFalse(notificacoes_visiveis(self.coord).exists())

    def test_estado_e_equipe_revalidados_apos_selecao(self):
        t=self.chamado()
        self.assertEqual(processar_chamado(t.pk,999,self.agora),contadores())
        Chamado.objects.filter(pk=t.pk).update(status='Fechado')
        self.assertEqual(processar_chamado(t.pk,self.equipe.pk,self.agora),contadores())
        self.assertFalse(Notificacao.objects.exists())

    def test_falha_reverte_avisos_do_mesmo_chamado(self):
        self.chamado(tecnico=None)
        from .notificacoes import gerar
        def falha(chamado,ator,tipo,evento,destinatarios):
            gerar(chamado,ator,tipo,evento,destinatarios)
            if tipo=='sla_proximo':raise RuntimeError('Fixture rollback')
        with patch('helpdesk.sla.gerar',side_effect=falha), self.assertRaises(RuntimeError):self.processar()
        self.assertFalse(Notificacao.objects.exists())

    def test_filtros_combinados_respeitam_acesso_e_nao_geram_avisos(self):
        esperado=self.chamado(status='Em Andamento')
        self.chamado(-1);self.chamado(180);self.chamado(tecnico=self.coord)
        self.chamado(status='Resolvido');self.chamado(equipe=Equipe.objects.get(nome='Infraestrutura e Redes'))
        self.client.force_login(self.tec)
        r=self.client.get(reverse('lista_chamados'),{'fila':'minha','sla':'proximos','q':'Rede & acesso',
            'categoria':'Rede','equipe':self.equipe.pk,'status':'Em Andamento'})
        self.assertEqual([t.pk for t in r.context['page_obj']],[esperado.pk])
        self.assertContains(r,'até 1h');self.assertFalse(Notificacao.objects.exists())
        self.assertFalse(self.client.get(reverse('lista_chamados'),{'sla':'vencidos','status':'Resolvido'}).context['page_obj'])

    def test_filtro_vencidos_e_invalido_e_limpar(self):
        vencido=self.chamado(-1);self.chamado(30);self.chamado(-1,status='Fechado')
        self.client.force_login(self.tec);url=reverse('lista_chamados')
        self.assertEqual([t.pk for t in self.client.get(url,{'sla':'vencidos'}).context['page_obj']],[vencido.pk])
        r=self.client.get(url,{'sla':'inventado'})
        self.assertEqual(r.context['sla_filter'],'');self.assertEqual(len(r.context['page_obj']),3)
        self.assertEqual(len(self.client.get(url).context['page_obj']),3)

    def test_filtro_cliente_nao_amplia_acesso(self):
        meu=self.chamado();self.chamado(solicitante=self.coord)
        self.client.force_login(self.cliente)
        r=self.client.get(reverse('lista_chamados'),{'sla':'proximos'})
        self.assertEqual([t.pk for t in r.context['page_obj']],[meu.pk])

    def test_paginacao_preserva_filtros_sla_e_encoding(self):
        from html import unescape
        import re
        from urllib.parse import urlsplit,parse_qs
        for _ in range(11):self.chamado()
        self.client.force_login(self.tec)
        r=self.client.get(reverse('lista_chamados'),{'sla':'proximos','fila':'minha','q':'Rede & acesso'})
        link=next(x for x in re.findall(r'href="([^"]+)"',r.content.decode()) if 'page=2' in x)
        query=parse_qs(urlsplit(unescape(link)).query)
        self.assertEqual(query['sla'],['proximos']);self.assertEqual(query['q'],['Rede & acesso'])
        self.assertEqual(query['fila'],['minha'])
        self.assertEqual(len(self.client.get(unescape(link)).context['page_obj']),1)

    def test_comando_uma_vez(self):
        self.chamado();saida=StringIO()
        call_command('processar_alertas_sla',stdout=saida)
        self.assertIn('próximos: 1',saida.getvalue())
        self.assertEqual(Notificacao.objects.count(),1)

    def test_comando_continuo_intervalo_e_interrupcao(self):
        with patch('helpdesk.management.commands.processar_alertas_sla.processar_alertas_sla',return_value=contadores()) as processar, patch('helpdesk.management.commands.processar_alertas_sla.time.sleep',side_effect=KeyboardInterrupt) as dormir:
            call_command('processar_alertas_sla',continuo=True,intervalo=5,stdout=StringIO())
            dormir.assert_called_once_with(5);processar.assert_called_once()
        for intervalo in (0,4,3601):
            with self.assertRaises(CommandError):call_command('processar_alertas_sla',intervalo=intervalo)

    def test_falha_banco_continuo_tenta_novamente_sem_vazar_dados(self):
        erro=StringIO()
        with patch('helpdesk.management.commands.processar_alertas_sla.processar_alertas_sla',side_effect=[OperationalError('dado privado'),contadores()]) as processar, patch('helpdesk.management.commands.processar_alertas_sla.time.sleep',side_effect=[None,KeyboardInterrupt]):
            call_command('processar_alertas_sla',continuo=True,stderr=erro,stdout=StringIO())
        self.assertEqual(processar.call_count,2);self.assertNotIn('dado privado',erro.getvalue())
        with patch('helpdesk.management.commands.processar_alertas_sla.processar_alertas_sla',side_effect=OperationalError('fixture')):
            with self.assertRaises(CommandError):call_command('processar_alertas_sla',stdout=StringIO())
