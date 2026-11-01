from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from helpdesk.backups import criar_backup, restaurar_backup


class Command(BaseCommand):
    help = 'Backup ou restauração não destrutiva de SQLite e uploads privados.'

    def add_arguments(self, parser):
        parser.add_argument('destino', type=Path)
        parser.add_argument('--restaurar', type=Path, help='Backup a restaurar para um diretório novo.')
        parser.add_argument('--confirmar-escritores-parados', action='store_true')

    def handle(self, *args, **options):
        try:
            if options['restaurar']:
                restaurar_backup(options['restaurar'], options['destino'])
            else:
                if not options['confirmar_escritores_parados']:
                    raise CommandError('Pare todos os processos que gravam banco/uploads e confirme com --confirmar-escritores-parados.')
                db = settings.DATABASES['default']
                if db['ENGINE'] != 'django.db.backends.sqlite3':
                    raise CommandError('Este procedimento suporta apenas SQLite.')
                criar_backup(db['NAME'], settings.MEDIA_ROOT, options['destino'])
        except (ValueError, OSError) as erro:
            raise CommandError(str(erro)) from erro
        self.stdout.write(self.style.SUCCESS('Cópia concluída e integridade verificada.'))
