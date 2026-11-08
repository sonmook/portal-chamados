"""Preferência pessoal de apresentação; não altera consultas ou permissões."""
import json
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from .models import PreferenciaListaChamados

COLUNAS = ('ticket', 'assunto', 'abertura', 'status', 'prioridade', 'sla', 'interacao', 'solicitante', 'tecnico', 'acoes')


def ordem_valida(ordem):
    return (isinstance(ordem, list) and len(ordem) == len(COLUNAS)
        and all(isinstance(campo, str) for campo in ordem) and set(ordem) == set(COLUNAS))


def ordem_usuario(usuario):
    ordem = PreferenciaListaChamados.objects.filter(usuario=usuario).values_list('ordem', flat=True).first()
    return ordem if ordem_valida(ordem) else list(COLUNAS)


@login_required
@require_POST
@never_cache
def salvar_ordem(request):
    if not request.user.is_active:
        raise PermissionDenied
    if request.content_type != 'application/json' or len(request.body) > 4096:
        return JsonResponse({'erro': 'Envie a ordem das colunas em JSON.'}, status=400)
    try:
        dados = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'erro': 'JSON inválido.'}, status=400)
    if not isinstance(dados, dict) or set(dados) != {'ordem'} or not ordem_valida(dados['ordem']):
        return JsonResponse({'erro': 'A ordem deve conter todas as colunas, sem repetições.'}, status=400)
    PreferenciaListaChamados.objects.update_or_create(usuario=request.user, defaults={'ordem': dados['ordem']})
    return JsonResponse({'ordem': dados['ordem']})
