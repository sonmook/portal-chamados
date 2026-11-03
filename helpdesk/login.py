import hashlib
import time
from datetime import datetime, timezone

from django.contrib.auth.views import LoginView
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse

from .models import JanelaLogin


def limitar_login(request):
    """Limite compartilhado no banco: 10 posts conta/IP e 50 por IP em 15 min."""
    agora = int(time.time())
    janela = agora // 900
    expira = datetime.fromtimestamp((janela + 1) * 900, tz=timezone.utc)
    # Não confiar em X-Forwarded-For enviado pelo cliente.
    ip = request.META.get('REMOTE_ADDR', '')
    conta = request.POST.get('username', '').strip().casefold()
    JanelaLogin.objects.filter(expira_em__lte=datetime.fromtimestamp(agora, tz=timezone.utc)).delete()
    for identidade, limite in [(f'ip:{ip}', 50), (f'conta:{ip}:{conta}', 10)]:
        chave = hashlib.sha256(f'{janela}:{identidade}'.encode()).hexdigest()
        with transaction.atomic():
            registro, _ = JanelaLogin.objects.get_or_create(chave=chave, defaults={'expira_em': expira})
            permitido = JanelaLogin.objects.filter(pk=registro.pk, tentativas__lt=limite).update(tentativas=F('tentativas') + 1)
        if not permitido:
            resposta = HttpResponse('Muitas tentativas. Aguarde antes de tentar novamente.', status=429)
            resposta['Retry-After'] = str((janela + 1) * 900 - agora)
            resposta['Cache-Control'] = 'no-store'
            return resposta
    return None


class LoginLimitadoView(LoginView):
    def post(self, request, *args, **kwargs):
        resposta = limitar_login(request)
        if resposta is not None:
            return resposta
        return super().post(request, *args, **kwargs)
