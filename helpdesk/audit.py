from contextvars import ContextVar

from .models import RegistroAuditoria

ator_atual = ContextVar('ator_auditoria', default=None)
origem_atual = ContextVar('origem_auditoria', default='sistema')


class AuditoriaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = ator_atual.set(request.user.pk if request.user.is_authenticated else None)
        origem = origem_atual.set('admin' if request.path.startswith('/admin/') else 'portal')
        try:
            return self.get_response(request)
        finally:
            origem_atual.reset(origem)
            ator_atual.reset(token)


def registrar(objeto, pk, acao, alteracoes):
    return RegistroAuditoria.objects.create(
        ator_id=ator_atual.get(), origem=origem_atual.get(), objeto=objeto,
        objeto_id=pk, acao=acao, alteracoes=alteracoes,
    )
