// Modelo visual versionado. A aplicação preenche os dados sem precisar de Node.
import fs from 'node:fs/promises';
import path from 'node:path';
import { FileBlob, SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const root = path.resolve(process.argv[2]);
const output = path.join(root, 'helpdesk', 'report_templates');
if (process.argv[3]) {
  const book = await SpreadsheetFile.importXlsx(await FileBlob.load(process.argv[3]));
  book.recalculate();
  const previewDir = path.join(root, 'docs/imagens/v1.17.0');
  await fs.mkdir(previewDir, {recursive:true});
  for (const [sheetName, range, filename] of [
    ['Resumo','B1:L46','relatorio-excel-resumo.png'],
    ['Desempenho','B1:E38','relatorio-excel-desempenho.png'],
    ['Resoluções','B1:L13','relatorio-excel-resolucoes.png'],
  ]) {
    const inspection = await book.inspect({kind:'table',range:`'${sheetName}'!${range}`,
      include:'values,formulas',tableMaxRows:5,tableMaxCols:5,maxChars:1000});
    console.log(inspection.ndjson);
    const image=await book.render({sheetName,range,scale:1.5,format:'png'});
    await fs.writeFile(path.join(previewDir,filename),new Uint8Array(await image.arrayBuffer()));
  }
  const errors=await book.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#NULL!',options:{useRegex:true,maxResults:30},maxChars:1000});
  console.log(errors.ndjson);
  process.exit(0);
}
const wb = Workbook.create();
const resumo = wb.worksheets.add('Resumo');
const desempenho = wb.worksheets.add('Desempenho');
const resolucoes = wb.worksheets.add('Resoluções');
const navy = '#101D37', teal = '#14B8A6', blue = '#638CFF';
const muted = '#526179', ice = '#F4F7FB';
const icon = await fs.readFile(path.join(root, 'helpdesk/static/helpdesk/brand/apple-touch-icon.png'));

function merged(sheet, ref, value, format = {}) {
  const range = sheet.getRange(ref);
  range.merge();
  range.values = [[value]];
  range.format = format;
}
function base(sheet, title, end = 'L') {
  sheet.showGridLines = false;
  sheet.tabColor = sheet === resumo ? navy : teal;
  sheet.getRange(`A1:${end}50`).format.font = {name:'Arial', size:10, color:navy};
  sheet.getRange(`A1:${end}50`).format.rowHeight = 22;
  sheet.getRange(`A1:${end}50`).format.verticalAlignment = 'center';
  sheet.getRange('A:A').format.columnWidth = 3;
  sheet.getRange(`B:${end}`).format.columnWidth = 12;
  const headerEnd = end === 'E' ? 'D' : 'I';
  merged(sheet, `B2:${headerEnd}2`, 'NEXALTRI', {font:{name:'Arial', size:16, bold:true, color:navy}});
  merged(sheet, `B3:${headerEnd}3`, title, {font:{name:'Arial', size:13, bold:true, color:navy}});
  merged(sheet, `B4:${end}4`, '{{escopo}}', {font:{name:'Arial', size:10, color:muted}, wrapText:true});
  merged(sheet, `B5:${end}5`, '{{gerado}}', {font:{name:'Arial', size:9, color:muted}});
  sheet.getRange(`B6:${end}6`).format.borders = {bottom:{style:'medium', color:teal}};
  sheet.images.add({dataUrl:`data:image/png;base64,${icon.toString('base64')}`,
    anchor:{from:{row:1,col:end==='E'?4:10},extent:{widthPx:48,heightPx:48}}});
}
base(resumo, 'Relatório de performance');
base(desempenho, 'Equipes, analistas e solicitantes', 'E');
base(resolucoes, 'Ciclos concluídos', 'L');

function card(col, row, label, note, format = '#,##0') {
  const end = String.fromCharCode(col.charCodeAt(0)+2);
  merged(resumo, `${col}${row}:${end}${row}`, label,
    {fill:ice,font:{name:'Arial',size:10,bold:true,color:muted}});
  merged(resumo, `${col}${row+1}:${end}${row+1}`, 0,
    {fill:ice,font:{name:'Arial',size:16,bold:true,color:navy},numberFormat:format});
  merged(resumo, `${col}${row+2}:${end}${row+2}`, note,
    {fill:ice,font:{name:'Arial',size:9,color:muted},wrapText:true});
  resumo.getRange(`${col}${row+1}:${end}${row+1}`).format.rowHeight = 29;
  resumo.getRange(`${col}${row+2}:${end}${row+2}`).format.rowHeight = 28;
}
card('B',8,'Chamados criados','Aberturas no período');
card('F',8,'Resoluções','Ciclos concluídos no período');
card('J',8,'Dentro do SLA','Sobre resoluções com SLA conhecido','0.0%');
card('B',12,'Chamados ativos','Situação atual da equipe');
card('F',12,'Sem responsável','Chamados ativos agora');
card('J',12,'Ativos vencidos','Chamados ativos agora');
card('B',16,'Tempo médio','Horas corridas por ciclo concluído','0.0" h"');
card('F',16,'SLA violado','Resoluções fora do prazo');
card('J',16,'Sem dados de SLA','Resoluções sem prazo ou fechamento');
for(const cell of ['J13','F17']) resumo.getRange(cell).conditionalFormats.add('cellIs',
  {operator:'greaterThan',formula:0,format:{font:{color:'#B42318',bold:true}}});

merged(resumo,'B20:L20','Resoluções usam a data de fechamento. Ativos agora mostram a fila atual, independentemente do período.',
  {font:{name:'Arial',size:9,color:muted},wrapText:true});
resumo.getRange('B20:L20').format.rowHeight=30;
resumo.getRange('B37:C40').values=[['Resultado de SLA','Resoluções'],['Dentro do SLA',0],['Fora do SLA',0],['Sem dados de SLA',0]];
resumo.getRange('G37:H42').values=[['Categoria','Aberturas'],['Hardware',0],['Software',0],['Rede/Internet',0],['Acessos',0],['Outros',0]];
resumo.getRange('B37:C37').format={fill:navy,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'}};
resumo.getRange('G37:H37').format={fill:navy,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'}};
resumo.getRange('B38:B40').format.font={name:'Arial',size:9,color:muted};
resumo.getRange('G38:G42').format.font={name:'Arial',size:9,color:muted};
resumo.getRange('C38:C40').setNumberFormat('#,##0');
resumo.getRange('H38:H42').setNumberFormat('#,##0');
resumo.getRange('B37:B42').format.columnWidth=17;
resumo.getRange('G37:G42').format.columnWidth=17;
resumo.getRange('F9').formulas=[['=SUM(C38:C40)']];
resumo.getRange('J9').formulas=[['=IF(SUM(C38:C39)=0,"Sem dados",ROUND(100*C38/SUM(C38:C39),1)/100)']];
resumo.getRange('F17').formulas=[['=C39']];
resumo.getRange('J17').formulas=[['=C40']];
for(const [range,title,left,right,color] of [
  ['B37:C40','Resultado dos ciclos','B22','F35',teal],
  ['G37:H42','Chamados por categoria','H22','L35',blue],
]) {
  const chart=resumo.charts.add('bar',resumo.getRange(range));
  chart.title=title;
  chart.titleTextStyle.fontSize=12;
  chart.titleTextStyle.typeface='Arial';
  chart.hasLegend=false;
  chart.series.items[0].fill=color;
  chart.xAxis={axisType:'textAxis',textStyle:{typeface:'Arial',fontSize:9}};
  chart.yAxis={numberFormatCode:'#,##0',numberFormatSourceLinked:false,textStyle:{typeface:'Arial',fontSize:9}};
  chart.setPosition(left,right);
}
merged(resumo,'B44:L44','{{situacao}}',{font:{name:'Arial',size:9,color:muted},wrapText:true});
resumo.getRange('B44:L44').format.rowHeight=32;

function table(sheet, headerRow, headers, name, widths, formats=[]) {
  const last=String.fromCharCode('B'.charCodeAt(0)+headers.length-1);
  sheet.getRange(`B${headerRow}:${last}${headerRow}`).values=[headers];
  sheet.getRange(`B${headerRow+1}:${last}${headerRow+1}`).values=[headers.map(()=> '')];
  const tab=sheet.tables.add(`B${headerRow}:${last}${headerRow+1}`,true,name);
  tab.style='TableStyleMedium2';
  sheet.getRange(`B${headerRow}:${last}${headerRow}`).format={fill:navy,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,horizontalAlignment:'center'};
  sheet.getRange(`B${headerRow}:${last}${headerRow}`).format.rowHeight=32;
  sheet.getRange(`B${headerRow+1}:${last}${headerRow+1}`).format={fill:ice,font:{name:'Arial',size:10,color:navy},wrapText:true};
  sheet.getRange(`B${headerRow+1}:${last}${headerRow+1}`).format.rowHeight=30;
  widths.forEach((width,i)=>sheet.getRange(`${String.fromCharCode(66+i)}:${String.fromCharCode(66+i)}`).format.columnWidth=width);
  formats.forEach((format,i)=>sheet.getRange(`${String.fromCharCode(66+i)}${headerRow+1}`).setNumberFormat(format));
}
desempenho.getRange('B7').values=[['Equipes']];
desempenho.getRange('B12').values=[['Analistas']];
desempenho.getRange('B17').values=[['Top 20 solicitantes']];
table(desempenho,8,['Equipe','Resoluções','Dentro do SLA','Tempo médio (h)'],'Equipes',[42,17,18,19],['@','#,##0','0.0%','0.0']);
table(desempenho,13,['Analista','Resoluções'],'Analistas',[42,17],['@','#,##0']);
table(desempenho,18,['Solicitante','Chamados criados'],'Solicitantes',[42,20],['@','#,##0']);
desempenho.getRange('B21:E21').merge();
desempenho.getRange('B21').values=[['{{criterios}}']];
desempenho.getRange('B21:E21').format={font:{name:'Arial',size:9,color:muted},wrapText:true};
desempenho.getRange('B21:E21').format.rowHeight=45;
desempenho.freezePanes.freezeRows(6);

table(resolucoes,8,['Chamado','Ciclo','Título','Equipe','Resolvido por','Status do ciclo','Início do ciclo','Vencimento','Fechamento','SLA','Duração (h)'],
  'Resolucoes',[13,9,45,34,26,20,24,24,24,24,17],['#,##0','#,##0','@','@','@','@','dd/mm/yyyy hh:mm','dd/mm/yyyy hh:mm','dd/mm/yyyy hh:mm','@','0.0']);
resolucoes.getRange('K9').conditionalFormats.addCustom('K9="Fora do SLA"',{fill:'#FEE4E2',font:{color:'#B42318'}});
resolucoes.getRange('K9').conditionalFormats.addCustom('K9="Dentro do SLA"',{fill:'#DCFCE7',font:{color:'#166534'}});
resolucoes.freezePanes.freezeRows(8);
resolucoes.freezePanes.freezeColumns(3);

wb.recalculate();
await fs.mkdir(output,{recursive:true});
const file=await SpreadsheetFile.exportXlsx(wb);
await file.save(path.join(output,'indicadores.xlsx'));
await fs.rm(path.join(output,'indicadores.xlsx.inspect.ndjson'),{force:true});
console.log('Modelo visual salvo em helpdesk/report_templates/indicadores.xlsx');
