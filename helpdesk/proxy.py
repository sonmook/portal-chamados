from ipaddress import ip_address, ip_network
from django.conf import settings


class IPProxyConfiavelMiddleware:
    """Aceita X-Real-IP somente de endereços de proxy explicitamente configurados."""
    def __init__(self, get_response):
        self.get_response = get_response
        self.redes = [ip_network(rede) for rede in getattr(settings, 'TRUSTED_PROXY_NETWORKS', [])]

    def __call__(self, request):
        try:
            origem = ip_address(request.META.get('REMOTE_ADDR', ''))
            if any(origem in rede for rede in self.redes):
                cliente = ip_address(request.META.get('HTTP_X_REAL_IP', ''))
                request.META['REMOTE_ADDR'] = str(cliente)
        except ValueError:
            pass
        return self.get_response(request)
