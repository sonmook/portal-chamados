from django.contrib.admin import AdminSite
from django.contrib.auth.decorators import login_not_required
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect


class PortalAdminSite(AdminSite):
    @method_decorator(never_cache)
    @method_decorator(csrf_protect)
    @login_not_required
    def login(self, request, extra_context=None):
        # Import tardio: o AdminSite é carregado durante a inicialização dos apps.
        from helpdesk.login import limitar_login

        if request.method == 'POST':
            resposta = limitar_login(request)
            if resposta is not None:
                return resposta
        return super().login(request, extra_context=extra_context)
