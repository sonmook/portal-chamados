"""Preenche o modelo visual XLSX versionado, preservando estilos, marca e gráficos.

O desenho é produzido por scripts/gerar_modelo_indicadores.mjs. Em execução,
somente dados, limites das tabelas e caches dos gráficos são atualizados.
"""
from copy import deepcopy
from datetime import datetime
from io import BytesIO
from math import floor, log10
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from django.utils import timezone

from core.version import VERSION

S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
C = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
ET.register_namespace('x', S)
ET.register_namespace('c', C)
ET.register_namespace('a', 'http://schemas.openxmlformats.org/drawingml/2006/main')
ET.register_namespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')
MODELO = Path(__file__).resolve().parent / 'report_templates' / 'indicadores.xlsx'
INVALIDOS_XML = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f]')


def _tag(nome):
    return f'{{{S}}}{nome}'


def _valor(celula, valor, *, formula=False):
    for filho in list(celula):
        if not formula or filho.tag != _tag('f'):
            celula.remove(filho)
    celula.attrib.pop('t', None)
    if valor is None:
        return
    if isinstance(valor, datetime):
        valor = (timezone.localtime(valor).replace(tzinfo=None) - datetime(1899, 12, 30)).total_seconds() / 86400
    if isinstance(valor, (int, float)):
        ET.SubElement(celula, _tag('v')).text = str(valor)
    elif formula:
        celula.set('t', 'str')
        ET.SubElement(celula, _tag('v')).text = str(valor)
    else:
        # Texto é sempre uma célula literal, inclusive quando começa por =, + ou @.
        celula.set('t', 'inlineStr')
        texto = ET.SubElement(ET.SubElement(celula, _tag('is')), _tag('t'))
        texto.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        texto.text = INVALIDOS_XML.sub('\ufffd', str(valor))


def _celulas(folha):
    return {c.get('r'): c for c in folha.iter(_tag('c'))}


def _linha(prototipo, numero, valores=None):
    linha = deepcopy(prototipo)
    linha.set('r', str(numero))
    for celula in linha.findall(_tag('c')):
        coluna = re.sub(r'\d+', '', celula.get('r'))
        celula.set('r', f'{coluna}{numero}')
        if valores is not None:
            _valor(celula, valores.get(coluna))
    return linha


def _tabela(arquivo, nome, primeira, ultima, coluna_final):
    raiz = next(ET.fromstring(v) for k, v in arquivo.items()
        if k.startswith('xl/tables/') and ET.fromstring(v).get('name') == nome)
    ref = f'B{primeira}:{coluna_final}{ultima}'
    raiz.set('ref', ref)
    filtro = raiz.find(_tag('autoFilter'))
    if filtro is None:
        filtro = ET.Element(_tag('autoFilter'))
        raiz.insert(0, filtro)
    filtro.set('ref', ref)
    caminho = next(k for k, v in arquivo.items() if k.startswith('xl/tables/') and ET.fromstring(v).get('name') == nome)
    arquivo[caminho] = ET.tostring(raiz, encoding='utf-8', xml_declaration=True)


