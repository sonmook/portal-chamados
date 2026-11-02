from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from .proxy import IPProxyConfiavelMiddleware


class ProxyTests(SimpleTestCase):
    def ip(self, origem, header):
        request = RequestFactory().get('/', REMOTE_ADDR=origem, HTTP_X_REAL_IP=header)
        middleware = IPProxyConfiavelMiddleware(lambda req:HttpResponse(req.META['REMOTE_ADDR']))
        return middleware(request).content.decode()

    def test_padrao_nao_confia_em_header(self):
        self.assertEqual(self.ip('192.0.2.10','203.0.113.2'),'192.0.2.10')

    @override_settings(TRUSTED_PROXY_NETWORKS=['192.0.2.10/32'])
    def test_somente_proxy_configurado_pode_encaminhar_ip(self):
        self.assertEqual(self.ip('192.0.2.10','203.0.113.2'),'203.0.113.2')
        self.assertEqual(self.ip('192.0.2.11','203.0.113.2'),'192.0.2.11')
        self.assertEqual(self.ip('192.0.2.10','forjado, 1.2.3.4'),'192.0.2.10')
