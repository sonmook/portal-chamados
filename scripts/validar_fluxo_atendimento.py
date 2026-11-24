"""Homologa atendimento pelo Chromium e restauração isolada, com dados fictícios.

Executa os formulários reais, com CSRF e sessões independentes. Usa banco, uploads
e backups temporários próprios; não consulta a instalação do operador.
"""
from contextlib import closing, contextmanager
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import urlopen
from wsgiref.simple_server import WSGIRequestHandler, make_server
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SAIDA = ROOT/'artifacts'/'homologacao-funcional'
TITULO = 'Homologação: acesso ao sistema de pedidos'
PUBLICO = 'Atendimento iniciado. Vamos conferir a configuração do aplicativo.'
PRIVADO = 'Diagnóstico interno fictício: conferir o perfil de acesso da aplicação.'
SOLUCOES = ('Perfil de acesso corrigido e conferido com o solicitante.',
            'Ajuste complementar aplicado e acesso validado após a reabertura.')
S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def ler(banco, consulta, parametros=()):
    with closing(sqlite3.connect(banco.as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        with closing(db.execute(consulta, parametros)) as cursor:
            return [dict(r) for r in cursor.fetchall()]


def retrato(banco):
    """Compara todas as tabelas sem escrever dados ou credenciais no relatório."""
    tabelas = ler(banco, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    return {t['name']: hashlib.sha256(json.dumps(ler(banco, f'SELECT * FROM "{t["name"]}" ORDER BY rowid'),
        ensure_ascii=False, sort_keys=True).encode()).hexdigest() for t in tabelas}


def celulas(arquivo, numero):
    with ZipFile(arquivo) as z:
        strings = [''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        valores = {}
        for c in ET.fromstring(z.read(f'xl/worksheets/sheet{numero}.xml')).iter(S+'c'):
            v = c.find(S+'v')
            if c.get('t') == 'inlineStr':
                valores[c.get('r')] = ''.join(c.find(S+'is').itertext())
            elif v is not None:
                valores[c.get('r')] = strings[int(v.text)] if c.get('t') == 's' else (v.text if c.get('t') == 'str' else float(v.text))
        return valores


class Silencioso(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def main():
    from playwright.sync_api import sync_playwright, expect
    resultados, capturas, erros_js = [], [], []
    SAIDA.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()

    @contextmanager
    def etapa(codigo, nome):
        print(f'RUN {codigo}: {nome}', flush=True)
        try:
            yield
        except Exception:
            resultados.append({'codigo': codigo, 'cenario': nome, 'resultado': 'falhou'})
            raise
        else:
            resultados.append({'codigo': codigo, 'cenario': nome, 'resultado': 'aprovado'})
            print(f'PASS {codigo}: {nome}', flush=True)

    def capturar(page, nome):
        dados = page.screenshot(path=str(SAIDA/f'{nome}.png'), full_page=True, animations='disabled')
        capturas.append({'arquivo': nome+'.png', 'sha256': hashlib.sha256(dados).hexdigest()})

    try:
        with TemporaryDirectory(prefix='nexaltri-homologacao-') as temp:
            tmp = Path(temp)
            banco, midia = tmp/'origem.sqlite3', tmp/'media'
            os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'
            from django.conf import settings
            settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': banco}}
            settings.MEDIA_ROOT = midia
            settings.SECRET_KEY = secrets.token_urlsafe(64)
            settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
            settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
            settings.DEBUG = True
            import django
            django.setup()
            from django.contrib.auth.models import User
            from django.contrib.staticfiles.handlers import StaticFilesHandler
            from django.core.management import call_command
            from django.core.wsgi import get_wsgi_application
            from django.db import connections
            from django.test import override_settings
            from django.urls import reverse
            from helpdesk.backups import criar_backup, restaurar_backup, digest
            from helpdesk.models import Equipe, IntegranteEquipe, RegraEncaminhamento
            from PIL import Image
            call_command('migrate', interactive=False, verbosity=0)
            senha = secrets.token_urlsafe(24)
            usuarios = {}
            for chave, nome, staff, admin in (
                ('cliente', 'Carla Solicitante', False, False), ('origem', 'Lucas Atendimento', True, False),
                ('destino', 'Marina Sistemas', True, False), ('admin', 'Ana Administração', True, True),
                ('intruso', 'Pedro Outro Solicitante', False, False),
            ):
                primeiro, ultimo = nome.split(' ', 1)
                u = User.objects.create_user('homol.'+chave, password=senha, first_name=primeiro,
                    last_name=ultimo, is_staff=staff, is_superuser=admin)
                usuarios[chave] = {'id': u.pk, 'login': u.username, 'nome': nome}
            origem = Equipe.objects.create(nome='Homologação — Atendimento')
            destino = Equipe.objects.create(nome='Homologação — Sistemas')
            IntegranteEquipe.objects.create(equipe=origem, usuario_id=usuarios['origem']['id'], coordenador=True)
            IntegranteEquipe.objects.create(equipe=destino, usuario_id=usuarios['destino']['id'])
            RegraEncaminhamento.objects.update_or_create(categoria='Software', defaults={'equipe': origem, 'ativa': True})
            origem_id, destino_id, destino_nome = origem.pk, destino.pk, destino.nome
            caminhos = {n: reverse(n) for n in ('login', 'novo_chamado', 'listar_notificacoes',
                'indicadores_administracao', 'exportar_indicadores_excel', 'listar_auditoria')}
            img = io.BytesIO(); Image.new('RGB', (160, 90), '#14B8A6').save(img, 'PNG')
            evidencia = img.getvalue()
            arquivo_evidencia = tmp/'evidencia-ficticia.png'; arquivo_evidencia.write_bytes(evidencia)
            connections.close_all()
            cdn = {}

            @contextmanager
            def servir(db_path, media_path):
                connections.close_all()
                settings.DATABASES['default']['NAME'] = db_path
                connections['default'].settings_dict['NAME'] = db_path
                # O sinal de override_settings também limpa o cache do storage.
                # A instância restaurada deve servir seus próprios uploads.
                with override_settings(MEDIA_ROOT=media_path):
                    server = make_server('127.0.0.1', 0, StaticFilesHandler(get_wsgi_application()), handler_class=Silencioso)
                    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
                    try:
                        yield f'http://127.0.0.1:{server.server_port}'
                    finally:
                        server.shutdown(); server.server_close(); thread.join(timeout=5)
                        connections.close_all()

            def recurso(route):
                url = route.request.url
                if url not in cdn:
                    with urlopen(url, timeout=30) as resposta:
                        cdn[url] = (resposta.read(), resposta.headers.get_content_type())
                dados, tipo = cdn[url]
                route.fulfill(status=200, body=dados, content_type=tipo,
                    headers={'Access-Control-Allow-Origin': '*'})

            def entrar(browser, base, chave):
                context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
                context.route('https://cdn.jsdelivr.net/**', recurso)
                page = context.new_page()
                page.on('pageerror', lambda erro: erros_js.append(str(erro)))
                page.goto(base+caminhos['login'])
                page.locator('#floatingInput').fill(usuarios[chave]['login'])
                page.locator('#floatingPassword').fill(senha)
                page.get_by_role('button', name=re.compile('ENTRAR')).click()
                page.wait_for_url(lambda url: '/contas/login/' not in url)
                return context, page

            def enviar(page, texto):
                page.locator('#formulario-comentario textarea').fill(texto)
                page.get_by_role('button', name='Enviar Resposta', exact=True).click()
                expect(page.get_by_text(texto, exact=True)).to_be_visible()

            def resolver(page, texto):
                page.get_by_role('button', name='Marcar como Resolvido', exact=True).click()
                page.locator('#modalResolucao textarea').fill(texto)
                page.get_by_role('button', name='Encerrar Chamado', exact=True).click()
                expect(page.get_by_text('Este chamado foi resolvido e encerrado.', exact=True)).to_be_visible()

            def exportar(page, nome):
                with page.expect_download() as evento:
                    page.get_by_role('link', name='Exportar Excel formatado', exact=True).click()
                download = evento.value
                assert download.failure() is None
                arquivo = SAIDA/nome; download.save_as(arquivo)
                resumo = celulas(arquivo, 1)
                assert {k: resumo[k] for k in ('B9', 'F9', 'J9', 'B13', 'F17')} == {
                    'B9': 1, 'F9': 2, 'J9': 1, 'B13': 0, 'F17': 0}, resumo
                detalhes = celulas(arquivo, 3)
                assert sorted([detalhes['C9'], detalhes['C10']]) == [1, 2]
                assert detalhes['D9'] == detalhes['D10'] == TITULO
                assert detalhes['E9'] == detalhes['E10'] == destino_nome
                assert detalhes['F9'] == detalhes['F10'] == usuarios['destino']['nome']
                with ZipFile(arquivo) as z:
                    assert z.testzip() is None
                    for i in (1, 2, 3):
                        assert len(ET.fromstring(z.read(f'xl/worksheets/sheet{i}.xml')).findall(S+'pageMargins')) == 1

            with servir(banco, midia) as base, sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    cliente_ctx, cliente = entrar(browser, base, 'cliente')
                    with etapa('HF-01', 'Solicitante abre chamado com anexo; encaminhamento e prazo registrados'):
                        cliente.goto(base+caminhos['novo_chamado'])
                        cliente.locator('#id_titulo').fill(TITULO)
                        cliente.locator('#id_categoria').select_option('Software')
                        cliente.locator('#id_prioridade').select_option('Normal')
                        cliente.locator('#id_descricao').fill('Cenário fictício: acesso negado ao sistema de pedidos.')
                        cliente.locator('#id_anexo').set_input_files(arquivo_evidencia)
                        cliente.get_by_role('button', name='Enviar Solicitação', exact=True).click()
                        cliente.wait_for_load_state('networkidle')
                        chamado = ler(banco, 'SELECT * FROM helpdesk_chamado WHERE titulo=?', (TITULO,))[0]
                        chamado_id, prazo = chamado['id'], chamado['data_vencimento']
                        url = f'/chamado/{chamado_id}/'
                        assert chamado['equipe_id'] == origem_id and chamado['tecnico_id'] is None and prazo
                        cliente.goto(base+url)
                        with cliente.expect_download() as evento:
                            cliente.get_by_role('link', name='Baixar anexo do chamado', exact=True).click()
                        assert Path(evento.value.path()).read_bytes() == evidencia
                        capturar(cliente, '01-abertura-solicitante')
                    with etapa('HF-02', 'Outro solicitante não acessa chamado, anexo ou relatório administrativo'):
                        intruso_ctx, intruso = entrar(browser, base, 'intruso')
                        for caminho, status in ((url, 404), (url+'anexo/', 404), (caminhos['exportar_indicadores_excel'], 403)):
                            assert intruso_ctx.request.get(base+caminho).status == status
                        intruso_ctx.close()
                    origem_ctx, tecnico = entrar(browser, base, 'origem')
                    tecnico.goto(base+url)
                    with etapa('HF-03', 'Técnico assume o chamado sem alterar o vencimento'):
                        tecnico.get_by_role('button', name='Assumir Chamado', exact=True).click()
                        expect(tecnico.get_by_text('Você é o responsável', exact=True)).to_be_visible()
                        atual = ler(banco, 'SELECT * FROM helpdesk_chamado WHERE id=?', (chamado_id,))[0]
                        assert atual['tecnico_id'] == usuarios['origem']['id'] and atual['data_vencimento'] == prazo
                    with etapa('HF-04', 'Resposta pública aparece ao solicitante e gera notificação'):
                        enviar(tecnico, PUBLICO)
                        cliente.reload(); expect(cliente.get_by_text(PUBLICO, exact=True)).to_be_visible()
                        assert ler(banco, "SELECT id FROM helpdesk_notificacao WHERE destinatario_id=? AND tipo='resposta'", (usuarios['cliente']['id'],))
                    with etapa('HF-05', 'Nota e anexo internos ficam restritos à TI sem notificar o solicitante'):
                        antes = len(ler(banco, 'SELECT id FROM helpdesk_notificacao WHERE destinatario_id=?', (usuarios['cliente']['id'],)))
                        tecnico.get_by_text('Adicionar nota interna · TI', exact=True).click()
                        tecnico.locator('#id_nota-texto').fill(PRIVADO)
                        tecnico.locator('#id_nota-anexo').set_input_files(arquivo_evidencia)
                        tecnico.get_by_role('button', name='Salvar nota interna', exact=True).click()
                        expect(tecnico.get_by_text(PRIVADO, exact=True)).to_be_visible()
                        nota_id = ler(banco, 'SELECT id FROM helpdesk_comentario WHERE interna=1')[0]['id']
                        privado_url = url+f'comentario/{nota_id}/anexo/'
                        cliente.reload(); expect(cliente.get_by_text(PRIVADO, exact=True)).to_have_count(0)
                        assert cliente_ctx.request.get(base+privado_url).status == 404
                        assert len(ler(banco, 'SELECT id FROM helpdesk_notificacao WHERE destinatario_id=?', (usuarios['cliente']['id'],))) == antes
                    with etapa('HF-06', 'Espera por solicitante e resposta retomam atendimento preservando o prazo'):
                        tecnico.locator('#id_status').select_option('Aguardando solicitante')
                        tecnico.locator('#id_motivo').fill('Confirmar a mensagem exibida no aplicativo.')
                        tecnico.get_by_role('button', name='Salvar situação', exact=True).click()
                        cliente.reload()
                        enviar(cliente, 'Confirmado: o aplicativo informa acesso negado ao abrir pedidos.')
                        atual = ler(banco, 'SELECT * FROM helpdesk_chamado WHERE id=?', (chamado_id,))[0]
                        assert atual['status'] == 'Em Andamento' and atual['data_vencimento'] == prazo
                    with etapa('HF-07', 'Transferência preserva SLA e revoga o acesso técnico da equipe anterior'):
                        tecnico.reload(); tecnico.get_by_role('link', name='Redistribuir chamado', exact=True).click()
                        tecnico.locator('#equipe-destino').select_option(str(destino_id))
                        tecnico.get_by_role('button', name='Carregar integrantes', exact=True).click()
                        tecnico.locator('#id_tecnico').select_option(str(usuarios['destino']['id']))
                        tecnico.locator('#id_motivo').fill('Encaminhar a validação do perfil de acesso à equipe de sistemas.')
                        tecnico.get_by_role('button', name='Confirmar transferência', exact=True).click()
                        tecnico.wait_for_load_state('networkidle')
                        atual = ler(banco, 'SELECT * FROM helpdesk_chamado WHERE id=?', (chamado_id,))[0]
                        assert atual['equipe_id'] == destino_id and atual['tecnico_id'] == usuarios['destino']['id']
                        assert atual['data_vencimento'] == prazo
                        assert origem_ctx.request.get(base+url).status == 404
                        destino_ctx, especialista = entrar(browser, base, 'destino')
                        especialista.goto(base+url); expect(especialista.get_by_text(PRIVADO, exact=True)).to_be_visible()
                        assert destino_ctx.request.get(base+privado_url).body() == evidencia
                        capturar(especialista, '02-atendimento-transferido')
                    with etapa('HF-08', 'Resolução registra solução, autor, equipe e primeiro ciclo'):
                        resolver(especialista, SOLUCOES[0])
                        ciclos = ler(banco, 'SELECT * FROM helpdesk_cicloatendimento WHERE chamado_id=?', (chamado_id,))
                        assert len(ciclos) == 1 and ciclos[0]['numero'] == 1
                        assert ciclos[0]['data_vencimento'] == prazo and ciclos[0]['fechado_por_id'] == usuarios['destino']['id']
                        primeiro_ciclo = ciclos[0]
                        capturar(especialista, '03-primeira-resolucao')
                    with etapa('HF-09', 'Solicitante lê aviso e reabre com justificativa; histórico anterior permanece'):
                        cliente.goto(base+caminhos['listar_notificacoes'])
                        cliente.get_by_role('button', name=f'Abrir chamado {chamado_id}: {TITULO}', exact=True).first.click()
                        expect(cliente.get_by_text(SOLUCOES[0], exact=True)).to_be_visible()
                        cliente.locator('#id_motivo_reabertura').fill('O acesso voltou a falhar ao consultar um pedido diferente.')
                        cliente.get_by_role('button', name='Reabrir chamado', exact=True).click()
                        expect(cliente.get_by_text(SOLUCOES[0], exact=True)).to_be_visible()
                        atual = ler(banco, 'SELECT * FROM helpdesk_chamado WHERE id=?', (chamado_id,))[0]
                        assert atual['ciclo_atual'] == 2 and atual['status'] == 'Em Andamento'
                        assert atual['data_fechamento'] is None and atual['data_vencimento']
                        assert ler(banco, 'SELECT * FROM helpdesk_cicloatendimento WHERE chamado_id=?', (chamado_id,))[0] == primeiro_ciclo
                        assert ler(banco, 'SELECT id FROM helpdesk_notificacao WHERE lida_em IS NOT NULL AND destinatario_id=?', (usuarios['cliente']['id'],))
                        assert ler(banco, "SELECT id FROM helpdesk_notificacao WHERE tipo='reabertura' AND chamado_id=?", (chamado_id,))
                        capturar(cliente, '04-reabertura-solicitante')
                    with etapa('HF-10', 'Segunda resolução preserva os dois ciclos e a conversa'):
                        especialista.reload(); resolver(especialista, SOLUCOES[1])
                        ciclos = ler(banco, 'SELECT * FROM helpdesk_cicloatendimento WHERE chamado_id=? ORDER BY numero', (chamado_id,))
                        assert len(ciclos) == 2 and ciclos[0] == primeiro_ciclo
                        assert all(c['equipe_id'] == destino_id and c['fechado_por_id'] == usuarios['destino']['id'] for c in ciclos)
                        assert all(c['data_fechamento'] <= c['data_vencimento'] for c in ciclos)
                    admin_ctx, admin = entrar(browser, base, 'admin')
                    with etapa('HF-11', 'Administrador concilia indicadores: um chamado, duas resoluções e nenhum ativo'):
                        admin.goto(base+caminhos['indicadores_administracao'])
                        admin.locator('#id_periodo').select_option('sempre')
                        admin.locator('#id_equipe').select_option(str(destino_id))
                        admin.get_by_role('button', name='Aplicar filtros', exact=True).click()
                        expect(admin.get_by_text(re.compile('2 resoluções no período · 0 ativos agora'))).to_be_visible()
                        assert admin.locator('.rel-kpi').nth(0).inner_text() == '1'
                        capturar(admin, '05-indicadores-administrador')
                    with etapa('HF-12', 'Download real de Excel e CSV mantém filtros, autores, números e dois ciclos'):
                        exportar(admin, 'indicadores.xlsx')
                        import csv
                        with admin.expect_download() as evento:
                            admin.get_by_role('link', name='Exportar CSV', exact=True).click()
                        csv_path = SAIDA/'resolucoes.csv'; evento.value.save_as(csv_path)
                        linhas = list(csv.DictReader(io.StringIO(csv_path.read_text(encoding='utf-8-sig')), delimiter=';'))
                        assert len(linhas) == 2 and all(l['Equipe'] == destino_nome for l in linhas)
                        assert {l['Ciclo'] for l in linhas} == {'1', '2'}
                    with etapa('HF-13', 'Auditoria administrativa e ausência de erros JavaScript'):
                        admin.goto(base+caminhos['listar_auditoria'])
                        expect(admin.get_by_role('heading', name='Auditoria', exact=True)).to_be_visible()
                        assert len(ler(banco, 'SELECT id FROM helpdesk_registroauditoria')) > 5
                        assert not erros_js, erros_js
                except Exception:
                    for i, context in enumerate(browser.contexts):
                        for j, page in enumerate(context.pages):
                            if not page.is_closed():
                                capturar(page, f'falha-{i}-{j}')
                    raise
                finally:
                    browser.close()

            with etapa('HF-14', 'Backup e restauração isolada preservam todas as tabelas e arquivos privados'):
                esperado = retrato(banco)
                hash_origem = digest(banco)
                criar_backup(banco, midia, tmp/'backup')
                restaurar_backup(tmp/'backup', tmp/'restaurado')
                restaurado, media_restaurada = tmp/'restaurado/db.sqlite3', tmp/'restaurado/media'
                assert retrato(restaurado) == esperado
                assert digest(banco) == hash_origem
                arquivos = {p.relative_to(midia).as_posix(): digest(p) for p in midia.rglob('*') if p.is_file()}
                assert arquivos == {p.relative_to(media_restaurada).as_posix(): digest(p) for p in media_restaurada.rglob('*') if p.is_file()}

            with servir(restaurado, media_restaurada) as base, sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    with etapa('HF-15', 'Aplicação restaurada permite login, histórico, anexos autorizados e os mesmos indicadores'):
                        from django.core.files.storage import default_storage
                        assert Path(default_storage.location) == media_restaurada
                        cliente_ctx, cliente = entrar(browser, base, 'cliente')
                        cliente.goto(base+url)
                        for texto in SOLUCOES:
                            expect(cliente.get_by_text(texto, exact=True)).to_be_visible()
                        expect(cliente.get_by_text(PRIVADO, exact=True)).to_have_count(0)
                        assert cliente_ctx.request.get(base+privado_url).status == 404
                        assert cliente_ctx.request.get(base+url+'anexo/').body() == evidencia
                        tecnico_ctx, tecnico = entrar(browser, base, 'destino')
                        tecnico.goto(base+url); expect(tecnico.get_by_text(PRIVADO, exact=True)).to_be_visible()
                        assert tecnico_ctx.request.get(base+privado_url).body() == evidencia
                        admin_ctx, admin = entrar(browser, base, 'admin')
                        admin.goto(base+caminhos['indicadores_administracao']+f'?periodo=sempre&equipe={destino_id}')
                        exportar(admin, 'indicadores-restaurado.xlsx')
                        capturar(admin, '06-indicadores-apos-restauracao')
                        assert not erros_js, erros_js
                        assert retrato(banco) == esperado, 'A navegação restaurada não deve escrever na origem'
                finally:
                    browser.close()
    finally:
        relatorio = {'versao': (ROOT/'VERSION').read_text().strip(), 'commit': commit,
            'executado_em': datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
            'dados': 'Fictícios, com banco, uploads e backup temporários próprios.',
            'resultados': resultados, 'capturas': capturas,
            'limites': ['Sem envio SMTP externo ou OAuth Google real.', 'Sem teste de carga ou publicação em domínio público.',
                'Excel conferido por valores/estrutura; o aplicativo Microsoft Excel não é automatizado.']}
        (SAIDA/'resultados.json').write_text(json.dumps(relatorio, ensure_ascii=False, indent=2))
    assert len(resultados) == 15 and all(r['resultado'] == 'aprovado' for r in resultados)
    print(f'PASS: {len(resultados)} cenários de homologação funcional no Chromium, incluindo restauração isolada.', flush=True)


if __name__ == '__main__':
    main()
