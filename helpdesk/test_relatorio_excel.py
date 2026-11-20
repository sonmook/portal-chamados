from datetime import datetime, timedelta, timezone as utc
from io import BytesIO
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import test_exportacao_indicadores as fixtures
from .atendimento import alterar_situacao, reabrir_atendimento
from .models import Chamado, Comentario, Equipe, IntegranteEquipe

S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
C = '{http://schemas.openxmlformats.org/drawingml/2006/chart}'


class Livro:
    def __init__(self, conteudo):
        with ZipFile(BytesIO(conteudo)) as z:
            assert z.testzip() is None
            self.partes = {p: z.read(p) for p in z.namelist()}
        strings = ET.fromstring(self.partes['xl/sharedStrings.xml'])
        self.textos = [''.join(n.itertext()) for n in strings]

    def xml(self, nome):
        return ET.fromstring(self.partes[nome])

    def celulas(self, numero):
        resultado = {}
        for c in self.xml(f'xl/worksheets/sheet{numero}.xml').iter(S+'c'):
            valor = c.find(S+'v')
            if c.get('t') == 'inlineStr':
                resultado[c.get('r')] = ''.join(c.find(S+'is').itertext())
            elif valor is not None:
                if c.get('t') == 's':
                    resultado[c.get('r')] = self.textos[int(valor.text)]
                elif c.get('t') == 'str':
                    resultado[c.get('r')] = valor.text
                else:
                    resultado[c.get('r')] = float(valor.text)
        return resultado

    def tabela(self, nome):
        return next(self.xml(p) for p in self.partes if p.startswith('xl/tables/') and self.xml(p).get('name') == nome)


