import csv
from datetime import datetime, timedelta, timezone as datetime_timezone
from html import unescape
from io import StringIO
import re
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .atendimento import alterar_situacao, reabrir_atendimento
from .models import Chamado, CicloAtendimento, Comentario, Equipe, IntegranteEquipe


class ExportacaoIndicadoresTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('admin-csv', password=None)
        self.tecnico = User.objects.create_user('tecnico-csv', is_staff=True, first_name='João', last_name='Silva')
        self.equipe = Equipe.objects.get(triagem_padrao=True)
        IntegranteEquipe.objects.create(equipe=self.equipe, usuario=self.tecnico)
        self.url = reverse('exportar_indicadores_csv')
        self.painel = reverse('indicadores_administracao')
        self.client.force_login(self.admin)

    def ciclo(self, **campos):
        agora = timezone.now()
        chamado = campos.pop('chamado', None) or Chamado.objects.create(
            titulo='Conexão da impressora', descricao='Descrição que não deve ser exportada',
            solicitante=self.admin, tecnico=self.tecnico, equipe=self.equipe)
        dados = dict(numero=1, equipe=self.equipe, fechado_por=self.tecnico,
            prioridade='Normal', status='Resolvido', data_criacao=agora-timedelta(hours=2),
            data_atualizacao=agora, data_vencimento=agora, data_fechamento=agora)
        dados.update(campos)
        return CicloAtendimento.objects.create(chamado=chamado, **dados)

    def linhas(self, resposta):
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta['Content-Type'], 'text/csv; charset=utf-8')
        self.assertTrue(resposta.content.startswith(b'\xef\xbb\xbf'))
        return list(csv.DictReader(StringIO(resposta.content.decode('utf-8-sig'), newline=''), delimiter=';'))

    def test_acesso_exclusivo_de_administrador_ativo_e_metodo_get(self):
        self.ciclo()
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        coordenador = User.objects.create_user('coordenador-csv', is_staff=True)
        IntegranteEquipe.objects.create(equipe=self.equipe, usuario=coordenador, coordenador=True)
        for usuario in (self.tecnico, coordenador, User.objects.create_user('cliente-csv')):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                r = self.client.get(self.url)
                self.assertEqual(r.status_code, 403)
                self.assertNotIn('Content-Disposition', r)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertEqual(len(self.linhas(self.client.get(self.url))), 1)
        self.admin.is_active = False
        self.admin.save(update_fields=['is_active'])
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_filtros_invalidos_voltam_ao_formulario_sem_baixar_arquivo(self):
        self.ciclo()
        for dados in ({'periodo': 'invalido'}, {'periodo': 'personalizado'},
                {'periodo': 'personalizado', 'inicio': '2025-03-03', 'fim': '2025-03-01'},
                {'periodo': 'personalizado', 'inicio': '2025-02-30', 'fim': '2025-03-01'},
                {'periodo': 'personalizado', 'inicio': '2025-03-01', 'fim': '9999-12-31'},
                {'equipe': '99999999'}, {'equipe': 'abc'}):
            with self.subTest(dados=dados):
                r = self.client.get(self.url, dados)
                self.assertEqual(r.status_code, 400)
                self.assertNotIn('Content-Disposition', r)
                self.assertContains(r, 'Corrija os filtros', status_code=400)
                self.assertContains(r, f'action="{self.painel}"', status_code=400)
                self.assertNotContains(r, 'Exportar CSV', status_code=400)

    def test_periodos_predefinidos_exportam_as_mesmas_resolucoes_da_tela(self):
        agora = timezone.make_aware(datetime(2025, 3, 15, 12))
        for dias in (0, 6, 7, 14, 15):
            self.ciclo(data_fechamento=agora-timedelta(days=dias))
        with patch('helpdesk.indicadores.timezone.localdate', return_value=agora.date()):
            for periodo, quantidade in (('hoje', 1), ('7dias', 2), ('mes', 4), ('sempre', 5)):
                with self.subTest(periodo=periodo):
                    dados = {'periodo': periodo}
                    tela = self.client.get(self.painel, dados)
                    linhas = self.linhas(self.client.get(self.url, dados))
                    self.assertEqual(len(linhas), quantidade)
                    self.assertEqual(len(linhas), tela.context['resumo']['resolvidos'])
                    self.assertEqual([(int(l['Chamado']), int(l['Ciclo'])) for l in linhas],
                        [(c.chamado_id, c.numero) for c in tela.context['pagina']])

    def test_intervalo_inclusivo_no_fuso_local_e_equipe_inativa(self):
        equipe = Equipe.objects.create(nome='Equipe histórica', ativa=False)
        with timezone.override(ZoneInfo('America/Sao_Paulo')):
            # 01h UTC de 03/03 ainda pertence a 02/03 em São Paulo.
            for instante in (datetime(2025, 3, 1, 3), datetime(2025, 3, 3, 1), datetime(2025, 3, 3, 3)):
                self.ciclo(equipe=equipe, data_fechamento=instante.replace(tzinfo=datetime_timezone.utc))
            self.ciclo(data_fechamento=timezone.make_aware(datetime(2025, 3, 2)))
            dados = {'periodo': 'personalizado', 'inicio': '2025-03-01', 'fim': '2025-03-02', 'equipe': equipe.pk}
            linhas = self.linhas(self.client.get(self.url, dados))
            self.assertEqual(len(linhas), 2)
            self.assertEqual({l['Equipe'] for l in linhas}, {'Equipe histórica'})
            self.assertEqual(linhas[0]['Fechamento'], '2025-03-02T22:00:00-03:00')
            self.assertEqual(linhas[1]['Fechamento'], '2025-03-01T00:00:00-03:00')
            self.assertEqual(self.client.get(self.painel, dados).context['resumo']['resolvidos'], len(linhas))

    def test_csv_inclui_todas_as_paginas_e_link_preserva_apenas_filtros(self):
        for _ in range(28):
            self.ciclo()
        dados = {'periodo': 'sempre', 'equipe': self.equipe.pk, 'page': 2, 'page_sla': 3, 'extra': 'ignorar'}
        tela = self.client.get(self.painel, dados)
        self.assertEqual(len(tela.context['pagina']), 3)
        link = unescape(re.search(r'href="([^"]*exportar\.csv[^\"]*)"', tela.content.decode()).group(1))
        self.assertEqual(parse_qs(urlsplit(link).query), {'periodo': ['sempre'], 'equipe': [str(self.equipe.pk)]})
        linhas = self.linhas(self.client.get(link))
        self.assertEqual(len(linhas), 28)
        esperados = list(CicloAtendimento.objects.order_by('-data_fechamento', '-pk').values_list('chamado_id', flat=True))
        self.assertEqual([int(l['Chamado']) for l in linhas], esperados)
        self.assertEqual(self.linhas(self.client.get(self.url, dados)), linhas)

    def test_reabertura_e_transferencia_preservam_ciclos_e_autores_historicos(self):
        primeiro = self.ciclo()
        chamado = primeiro.chamado
        Chamado.objects.filter(pk=chamado.pk).update(status='Resolvido', data_fechamento=primeiro.data_fechamento,
            fechado_por=self.tecnico)
        chamado.refresh_from_db()
        reaberto = reabrir_atendimento(chamado, self.admin, 'O problema retornou',
            versao_esperada=chamado.versao_status, atribuicao_esperada=chamado.versao_atribuicao)
        destino = Equipe.objects.create(nome='Outra equipe')
        outro = User.objects.create_user('outro-csv', is_staff=True)
        Chamado.objects.filter(pk=reaberto.pk).update(equipe=destino, tecnico=outro)
        reaberto.refresh_from_db()
        alterar_situacao(reaberto, outro, 'Resolvido', notificar=False)
        self.tecnico.is_active = False
        self.tecnico.save(update_fields=['is_active'])
        linhas = self.linhas(self.client.get(self.url, {'periodo': 'sempre'}))
        self.assertEqual([(l['Chamado'], l['Ciclo'], l['Equipe'], l['Resolvido por']) for l in linhas], [
            (str(chamado.pk), '2', destino.nome, 'outro-csv'),
            (str(chamado.pk), '1', self.equipe.nome, 'João Silva')])
        antigas = self.linhas(self.client.get(self.url, {'periodo': 'sempre', 'equipe': self.equipe.pk}))
        self.assertEqual(antigas, [linhas[1]])

    def test_igualdade_de_sla_ausencias_e_legado_sem_fechamento(self):
        agora = timezone.now()
        self.ciclo(data_vencimento=agora, data_fechamento=agora)
        self.ciclo(status='Fechado', data_vencimento=agora-timedelta(seconds=1), data_fechamento=agora)
        self.ciclo(data_vencimento=None, fechado_por=None)
        self.ciclo(data_fechamento=None)
        linhas = self.linhas(self.client.get(self.url, {'periodo': 'sempre'}))
        self.assertCountEqual([l['SLA'] for l in linhas], ['Dentro do SLA', 'Fora do SLA', 'Sem dados de SLA', 'Sem dados de SLA'])
        self.assertEqual(sum(l['Status do ciclo'] == 'Fechado' for l in linhas), 1)
        sem_prazo = next(l for l in linhas if l['Resolvido por'] == 'Não registrado')
        self.assertEqual(sem_prazo['Vencimento'], '')
        self.assertEqual(sum(l['Fechamento'] == '' for l in linhas), 1)
        self.assertEqual(len(self.linhas(self.client.get(self.url, {'periodo': 'hoje'}))), 3)

    def test_acentos_aspas_quebras_e_separadores_sem_expor_conversa(self):
        ciclo = self.ciclo()
        titulo = 'Conexão; "São Paulo"\nImpressora'
        Chamado.objects.filter(pk=ciclo.chamado_id).update(titulo=titulo)
        Comentario.objects.create(chamado=ciclo.chamado, autor=self.tecnico,
            texto='Nota interna confidencial', interna=True)
        resposta = self.client.get(self.url, {'periodo': 'sempre'})
        linha, = self.linhas(resposta)
        self.assertEqual(linha['Título'], titulo)
        self.assertEqual(linha['Resolvido por'], 'João Silva')
        self.assertNotIn('Nota interna confidencial', resposta.content.decode())
        self.assertNotIn('Descrição que não deve ser exportada', resposta.content.decode())
        self.assertEqual(list(linha), ['Chamado', 'Ciclo', 'Título', 'Equipe', 'Resolvido por',
            'Status do ciclo', 'Início do ciclo', 'Vencimento', 'Fechamento', 'SLA'])

    def test_formulas_em_titulo_equipe_e_nome_sao_exportadas_como_texto(self):
        entradas = ['=1+1', '+1+1', '-1+1', '@SUM(1)', '  =1+1', '\t=1+1', '\r=1+1', '\n=1+1',
            '＝1+1', '＋1+1', '－1+1', '＠SUM(1)', '=1+2";=1+2']
        self.equipe.nome = '=HYPERLINK("https://example.invalid")'
        self.equipe.save(update_fields=['nome'])
        self.tecnico.first_name = '+1+1'
        self.tecnico.last_name = ''
        self.tecnico.save(update_fields=['first_name', 'last_name'])
        for texto in entradas:
            ciclo = self.ciclo()
            Chamado.objects.filter(pk=ciclo.chamado_id).update(titulo=texto)
        linhas = self.linhas(self.client.get(self.url, {'periodo': 'sempre'}))
        self.assertCountEqual([l['Título'] for l in linhas], ['\t'+s for s in entradas])
        self.assertEqual({l['Equipe'] for l in linhas}, {'\t'+self.equipe.nome})
        self.assertEqual({l['Resolvido por'] for l in linhas}, {'\t+1+1'})

    def test_exportacao_vazia_tem_cabecalho_download_e_cache_privado(self):
        resposta = self.client.get(self.url)
        self.assertEqual(self.linhas(resposta), [])
        self.assertEqual(len(list(csv.reader(StringIO(resposta.content.decode('utf-8-sig')), delimiter=';'))), 1)
        self.assertRegex(resposta['Content-Disposition'], r'^attachment; filename="nexaltri-resolucoes-\d{4}-\d{2}-\d{2}\.csv"$')
        self.assertIn('private', resposta['Cache-Control'])
        self.assertIn('no-store', resposta['Cache-Control'])
        self.assertEqual(resposta['X-Content-Type-Options'], 'nosniff')

    def test_sem_parametros_usa_o_mes_atual_como_a_tela(self):
        agora = timezone.make_aware(datetime(2025, 3, 15, 12))
        incluido = self.ciclo(data_fechamento=agora)
        self.ciclo(data_fechamento=agora-timedelta(days=20))
        with patch('helpdesk.indicadores.timezone.localdate', return_value=agora.date()):
            linha, = self.linhas(self.client.get(self.url))
            self.assertEqual(linha['Chamado'], str(incluido.chamado_id))
            self.assertEqual(self.client.get(self.painel).context['resumo']['resolvidos'], 1)
