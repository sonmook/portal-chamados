"""Valida a interface com Chromium e dados fictícios em um banco temporário próprio."""
import base64
import csv
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
from threading import Thread
from urllib.request import urlopen
from wsgiref.simple_server import WSGIRequestHandler, make_server

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class Silencioso(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def main():
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory(prefix='nexaltri-visual-') as tmp:
        tmp = Path(tmp)
        os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'
        from django.conf import settings
        settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': tmp/'db.sqlite3'}}
        settings.MEDIA_ROOT = tmp/'media'
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
        from django.urls import reverse
        from helpdesk.models import Chamado, Comentario, Conquista, IntegranteEquipe, Notificacao, Perfil, RegraConquista
        call_command('migrate', interactive=False, verbosity=0)
        call_command('criar_dados_demo', stdout=io.StringIO())
        senha = secrets.token_urlsafe(18)
        usuario = User.objects.create_superuser('preview.nexaltri', 'preview@example.invalid', senha,
            first_name='Ana', last_name='Suporte')
        ticket = Chamado.objects.filter(status='Em Andamento', categoria='Rede').first()
        # Cenários exclusivos do banco temporário para documentar a interface em uso.
        ticket.tecnico = usuario
        ticket.save(update_fields=['tecnico'])
        IntegranteEquipe.objects.create(equipe=ticket.equipe, usuario=usuario)
        Perfil.objects.create(usuario=usuario, cargo='Analista de suporte', departamento='Tecnologia', ramal='204')
        Comentario.objects.create(chamado=ticket, autor=usuario,
            texto='Verificação inicial concluída. Vamos acompanhar a estabilidade da conexão.')
        Comentario.objects.create(chamado=ticket, autor=usuario, interna=True,
            texto='Nota interna de demonstração: validar o acesso com a equipe de redes.')
        for tipo in ('atribuicao', 'resposta', 'sla_proximo'):
            Notificacao.objects.create(destinatario=usuario, chamado=ticket, tipo=tipo, evento='preview-'+tipo)
        regra = RegraConquista.objects.filter(alvo='pessoa').first()
        Conquista.objects.create(usuario=usuario, regra=regra, icone=regra.icone,
            nome=regra.nome, descricao=regra.descricao, meta=regra.meta, versao_regra=regra.versao)
        resolvido = Chamado.objects.filter(status='Resolvido').first()
        # Evita uma consulta ORM dentro do contexto assíncrono do Playwright.
        equipe_exportacao_nome = resolvido.equipe.nome
        tecnico = User.objects.get(username='demo.lucas')
        paginas = {
            'chamados': reverse('lista_chamados'), 'dashboard': reverse('dashboard'),
            'detalhe': reverse('detalhes_chamado', args=[ticket.pk]),
            'administracao': reverse('central_administracao'), 'perfil': reverse('meu_perfil'),
            'indicadores': reverse('indicadores_administracao'),
            'novo-chamado': reverse('novo_chamado'), 'equipes': reverse('gerenciar_equipes'),
            'notificacoes': reverse('listar_notificacoes'),
        }
        documentacao = {
            'respostas-prontas': reverse('gerenciar_respostas_prontas'),
            'conquistas': reverse('minhas_conquistas'),
            'usuarios': reverse('gerenciar_usuarios'),
            'redistribuicao': reverse('redistribuir_chamado', args=[ticket.pk]),
            'pendencias-tecnico': reverse('editar_usuario', args=[tecnico.pk]),
            'encaminhamento': reverse('listar_regras_encaminhamento'),
            'resolucao': reverse('detalhes_chamado', args=[resolvido.pk]),
            'fila-sla': reverse('lista_chamados')+'?fila=minha&sla=proximos',
        }
        connections.close_all()
        server = make_server('127.0.0.1', 0, StaticFilesHandler(get_wsgi_application()), handler_class=Silencioso)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        saida = ROOT/'artifacts'/'nexaltri-visual'
        saida.mkdir(parents=True, exist_ok=True)
        cdn = {}
        resultados = []
        capturas = []
        erros = []

        # O fetch usa a CA/proxy do ambiente, mantendo a verificação TLS dos recursos existentes.
        def recurso_externo(route):
            url = route.request.url
            if url not in cdn:
                with urlopen(url, timeout=30) as response:
                    cdn[url] = (response.read(), response.headers.get_content_type())
            dados, tipo = cdn[url]
            route.fulfill(status=200, body=dados, content_type=tipo,
                headers={'Access-Control-Allow-Origin': '*'})

        def preparar(context):
            context.route('https://cdn.jsdelivr.net/**', recurso_externo)
            pagina = context.new_page()
            pagina.on('pageerror', lambda erro: erros.append(str(erro)))
            return pagina

        def verificar(page, nome):
            page.wait_for_load_state('networkidle')
            page.evaluate('document.fonts.ready')
            assert not erros, (nome, erros)
            assert 'Nexaltri' in page.title(), (nome, page.title())
            medidas = page.evaluate('''() => ({viewport:innerWidth, largura:document.documentElement.scrollWidth,
                imagens:[...document.querySelectorAll('img[src*="/brand/"]')].map(i=>({src:i.src,ok:i.complete&&i.naturalWidth>0})),
                fontes:[...document.fonts].map(f=>({nome:f.family,estado:f.status})),
                texto:getComputedStyle(document.body).fontFamily})''')
            assert medidas['largura'] <= medidas['viewport']+1, (nome, medidas)
            assert medidas['imagens'] and all(i['ok'] for i in medidas['imagens']), (nome, medidas)
            assert 'Inter' in medidas['texto'], (nome, medidas)
            for fonte in ('Manrope', 'Inter'):
                assert any(fonte in f['nome'] and f['estado']=='loaded' for f in medidas['fontes']), (nome, medidas)
            for botao in page.locator('.btn-primary:visible').all():
                cores = botao.evaluate('(b)=>({frente:getComputedStyle(b).color,fundo:getComputedStyle(b).backgroundColor})')
                def luminancia(cor):
                    valores = [int(v)/255 for v in re.findall(r'\d+', cor)[:3]]
                    linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in valores]
                    return sum(v*p for v,p in zip(linear,(.2126,.7152,.0722)))
                alto, baixo = sorted((luminancia(cores['frente']), luminancia(cores['fundo'])), reverse=True)
                assert (alto+.05)/(baixo+.05) >= 4.5, (nome, 'Contraste do botão', cores)
            resultados.append({'pagina': nome, 'viewport': medidas['viewport'], 'overflow': False, 'fontes': 'locais carregadas'})

        def capturar(page, nome, *, completa=False):
            dados = page.screenshot(path=str(saida/f'{nome}.png'), full_page=completa, animations='disabled')
            capturas.append({'arquivo': nome+'.png', 'viewport': page.viewport_size,
                'pagina_inteira': completa, 'sha256': hashlib.sha256(dados).hexdigest()})
            if os.environ.get('NEXALTRI_LOG_PREVIEWS') == '1':
                codificado = base64.b64encode(dados).decode()
                print('NEXALTRI_IMAGE_BEGIN '+nome, flush=True)
                for inicio in range(0, len(codificado), 8192):
                    print('NEXALTRI_IMAGE_DATA '+codificado[inicio:inicio+8192], flush=True)
                print('NEXALTRI_IMAGE_END', flush=True)

        def verificar_exportacao(page, largura):
            # Download real após aplicar filtros; cada viewport usa a sessão administrativa.
            page.locator('#id_periodo').select_option('sempre')
            page.locator('#id_equipe').select_option(str(resolvido.equipe_id))
            page.get_by_role('button', name='Aplicar filtros').click()
            verificar(page, f'indicadores-exportacao-{largura}')
            with page.expect_download() as evento:
                page.get_by_role('link', name='Exportar CSV', exact=True).click()
            download = evento.value
            assert download.failure() is None, download.failure()
            assert download.suggested_filename.startswith('nexaltri-resolucoes-')
            dados = Path(download.path()).read_bytes()
            assert dados.startswith(b'\xef\xbb\xbf'), 'Acentos precisam de UTF-8 com BOM'
            linhas = list(csv.DictReader(io.StringIO(dados.decode('utf-8-sig')), delimiter=';'))
            assert linhas and all(l['Equipe'] == equipe_exportacao_nome for l in linhas)
            assert any(l['Chamado'] == str(resolvido.pk) for l in linhas)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                desktop = browser.new_context(viewport={'width': 1440, 'height': 960}, reduced_motion='reduce')
                page = preparar(desktop)
                page.goto(base+reverse('login'))
                verificar(page, 'login-desktop')
                capturar(page, 'login-desktop')
                page.locator('#floatingInput').fill(usuario.username)
                page.locator('#floatingPassword').fill(senha)
                page.get_by_role('button', name='Mostrar senha').click()
                assert page.locator('#floatingPassword').get_attribute('type') == 'text'
                page.get_by_role('button', name='Ocultar senha').click()
                page.get_by_role('button', name=re.compile('ENTRAR')).click()
                page.wait_for_url(lambda url: '/contas/login/' not in url)
                estado = desktop.storage_state()
                mobile_login = browser.new_context(viewport={'width': 390, 'height': 844}, reduced_motion='reduce')
                public = preparar(mobile_login)
                public.goto(base+reverse('login'))
                verificar(public, 'login-mobile')
                capturar(public, 'login-mobile')
                mobile_login.close()

                for largura, altura in ((1440,960),(820,1000),(390,844)):
                    contexto = browser.new_context(viewport={'width': largura, 'height': altura},
                        storage_state=estado, reduced_motion='reduce')
                    atual = preparar(contexto)
                    for nome, caminho in paginas.items():
                        atual.goto(base+caminho)
                        verificar(atual, f'{nome}-{largura}')
                        assert atual.locator('.portal-navbar img[alt="Nexaltri"]').count()==1
                        if nome == 'chamados':
                            if largura < 1400:
                                menu = atual.get_by_role('button', name='Abrir ou fechar menu')
                                menu.click()
                                atual.locator('#navbarNav.show').wait_for()
                                menu.click()
                                atual.locator('#navbarNav').wait_for(state='hidden')
                            if largura in (390,1440):
                                capturar(atual, f'chamados-{largura}')
                        if largura == 1440 and nome != 'chamados':
                            capturar(atual, f'{nome}-{largura}', completa=True)
                        if nome == 'indicadores':
                            verificar_exportacao(atual, largura)
                    contexto.close()
                for nome, caminho in documentacao.items():
                    page.goto(base+caminho)
                    verificar(page, nome+'-1440')
                    capturar(page, nome+'-1440', completa=True)
                page.goto(base+reverse('admin:index'))
                verificar(page, 'admin-desktop')
                assert page.locator('#site-name img[alt="Nexaltri"]').is_visible()
                capturar(page, 'admin-desktop')
                page.set_viewport_size({'width': 390, 'height': 844})
                verificar(page, 'admin-mobile')
                assert page.locator('#site-name img[alt="Nexaltri"]').is_visible()
                capturar(page, 'admin-mobile')
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            connections.close_all()
        (saida/'resultados.json').write_text(json.dumps(resultados, ensure_ascii=False, indent=2))
        (saida/'capturas.json').write_text(json.dumps({
            'versao': (ROOT/'VERSION').read_text().strip(),
            'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'capturado_em': datetime.now().astimezone().isoformat(),
            'fuso_interface': settings.TIME_ZONE,
            'dados': 'Fictícios; banco temporário exclusivo. A medalha foi semeada para demonstrar a vitrine.',
            'capturas': capturas,
        }, ensure_ascii=False, indent=2))
        print(f'PASS: {len(resultados)} verificações visuais; login, navegação, fontes, marca e largura em desktop/tablet/celular.')


if __name__ == '__main__':
    main()
