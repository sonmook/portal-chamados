from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from .models import Chamado


class IdiomaPortalTests(TestCase):
    def test_ultima_interacao_em_portugues_no_idioma_padrao(self):
        usuario = User.objects.create_user('cliente-idioma')
        chamado = Chamado.objects.create(titulo='Teste de idioma', descricao='Fixture', solicitante=usuario)
        instante = timezone.now() - timedelta(days=1, hours=23, minutes=5)
        Chamado.objects.filter(pk=chamado.pk).update(ultima_interacao_em=instante)
        self.client.force_login(usuario)
        # Usa a configuração real, sem definir pt-br artificialmente no teste.
        with translation.override(settings.LANGUAGE_CODE):
            resposta = self.client.get(reverse('lista_chamados'))
        texto = resposta.content.decode().replace('\xa0', ' ').replace('&nbsp;', ' ')
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('1 dia, 23 horas atrás', texto)
        self.assertNotIn('1 day', texto)
