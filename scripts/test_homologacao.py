"""Teste isolado de Docker/HTTPS/backup; remove somente os volumes que cria."""
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        envfile = tmp/'homologacao.env'
        envfile.write_text('STAGING_DOMAIN=localhost\nDJANGO_SECRET_KEY='+secrets.token_urlsafe(64)+'\n'
            'BIND_ADDRESS=127.0.0.1\nHTTP_PORT=18080\nHTTPS_PORT=18443\n'
            'HOMOLOGACAO_ENV_FILE='+str(envfile)+'\n')
        envfile.chmod(0o600)
        project = 'portal-validation-'+secrets.token_hex(4)
        docker_env = os.environ.copy()
        for name in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):
            docker_env.pop(name, None)
        base = ['docker','--host=unix:///var/run/docker.sock','compose','--env-file',str(envfile),
                '-f',str(ROOT/'deploy/compose.yml'),'-p',project]

        def compose(*args, **kwargs):
            return subprocess.run([*base,*args],env=docker_env,cwd=ROOT,check=True,**kwargs)

        def python_app(code, restored=False):
            args = ['exec','-T','app','python','-c',code]
            if restored:
                args = ['run','--rm','--no-deps','--entrypoint','python',
                    '-e','DJANGO_DB_PATH=/data/restaurado/db.sqlite3',
                    '-e','DJANGO_MEDIA_ROOT=/data/restaurado/media','app','-c',code]
            return compose(*args)

        try:
            compose('config','--quiet')
            compose('up','-d','--build','--wait','--wait-timeout','120')
            for _ in range(30):
                cert = subprocess.run([*base,'exec','-T','proxy','cat','/data/caddy/pki/authorities/local/root.crt'],
                    env=docker_env,capture_output=True)
                if cert.returncode==0:break
                time.sleep(1)
            else:raise RuntimeError('Certificado local não foi gerado.')
            ca = tmp/'ca.pem';ca.write_bytes(cert.stdout)
            context = ssl.create_default_context(cafile=str(ca))
            # Somente loopback local: não enviar a homologação ao proxy de saída.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
            for path in ['/contas/login/', '/static/helpdesk/brand/simbolo.svg',
                         '/static/helpdesk/brand/favicon-32.png', '/static/helpdesk/brand/apple-touch-icon.png']:
                for attempt in range(20):
                    try:
                        with opener.open('https://localhost:18443'+path,timeout=5) as response:
                            assert response.status==200,path
                            content = response.read()
                            if path == '/contas/login/':
                                version = (ROOT/'VERSION').read_text(encoding='utf-8').strip()
                                assert f'Versão {version}'.encode('utf-8') in content
                                assert b'helpdesk/brand/simbolo.svg' in content
                            elif path.endswith('.png'):
                                assert content.startswith(b'\x89PNG\r\n\x1a\n'), path
                            else:
                                assert b'<svg' in content, path
                        break
                    except (OSError, urllib.error.URLError) as error:
                        if attempt==19:
                            if isinstance(error, urllib.error.HTTPError):
                                print('HTTP failure:', error.code, 'server:', error.headers.get('Server'), flush=True)
                            raise
                        time.sleep(1)
            try:opener.open('https://localhost:18443/media/privado.pdf',timeout=5)
            except urllib.error.HTTPError as error:assert error.code==404
            else:raise AssertionError('A rota pública de mídia não foi bloqueada.')
            print('PASS: HTTPS com CA verificada, login com versão, marca e favicons servidos; mídia pública bloqueada.',flush=True)
            python_app("""
import django
django.setup()
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from helpdesk.models import Chamado, Comentario, IntegranteEquipe, RegraEncaminhamento, Perfil, RegraConquista, Conquista, ResolucaoConquista, PlanoConquista
user=User.objects.create_user(username='validation-only',is_staff=True)
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile
foto=BytesIO();Image.new('RGB',(32,32),'blue').save(foto,'PNG')
perfil=Perfil.objects.create(usuario=user,cargo='Validação',foto_x=75,foto_y=25,foto_zoom=150)
perfil.foto.save('fixture.png',ContentFile(foto.getvalue()))
t=Chamado.objects.create(titulo='Restauração isolada',descricao='Fixture',solicitante=user,tecnico=user)
IntegranteEquipe.objects.create(equipe=t.equipe,usuario=user,coordenador=True)
RegraEncaminhamento.objects.filter(categoria='Rede').update(ativa=False,versao=7)
Comentario.objects.create(chamado=t,autor=user,texto='Fixture',anexo=SimpleUploadedFile('evidencia.pdf',b'%PDF-1.7 fixture'))
cliente=User.objects.create_user(username='validation-client')
t.solicitante=cliente;t.save(update_fields=['solicitante'])
from django.test import Client
client=Client();client.force_login(user)
response=client.post(f'/chamado/{t.pk}/fechar/',{'resolucao':'Configuração corrigida e validada.'},secure=True,HTTP_HOST='localhost')
assert response.status_code==302
assert Conquista.objects.filter(usuario=user,regra__codigo='primeira-solucao').exists()
admin=User.objects.create_superuser('validation-admin','admin@example.invalid','validation-only-not-production')
client.force_login(admin)
# Configuração anterior à restrição: permanece publicável e restaurável.
assert client.post('/conquistas/nova/',{},secure=True,HTTP_HOST='localhost').status_code==403
plano=PlanoConquista.objects.create(nome='Trilha de validação',descricao='Fixture',icone='escudo',
    alvo='pessoa',metrica='no_prazo',bronze=1,prata=2,ouro=3,contagem='historico')
assert plano.estado=='rascunho' and not plano.niveis.exists()
from helpdesk.construtor_conquistas import previsao
response=client.post(f'/conquistas/planos/{plano.pk}/publicar/',{'confirmacao':previsao(plano)['token']},secure=True,HTTP_HOST='localhost')
assert response.status_code==302
assert Conquista.objects.filter(regra__plano=plano,usuario=user,nivel='bronze').exists()


""")
            compose('stop','app')
            compose('run','--rm','--no-deps','--entrypoint','python','app','manage.py','backup_homologacao',
                '/data/backups/validation','--confirmar-escritores-parados')
            compose('run','--rm','--no-deps','--entrypoint','python','app','manage.py','backup_homologacao',
                '/data/restaurado','--restaurar','/data/backups/validation')
            python_app("""
import django
django.setup()
from django.contrib.auth.models import User
from helpdesk.models import Chamado, Comentario, RegistroAuditoria, IntegranteEquipe, RegraEncaminhamento, Perfil, RegraConquista, Conquista, ResolucaoConquista, PlanoConquista
assert User.objects.filter(username='validation-only').exists()
assert RegraConquista.objects.filter(codigo='guardiao-sla',meta=50,icone='escudo').exists()
assert Chamado.objects.filter(titulo='Restauração isolada').exists()
comment=Comentario.objects.get(texto='Fixture')
assert comment.anexo.read()==b'%PDF-1.7 fixture'
assert RegistroAuditoria.objects.filter(objeto='helpdesk.chamado').exists()
t=Chamado.objects.get(titulo='Restauração isolada')
assert t.equipe.triagem_padrao
assert t.tecnico.username=='validation-only'
assert IntegranteEquipe.objects.filter(equipe=t.equipe,usuario=t.tecnico,coordenador=True).exists()
regra=RegraEncaminhamento.objects.get(categoria='Rede')
assert not regra.ativa and regra.versao==7
perfil=Perfil.objects.get(usuario__username='validation-only')
assert perfil.cargo=='Validação'
assert (perfil.foto_x,perfil.foto_y,perfil.foto_zoom)==(75,25,150)
with perfil.foto.open('rb') as imagem:
    assert imagem.read().startswith(bytes([137, 80, 78, 71]))
assert ResolucaoConquista.objects.filter(chamado=t,usuario__username='validation-only',no_prazo=True).exists()
assert Conquista.objects.filter(usuario__username='validation-only',regra__codigo='primeira-solucao',nome='Primeira solução',icone='foguete').exists()
plano=PlanoConquista.objects.get(nome='Trilha de validação',estado='publicada')
assert plano.niveis.count()==3
assert Conquista.objects.filter(regra__plano=plano,usuario__username='validation-only',nivel='bronze',meta=1).exists()
print('PASS: usuário, chamado, comentário, auditoria, anexos, equipes, perfil e conquistas com plano e níveis restaurados em destino separado.')
""",restored=True)
        except Exception:
            subprocess.run([*base,'logs','--tail=60','app','proxy'],env=docker_env,cwd=ROOT)
            raise
        finally:
            compose('down','--volumes','--remove-orphans')


if __name__=='__main__':
    main()
