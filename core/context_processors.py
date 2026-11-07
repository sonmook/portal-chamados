from .version import VERSION


def portal(request):
    from helpdesk.notificacoes import notificacoes_visiveis
    total = notificacoes_visiveis(request.user).filter(lida_em__isnull=True).count()
    return {'portal_version': VERSION, 'notificacoes_nao_lidas': total}
