from django.core.checks import Error, Tags, register
from django.core.exceptions import ImproperlyConfigured

from .calendario_sla import obter_calendario


@register(Tags.compatibility)
def verificar_calendario_sla(app_configs, **kwargs):
    try:
        obter_calendario()
    except ImproperlyConfigured as erro:
        return [Error(str(erro), id='helpdesk.E001')]
    return []
