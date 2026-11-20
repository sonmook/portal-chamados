"""Gera uma prévia com dados fictícios em banco temporário, sem ler a instalação."""
import io
import os
from pathlib import Path
import secrets
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT/'artifacts'/'relatorio-excel.xlsx'
    os.environ['DJANGO_SETTINGS_MODULE'] = 'core.settings'
    with TemporaryDirectory(prefix='nexaltri-excel-preview-') as tmp:
        from django.conf import settings
        settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': Path(tmp)/'demo.sqlite3'}}
        settings.SECRET_KEY = secrets.token_urlsafe(64)
        settings.MEDIA_ROOT = Path(tmp)/'media'
        settings.ALLOWED_HOSTS = ['testserver']
        import django
        django.setup()
        from django.core.management import call_command
        from django.contrib.auth.models import User
        from django.test import Client
        call_command('migrate', verbosity=0, interactive=False)
        call_command('criar_dados_demo', stdout=io.StringIO())
        from helpdesk.models import CicloAtendimento
        # Cenários exclusivos da prévia fictícia: autores e uma resolução atrasada.
        for ciclo in CicloAtendimento.objects.select_related('chamado'):
            ciclo.fechado_por_id = ciclo.chamado.tecnico_id
            ciclo.save(update_fields=['fechado_por'])
        atrasado = CicloAtendimento.objects.order_by('pk').first()
        if atrasado and atrasado.data_fechamento:
            from datetime import timedelta
            atrasado.data_vencimento = atrasado.data_fechamento-timedelta(hours=2)
            atrasado.save(update_fields=['data_vencimento'])
        admin = User.objects.create_superuser('preview.excel', 'preview@example.invalid', password=None)
        client = Client()
        client.force_login(admin)
        resposta = client.get('/administracao/indicadores/exportar.xlsx', {'periodo': 'sempre'})
        if resposta.status_code != 200:
            raise RuntimeError(f'Prévia retornou HTTP {resposta.status_code}')
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(resposta.content)
        print(f'Prévia criada com dados fictícios de demonstração: {destino}')


if __name__ == '__main__':
    main()