def _grafico(xml, categorias, valores, coluna_categoria, coluna_valor):
    raiz = ET.fromstring(xml)
    serie = raiz.find(f'.//{{{C}}}ser')
    for tipo, referencia, cache, conteudo, coluna in (
        ('cat', 'strRef', 'strCache', categorias, coluna_categoria),
        ('val', 'numRef', 'numCache', valores, coluna_valor),
    ):
        ref = serie.find(f'{{{C}}}{tipo}/{{{C}}}{referencia}')
        ref.find(f'{{{C}}}f').text = f"'Resumo'!${coluna}$38:${coluna}${37 + len(conteudo)}"
        anterior = ref.find(f'{{{C}}}{cache}')
        if anterior is not None:
            ref.remove(anterior)
        dados = ET.SubElement(ref, f'{{{C}}}{cache}')
        if tipo == 'val':
            ET.SubElement(dados, f'{{{C}}}formatCode').text = '#,##0'
        ET.SubElement(dados, f'{{{C}}}ptCount', val=str(len(conteudo)))
        for i, valor in enumerate(conteudo):
            ponto = ET.SubElement(dados, f'{{{C}}}pt', idx=str(i))
            ET.SubElement(ponto, f'{{{C}}}v').text = INVALIDOS_XML.sub('\ufffd', str(valor))
    # Quantidades usam intervalos inteiros, sem rótulos duplicados por arredondamento.
    eixo = raiz.find(f'.//{{{C}}}valAx')
    escala = eixo.find(f'{{{C}}}scaling')
    ET.SubElement(escala, f'{{{C}}}min', val='0')
    alvo = max(1, max(valores, default=0)/5)
    ordem = 10 ** floor(log10(alvo))
    passo = next(n*ordem for n in (1, 2, 5, 10) if n*ordem >= alvo)
    ET.SubElement(eixo, f'{{{C}}}majorUnit', val=str(passo))
    return ET.tostring(raiz, encoding='utf-8', xml_declaration=True)


def _paginas(folha, *, detalhe=False, vertical=False):
    # Metadados de impressão; não alteram o tamanho dos valores ou o zoom da tela.
    pr = folha.find(_tag('sheetPr'))
    ajuste = pr.find(_tag('pageSetUpPr'))
    if ajuste is None:
        ajuste = ET.SubElement(pr, _tag('pageSetUpPr'))
    ajuste.set('fitToPage', '1')
    # O modelo já possui pageMargins. O formato permite somente um por aba;
    # reaproveitá-lo evita o aviso de recuperação do Microsoft Excel.
    margens = folha.find(_tag('pageMargins'))
    margens.attrib.update(left='0.25', right='0.25', top='0.35', bottom='0.35', header='0.15', footer='0.15')
    pagina = folha.find(_tag('pageSetup'))
    if pagina is None:
        pagina = ET.Element(_tag('pageSetup'))
        folha.insert(list(folha).index(margens)+1, pagina)
    pagina.attrib.update(paperSize='8' if detalhe else '9', orientation='portrait' if vertical or not detalhe else 'landscape', fitToWidth='1', fitToHeight='0')


