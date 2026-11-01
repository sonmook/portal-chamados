import os
from pathlib import Path
import subprocess
import sys
import tempfile

from django.test import SimpleTestCase


class ProducaoTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = os.environ.copy()
        for key in list(self.env):
            if key.startswith('DJANGO_'):
                self.env.pop(key)
        self.env.update({
            'DJANGO_SETTINGS_MODULE':'core.settings_production',
            'DJANGO_SECRET_KEY':'validation-only-key-not-a-real-production-secret-738fd23a',
            'DJANGO_ALLOWED_HOSTS':'portal.example.invalid',
            'DJANGO_DB_PATH':str(Path(self.temp.name)/'db.sqlite3'),
            'DJANGO_MEDIA_ROOT':str(Path(self.temp.name)/'private'),
            'DJANGO_STATIC_ROOT':str(Path(self.temp.name)/'static'),
        })

    def importar(self):
        return subprocess.run([sys.executable,'-c',
            'import django; django.setup(); from django.conf import settings; '
            'assert not settings.DEBUG; assert settings.SECURE_SSL_REDIRECT; '
            'assert settings.SESSION_COOKIE_SECURE; assert settings.CSRF_COOKIE_SECURE'],
            env=self.env, capture_output=True, text=True, timeout=30)

    def test_configuracao_valida(self):
        result=self.importar()
        self.assertEqual(result.returncode,0,result.stderr)

    def test_exige_variaveis_sem_fallback_de_desenvolvimento(self):
        for nome in ['DJANGO_SECRET_KEY','DJANGO_ALLOWED_HOSTS','DJANGO_DB_PATH','DJANGO_MEDIA_ROOT','DJANGO_STATIC_ROOT']:
            with self.subTest(nome=nome):
                valor=self.env.pop(nome)
                result=self.importar()
                self.assertNotEqual(result.returncode,0)
                self.assertIn(nome,result.stderr)
                self.env[nome]=valor

    def test_rejeita_chave_fraca_e_host_aberto(self):
        for nome, valor in [('DJANGO_SECRET_KEY','fraca'),('DJANGO_ALLOWED_HOSTS','*'),
                            ('DJANGO_ALLOWED_HOSTS','https://portal.example.invalid'),
                            ('DJANGO_MEDIA_ROOT','relativo'),
                            ('DJANGO_CSRF_TRUSTED_ORIGINS','http://portal.example.invalid'),
                            ('DJANGO_CSRF_TRUSTED_ORIGINS','https://portal.example.invalid/path')]:
            with self.subTest(nome=nome,valor=valor):
                anterior=self.env.get(nome)
                self.env[nome]=valor
                self.assertNotEqual(self.importar().returncode,0)
                if anterior is None:self.env.pop(nome)
                else:self.env[nome]=anterior

    def test_midia_privada_nao_pode_ficar_nos_estaticos(self):
        self.env['DJANGO_MEDIA_ROOT']=self.env['DJANGO_STATIC_ROOT']+'/uploads'
        self.assertNotEqual(self.importar().returncode,0)

    def test_banco_fora_dos_estaticos(self):
        self.env['DJANGO_DB_PATH']=self.env['DJANGO_STATIC_ROOT']+'/db.sqlite3'
        self.assertNotEqual(self.importar().returncode,0)