class RelatorioExcelTests(TestCase):
    ciclo = fixtures.ExportacaoIndicadoresTests.ciclo

    def setUp(self):
        fixtures.ExportacaoIndicadoresTests.setUp(self)
        self.excel = reverse('exportar_indicadores_excel')

    def livro(self, filtros=None):
        r = self.client.get(self.excel, filtros or {'periodo': 'sempre'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        return Livro(r.content)

    def test_apenas_administrador_ativo_get_e_resposta_privada(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.excel).status_code, 302)
        coordenador = User.objects.create_user('coord-excel', is_staff=True)
        IntegranteEquipe.objects.create(equipe=self.equipe, usuario=coordenador, coordenador=True)
        for usuario in (self.tecnico, coordenador, User.objects.create_user('cliente-excel')):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(self.excel).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.excel).status_code, 405)
        r = self.client.get(self.excel)
        self.assertRegex(r['Content-Disposition'], r'attachment; filename="nexaltri-indicadores-\d{4}-\d{2}-\d{2}\.xlsx"')
        self.assertIn('private', r['Cache-Control'])
        self.assertIn('no-store', r['Cache-Control'])
        self.admin.is_active = False
        self.admin.save(update_fields=['is_active'])
        self.assertEqual(self.client.get(self.excel).status_code, 302)

    def test_filtros_invalidos_exibem_formulario_sem_download(self):
        for dados in ({'periodo': 'desconhecido'}, {'periodo': 'personalizado'},
                {'periodo': 'personalizado', 'inicio': '2025-03-02', 'fim': '2025-03-01'},
                {'periodo': 'personalizado', 'inicio': '2025-03-01', 'fim': '9999-12-31'},
                {'equipe': '99999999'}):
            with self.subTest(dados=dados):
                r = self.client.get(self.excel, dados)
                self.assertContains(r, 'Corrija os filtros', status_code=400)
                self.assertNotIn('Content-Disposition', r)

    def test_resumo_concilia_metricas_da_tela_e_separa_fila_atual(self):
        agora = timezone.now()
        self.ciclo(data_fechamento=agora, data_vencimento=agora)
        self.ciclo(data_fechamento=agora, data_vencimento=agora-timedelta(hours=1))
        self.ciclo(data_vencimento=None)
        Chamado.objects.filter(pk=1).update(data_criacao=agora-timedelta(days=80))
        tela = self.client.get(self.painel, {'periodo': 'hoje'})
        resumo = tela.context['resumo']
        livro = self.livro({'periodo': 'hoje'})
        celulas = livro.celulas(1)
        for endereco, chave in (('B9', 'criados'), ('F9', 'resolvidos'), ('B13', 'ativos'),
                ('F13', 'sem_responsavel'), ('J13', 'ativos_vencidos'), ('B17', 'tmr_horas'),
                ('F17', 'fora_sla'), ('J17', 'sem_sla')):
            self.assertEqual(celulas[endereco], resumo[chave])
        self.assertEqual(celulas['J9'], resumo['sla_percentual']/100)
        self.assertEqual(celulas['C38']+celulas['C39']+celulas['C40'], resumo['resolvidos'])

    def test_periodos_e_padrao_mensal_compartilham_regras_da_tela(self):
        agora = timezone.make_aware(datetime(2025, 3, 15, 12))
        for dias in (0, 6, 7, 14, 15):
            self.ciclo(data_fechamento=agora-timedelta(days=dias))
        with patch('helpdesk.indicadores.timezone.localdate', return_value=agora.date()):
            for periodo, quantidade in (('hoje', 1), ('7dias', 2), ('mes', 4), ('sempre', 5)):
                with self.subTest(periodo=periodo):
                    self.assertEqual(self.livro({'periodo': periodo}).celulas(1)['F9'], quantidade)
            self.assertEqual(Livro(self.client.get(self.excel).content).celulas(1)['F9'], 4)

    def test_datas_numericas_no_fuso_local_e_equipe_inativa(self):
        equipe = Equipe.objects.create(nome='Histórica Excel', ativa=False)
        with timezone.override(ZoneInfo('America/Sao_Paulo')):
            self.ciclo(equipe=equipe, data_fechamento=datetime(2025, 3, 3, 1, tzinfo=utc.utc))
            self.ciclo(equipe=equipe, data_fechamento=datetime(2025, 3, 3, 3, tzinfo=utc.utc))
            filtros = {'periodo': 'personalizado', 'inicio': '2025-03-01', 'fim': '2025-03-02', 'equipe': equipe.pk}
            livro = self.livro(filtros)
            self.assertEqual(livro.celulas(1)['F9'], 1)
            self.assertEqual(livro.celulas(2)['B9'], 'Histórica Excel (Inativa)')
            self.assertEqual(datetime(1899, 12, 30)+timedelta(days=livro.celulas(3)['J9']), datetime(2025, 3, 2, 22))
            self.assertIn('America/Sao_Paulo', livro.celulas(3)['B5'])

    def test_todos_registros_tabelas_filtros_e_linhas_fixadas(self):
        for _ in range(29):
            self.ciclo()
        livro = self.livro({'periodo': 'sempre', 'page': 2, 'page_sla': 9})
        self.assertEqual(livro.tabela('Resolucoes').get('ref'), 'B8:L37')
        self.assertEqual(livro.tabela('Resolucoes').find(S+'autoFilter').get('ref'), 'B8:L37')
        valores = livro.celulas(3)
        self.assertEqual(sum(f'B{n}' in valores for n in range(9, 38)), 29)
        pane = livro.xml('xl/worksheets/sheet3.xml').find(f'{S}sheetViews/{S}sheetView/{S}pane')
        self.assertEqual((pane.get('xSplit'), pane.get('ySplit')), ('3', '8'))
        self.assertEqual(livro.xml('xl/worksheets/sheet3.xml').find(S+'conditionalFormatting').get('sqref'), 'K9:K37')

    def test_reabertura_preserva_equipe_e_autor_de_cada_ciclo(self):
        ciclo = self.ciclo()
        ticket = ciclo.chamado
        Chamado.objects.filter(pk=ticket.pk).update(status='Resolvido', data_fechamento=ciclo.data_fechamento, fechado_por=self.tecnico)
        ticket.refresh_from_db()
        ticket = reabrir_atendimento(ticket, self.admin, 'O problema retornou',
            versao_esperada=ticket.versao_status, atribuicao_esperada=ticket.versao_atribuicao)
        outra = Equipe.objects.create(nome='Novo atendimento')
        novo = User.objects.create_user('novo-excel', is_staff=True)
        Chamado.objects.filter(pk=ticket.pk).update(equipe=outra, tecnico=novo)
        ticket.refresh_from_db()
        alterar_situacao(ticket, novo, 'Resolvido', notificar=False)
        self.tecnico.is_active = False
        self.tecnico.save(update_fields=['is_active'])
        livro = self.livro()
        c = livro.celulas(3)
        self.assertEqual((c['C9'], c['E9'], c['F9']), (2, outra.nome, novo.username))
        self.assertEqual((c['C10'], c['E10'], c['F10']), (1, self.equipe.nome, 'João Silva'))
        self.assertEqual(self.livro({'periodo': 'sempre', 'equipe': self.equipe.pk}).celulas(1)['F9'], 1)

    def test_dados_ausentes_nao_viram_zeros_nem_sla_cumprido(self):
        self.ciclo(data_fechamento=None, data_vencimento=None, fechado_por=None)
        livro = self.livro()
        self.assertEqual(livro.celulas(1)['J9'], 'Sem dados')
        self.assertEqual(livro.celulas(1)['B17'], 'Sem dados')
        self.assertEqual(livro.celulas(1)['J17'], 1)
        dados = livro.celulas(3)
        self.assertNotIn('I9', dados)
        self.assertNotIn('J9', dados)
        self.assertNotIn('L9', dados)
        self.assertEqual(dados['F9'], 'Não registrado')
        self.assertEqual(dados['K9'], 'Sem dados de SLA')

    def test_texto_literal_nao_vira_formula_url_ou_xml_e_notas_nao_vazam(self):
        titulo = '=HYPERLINK("https://example.invalid") <&>\nSão Paulo\x00'
        c = self.ciclo()
        Chamado.objects.filter(pk=c.chamado_id).update(titulo=titulo)
        Comentario.objects.create(chamado=c.chamado, autor=self.tecnico, interna=True, texto='Segredo interno fora da planilha')
        livro = self.livro()
        self.assertEqual(livro.celulas(3)['D9'], titulo.replace('\x00', '\ufffd'))
        celula = next(c for c in livro.xml('xl/worksheets/sheet3.xml').iter(S+'c') if c.get('r') == 'D9')
        self.assertEqual(celula.get('t'), 'inlineStr')
        self.assertIsNone(celula.find(S+'f'))
        self.assertFalse(any('externalLinks' in p or p.endswith('vbaProject.bin') for p in livro.partes))
        self.assertFalse(any(b'Segredo interno fora da planilha' in conteudo or 'Descrição que não deve ser exportada'.encode() in conteudo for conteudo in livro.partes.values()))

    def test_graficos_nativos_caches_e_identidade_visual(self):
        self.ciclo()
        self.ciclo(data_vencimento=None)
        livro = self.livro()
        self.assertEqual([s.get('name') for s in livro.xml('xl/workbook.xml').find(S+'sheets')], ['Resumo', 'Desempenho', 'Resoluções'])
        graficos = sorted(p for p in livro.partes if '/charts/chart' in p and p.endswith('.xml'))
        self.assertEqual(len(graficos), 2)
        valores = livro.xml(graficos[0]).findall(f'.//{C}numCache/{C}pt/{C}v')
        self.assertEqual([float(v.text) for v in valores], [1, 0, 1])
        self.assertTrue(any(p.startswith('xl/media/') and conteudo.startswith(b'\x89PNG') for p, conteudo in livro.partes.items()))
        estilos = livro.partes['xl/styles.xml'].decode()
        for cor in ('101D37', '14B8A6', 'F4F7FB'):
            self.assertIn(cor, estilos)

    def test_impressao_tem_configuracao_unica_e_ordenada_em_cada_aba(self):
        # Excel rejeita pageMargins duplicado, mesmo com XML bem formado e ZIP válido.
        livro = self.livro()
        for numero, tamanho, orientacao in ((1, '9', 'portrait'), (2, '8', 'portrait'), (3, '8', 'landscape')):
            with self.subTest(aba=numero):
                folha = livro.xml(f'xl/worksheets/sheet{numero}.xml')
                self.assertEqual(len(folha.findall(S+'pageMargins')), 1)
                self.assertEqual(len(folha.findall(S+'pageSetup')), 1)
                self.assertEqual(len(folha.findall(S+'sheetPr/'+S+'pageSetUpPr')), 1)
                margens = folha.find(S+'pageMargins')
                pagina = folha.find(S+'pageSetup')
                self.assertEqual(margens.get('left'), '0.25')
                self.assertEqual(pagina.get('paperSize'), tamanho)
                self.assertEqual(pagina.get('orientation'), orientacao)
                self.assertEqual(pagina.get('fitToWidth'), '1')
                self.assertLess(list(folha).index(margens), list(folha).index(pagina))
                self.assertLess(list(folha).index(pagina), list(folha).index(folha.find(S+'drawing')))

    def test_vazio_mantem_resumo_legivel_e_sem_dados_inventados(self):
        livro = self.livro()
        self.assertEqual(livro.celulas(1)['B9'], 0)
        self.assertEqual(livro.celulas(1)['F9'], 0)
        self.assertEqual(livro.celulas(1)['J9'], 'Sem dados')
        self.assertIn('Nenhuma resolução', livro.celulas(3)['D9'])
        self.assertEqual(livro.tabela('Resolucoes').get('ref'), 'B8:L9')

    def test_botao_do_relatorio_preserva_filtros_aplicados(self):
        r = self.client.get(self.painel, {'periodo': 'sempre', 'equipe': self.equipe.pk, 'page': 2})
        self.assertContains(r, 'Exportar Excel formatado')
        self.assertContains(r, f'{self.excel}?periodo=sempre&amp;equipe={self.equipe.pk}')
