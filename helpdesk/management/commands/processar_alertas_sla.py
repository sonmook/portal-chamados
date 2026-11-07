import time
import tempfile
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, close_old_connections
from django.utils import timezone
from helpdesk.sla import processar_alertas_sla


class Command(BaseCommand):
    help = 'Gera avisos de SLA e de chamados sem responsável, uma vez ou a cada minuto.'

    def add_arguments(self, parser):
        parser.add_argument('--continuo', action='store_true', help='Mantém a verificação periódica em execução.')
        parser.add_argument('--intervalo', type=int, default=60, help='Segundos entre verificações (5 a 3600; padrão 60).')

    def handle(self, *args, **options):
        intervalo = options['intervalo']
        if not 5 <= intervalo <= 3600:
            raise CommandError('O intervalo deve estar entre 5 e 3600 segundos.')
        try:
            while True:
                close_old_connections()
                try:
                    total = processar_alertas_sla()
                    if options['continuo']:
                        (Path(tempfile.gettempdir()) / 'portal-sla-heartbeat').touch(mode=0o600)
                    self.stdout.write(f"Verificação de SLA {timezone.localtime():%d/%m/%Y %H:%M:%S}: "
                        f"{total['verificados']} chamados; novos avisos — "
                        f"próximos: {total['sla_proximo']}, vencidos: {total['sla_vencido']}, "
                        f"sem responsável: {total['sem_responsavel']}.")
                except DatabaseError as error:
                    if not options['continuo']:
                        raise CommandError('Falha no banco ao processar alertas de SLA. Tente novamente.') from error
                    self.stderr.write(f'Falha no banco ({type(error).__name__}); nova tentativa no próximo ciclo.')
                finally:
                    close_old_connections()
                if not options['continuo']:
                    break
                time.sleep(intervalo)
        except KeyboardInterrupt:
            self.stdout.write('Verificação de SLA encerrada.')
