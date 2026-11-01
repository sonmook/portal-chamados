"""Configuração de produção: falha ao iniciar sem valores explícitos."""
import os
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured
from .settings import *  # noqa: F403


def obrigatorio(nome):
    valor = os.environ.get(nome, '').strip()
    if not valor:
        raise ImproperlyConfigured(f'Configure {nome} para produção.')
    return valor


def caminho(nome):
    valor = Path(obrigatorio(nome))
    if not valor.is_absolute():
        raise ImproperlyConfigured(f'{nome} deve ser um caminho absoluto.')
    return valor.resolve()


DEBUG = False
SECRET_KEY = obrigatorio('DJANGO_SECRET_KEY')
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith('django-insecure-') or len(set(SECRET_KEY)) < 5:
    raise ImproperlyConfigured('DJANGO_SECRET_KEY deve ser aleatória, com pelo menos 50 caracteres.')
ALLOWED_HOSTS = [host.strip() for host in obrigatorio('DJANGO_ALLOWED_HOSTS').split(',') if host.strip()]
if not ALLOWED_HOSTS or any('*' in host or '/' in host or ':' in host for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS deve conter nomes de host explícitos, sem esquema, porta ou wildcard.')
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()]
for origin in CSRF_TRUSTED_ORIGINS:
    parsed = urlparse(origin)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.path or '*' in origin:
        raise ImproperlyConfigured('Origens CSRF devem ser origens HTTPS explícitas, sem caminho.')
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': caminho('DJANGO_DB_PATH')}}
MEDIA_ROOT = caminho('DJANGO_MEDIA_ROOT')
STATIC_ROOT = caminho('DJANGO_STATIC_ROOT')
if STATIC_ROOT == MEDIA_ROOT or STATIC_ROOT in MEDIA_ROOT.parents or MEDIA_ROOT in STATIC_ROOT.parents:
    raise ImproperlyConfigured('Diretórios de mídia privada e estáticos públicos devem ser separados.')
if STATIC_ROOT in DATABASES['default']['NAME'].parents or STATIC_ROOT == DATABASES['default']['NAME']:
    raise ImproperlyConfigured('O banco deve ficar fora dos estáticos públicos.')
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
# Habilitar somente com proxy confiável que remova/substitua o cabeçalho recebido.
if os.environ.get('DJANGO_TRUST_PROXY_SSL_HEADER') == '1':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
