from .version import VERSION


def portal(request):
    from helpdesk.notificacoes import notificacoes_visiveis
    total = notificacoes_visiveis(request.user).filter(lida_em__isnull=True).count()
    from helpdesk.administracao import SECOES
    pagina = getattr(request.resolver_match, 'url_name', None)
    return {'portal_version': VERSION, 'notificacoes_nao_lidas': total,
            'secao_administrativa': SECOES.get(pagina, ''),
            'central_administrativa': pagina == 'central_administracao'}