def gerar_excel(relatorio, gerado_em):
    resumo = relatorio['resumo']
    with ZipFile(MODELO) as fonte:
        arquivo = {nome: fonte.read(nome) for nome in fonte.namelist()}
    folhas = [ET.fromstring(arquivo[f'xl/worksheets/sheet{i}.xml']) for i in (1, 2, 3)]
    compartilhados = ET.fromstring(arquivo['xl/sharedStrings.xml'])
    textos = [''.join(n.itertext()) for n in compartilhados]
    equipe = relatorio['equipe_selecionada']
    escopo = f"{equipe.nome if equipe else 'Todas as equipes'}. {relatorio['periodo_nome']}"
    if relatorio['inicio']:
        escopo += f". {relatorio['inicio']:%d/%m/%Y} a {relatorio['fim']:%d/%m/%Y}"
    gerado = f"Gerado em {timezone.localtime(gerado_em):%d/%m/%Y %H:%M}. Fuso: {timezone.get_current_timezone_name()}. Nexaltri {VERSION}"
    marcadores = {'{{escopo}}': escopo, '{{gerado}}': gerado,
        '{{situacao}}': f"{resumo['dentro_sla']} resoluções dentro do SLA, {resumo['fora_sla']} fora e {resumo['sem_sla']} sem dados de SLA. Taxa calculada sobre {resumo['sla_conhecidos']} resoluções com prazo e fechamento conhecidos.",
        '{{criterios}}': 'Equipes e analistas contam ciclos pela data de fechamento. Solicitantes contam aberturas no período. Vínculos são históricos; nomes exibem o cadastro atual.'}
    for folha in folhas:
        for celula in folha.iter(_tag('c')):
            valor = celula.find(_tag('v'))
            texto = None
            if celula.get('t') == 's' and valor is not None:
                texto = textos[int(valor.text)]
            elif celula.get('t') == 'str' and valor is not None:
                texto = valor.text
            elif celula.get('t') == 'inlineStr':
                texto = ''.join(celula.find(_tag('is')).itertext())
            if texto in marcadores:
                _valor(celula, marcadores[texto])

    painel = _celulas(folhas[0])
    for celula, valor in {'B9': resumo['criados'], 'F9': resumo['resolvidos'],
            'J9': resumo['sla_percentual']/100 if resumo['sla_percentual'] is not None else 'Sem dados',
            'B13': resumo['ativos'], 'F13': resumo['sem_responsavel'], 'J13': resumo['ativos_vencidos'],
            'B17': resumo['tmr_horas'] if resumo['tmr_horas'] is not None else 'Sem dados',
            'F17': resumo['fora_sla'], 'J17': resumo['sem_sla'],
            'C38': resumo['dentro_sla'], 'C39': resumo['fora_sla'], 'C40': resumo['sem_sla']}.items():
        _valor(painel[celula], valor, formula=painel[celula].find(_tag('f')) is not None)

    categorias = relatorio['categorias'] or [{'nome': 'Sem chamados no período', 'total': 0}]
    dados_painel = folhas[0].find(_tag('sheetData'))
    linhas_painel = {int(r.get('r')): r for r in dados_painel}
    rodape = max(44, 39 + len(categorias))
    if rodape != 44:
        antigo = linhas_painel[44]
        dados_painel.remove(antigo)
        dados_painel.append(_linha(antigo, rodape))
        for m in folhas[0].findall(f'{_tag("mergeCells")}/{_tag("mergeCell")}'):
            if m.get('ref') == 'B44:L44':
                m.set('ref', f'B{rodape}:L{rodape}')
    estilos_categoria = {col: deepcopy(painel[f'{col}38']) for col in ('G', 'H')}
    for r in list(dados_painel):
        if 38 <= int(r.get('r')) <= 42:
            for c in list(r):
                if re.sub(r'\d+', '', c.get('r', '')) in ('G', 'H'):
                    r.remove(c)
    for n, categoria in enumerate(categorias, 38):
        r = next((r for r in dados_painel if r.get('r') == str(n)), None)
        if r is None:
            r = ET.SubElement(dados_painel, _tag('row'), r=str(n), ht='28', customHeight='1')
        for col, valor in (('G', categoria['nome']), ('H', categoria['total'])):
            c = deepcopy(estilos_categoria[col]); c.set('r', f'{col}{n}'); _valor(c, valor); r.append(c)
    dados_painel[:] = sorted(dados_painel, key=lambda r: int(r.get('r')))
    graficos = sorted(k for k in arquivo if '/charts/chart' in k and k.endswith('.xml'))
    arquivo[graficos[0]] = _grafico(arquivo[graficos[0]], ['Dentro do SLA', 'Fora do SLA', 'Sem dados de SLA'],
        [resumo['dentro_sla'], resumo['fora_sla'], resumo['sem_sla']], 'B', 'C')
    arquivo[graficos[1]] = _grafico(arquivo[graficos[1]], [c['nome'] for c in categorias], [c['total'] for c in categorias], 'G', 'H')

    dados_desempenho = folhas[1].find(_tag('sheetData'))
    modelos = {int(r.get('r')): deepcopy(r) for r in dados_desempenho}
    dados_desempenho[:] = [r for r in dados_desempenho if int(r.get('r')) <= 6]
    blocos = [
        (7, 8, 9, 'Equipes', 'E', [
            {'B': l['equipe'].nome + (' (Inativa)' if not l['equipe'].ativa else ''), 'C': l['total'],
             'D': l['sla_percentual']/100 if l['sla_percentual'] is not None else None, 'E': l['tmr_horas']}
            for l in relatorio['equipes']]),
        (12, 13, 14, 'Analistas', 'C', [{'B': l['nome'], 'C': l['total']} for l in relatorio['analistas']]),
        (17, 18, 19, 'Solicitantes', 'C', [{'B': l['nome'], 'C': l['total']} for l in relatorio['solicitantes']]),
    ]
    cursor = 7
    for titulo, cabecalho, corpo, nome, ultima_coluna, linhas in blocos:
        dados_desempenho.append(_linha(modelos[titulo], cursor))
        dados_desempenho.append(_linha(modelos[cabecalho], cursor+1))
        linhas = linhas or [{'B': 'Sem resultados para os filtros'}]
        for n, linha in enumerate(linhas, cursor+2):
            dados_desempenho.append(_linha(modelos[corpo], n, linha))
        _tabela(arquivo, nome, cursor+1, cursor+1+len(linhas), ultima_coluna)
        cursor += len(linhas) + 4
    dados_desempenho.append(_linha(modelos[21], cursor))
    for m in folhas[1].findall(f'{_tag("mergeCells")}/{_tag("mergeCell")}'):
        if m.get('ref') == 'B21:E21':
            m.set('ref', f'B{cursor}:E{cursor}')

    dados_resolucoes = folhas[2].find(_tag('sheetData'))
    prototipo = next(r for r in dados_resolucoes if r.get('r') == '9')
    dados_resolucoes[:] = [r for r in dados_resolucoes if int(r.get('r')) < 9]
    quantidade = 0
    for numero, ciclo in enumerate(relatorio['resolvidos'].select_related('chamado', 'equipe', 'fechado_por').order_by('-data_fechamento', '-pk').iterator(chunk_size=1000), 9):
        if numero > 1048576:
            raise ValueError('O relatório excede o limite de linhas do Excel. Escolha um período menor.')
        autor = ciclo.fechado_por
        duracao = ((ciclo.data_fechamento-ciclo.data_criacao).total_seconds()/3600
            if ciclo.data_fechamento and ciclo.data_fechamento >= ciclo.data_criacao else None)
        valores = dict(zip('BCDEFGHIJKL', [ciclo.chamado_id, ciclo.numero, ciclo.chamado.titulo,
            ciclo.equipe.nome, (autor.get_full_name() or autor.username) if autor else 'Não registrado',
            ciclo.status, ciclo.data_criacao, ciclo.data_vencimento, ciclo.data_fechamento, ciclo.resultado_sla, duracao]))
        linha = _linha(prototipo, numero, valores)
        linha.set('ht', str(min(120, max(30, 15 * (1+len(ciclo.chamado.titulo)//40)))))
        dados_resolucoes.append(linha)
        quantidade += 1
    if not quantidade:
        dados_resolucoes.append(_linha(prototipo, 9, {'D': 'Nenhuma resolução para os filtros selecionados'}))
    ultima_resolucao = 8 + max(1, quantidade)
    _tabela(arquivo, 'Resolucoes', 8, ultima_resolucao, 'L')
    for cf in folhas[2].findall(_tag('conditionalFormatting')):
        cf.set('sqref', f'K9:K{ultima_resolucao}')
    for i, folha in enumerate(folhas, 1):
        for linha in folha.find(_tag('sheetData')):
            linha[:] = sorted(linha, key=lambda c: (len(re.sub(r'\d+', '', c.get('r', ''))), re.sub(r'\d+', '', c.get('r', ''))))
        _paginas(folha, detalhe=i != 1, vertical=i == 2)
        arquivo[f'xl/worksheets/sheet{i}.xml'] = ET.tostring(folha, encoding='utf-8', xml_declaration=True)
    workbook = ET.fromstring(arquivo['xl/workbook.xml'])
    ET.SubElement(workbook, _tag('calcPr'), calcId='191029', fullCalcOnLoad='1', forceFullCalc='1')
    arquivo['xl/workbook.xml'] = ET.tostring(workbook, encoding='utf-8', xml_declaration=True)
    destino = BytesIO()
    with ZipFile(destino, 'w', ZIP_DEFLATED) as saida:
        for nome, conteudo in arquivo.items():
            saida.writestr(nome, conteudo)
    return destino.getvalue()
