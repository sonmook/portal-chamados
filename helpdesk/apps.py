from django.apps import AppConfig

class HelpdeskConfig(AppConfig):
    """
    Configuração principal do aplicativo de Helpdesk.
    """
    name = 'helpdesk'

    def ready(self):
        from . import signals  # noqa: F401
