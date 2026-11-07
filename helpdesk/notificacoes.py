"""Avisos transacionais; destinatários e visibilidade seguem o acesso atual ao chamado."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache

from .acesso import chamados_acessiveis
from .models import Chamado, IntegranteEquipe, Notificacao


def notificacoes_visiveis(usuario):
    if not usuario.is_authenticated or not usuario.is_active:
        return Notificacao.objects.none()
    return Notificacao.objects.filter(destinatario_id=usuario.pk,
        chamado_id__in=chamados_acessiveis(usuario).order_by().values('pk'))


def participantes(chamado):
    ids = {chamado.solicitante_id, chamado.tecnico_id}
    if not chamado.tecnico_id:
        ids.update(IntegranteEquipe.objects.filter(equipe_id=chamado.equipe_id,
            equipe__ativa=True, coordenador=True).values_list('usuario_id', flat=True))
    return ids - {None}


@transaction.atomic
def gerar(chamado, ator_id, tipo, evento, candidatos):
    # Não guardamos cópias de título, comentário, solução ou nome de equipes no aviso.
    membros = IntegranteEquipe.objects.filter(equipe_id=chamado.equipe_id,
        equipe__ativa=True).values('usuario_id')
    aptos = User.objects.filter(is_active=True, pk__in=candidatos).exclude(pk=ator_id).filter(
        Q(pk=chamado.solicitante_id) | Q(is_superuser=True) | Q(is_staff=True, pk__in=membros))
    total = 0
    for destinatario in aptos.values_list('pk', flat=True):
        _, criada = Notificacao.objects.get_or_create(destinatario_id=destinatario, evento=evento,
            defaults={'chamado_id': chamado.pk, 'tipo': tipo})
        total += int(criada)
    return total


def notificar_atribuicao(chamado, ator_id, tecnico_anterior, equipe_anterior):
    chamado = Chamado.objects.get(pk=chamado.pk)
    if (chamado.tecnico_id, chamado.equipe_id) == (tecnico_anterior, equipe_anterior):
        return
    tipo = 'transferencia' if chamado.equipe_id != equipe_anterior else 'atribuicao'
    gerar(chamado, ator_id, tipo, f'atribuicao:{chamado.pk}:{chamado.versao_atribuicao}',
          participantes(chamado) | ({tecnico_anterior} if tecnico_anterior else set()))


def notificar_resposta(comentario):
    chamado = Chamado.objects.get(pk=comentario.chamado_id)
    gerar(chamado, comentario.autor_id, 'resposta', f'resposta:{comentario.pk}', participantes(chamado))


def notificar_resolucao(chamado, ator_id):
    chamado = Chamado.objects.get(pk=chamado.pk)
    gerar(chamado, ator_id, 'resolucao', f'resolucao:{chamado.pk}', participantes(chamado))


@login_required
@never_cache
@require_GET
def listar_notificacoes(request):
    filtro = request.GET.get('filtro', '')
    if filtro not in ('', 'nao_lidas'):
        filtro = ''
    avisos = notificacoes_visiveis(request.user)
    if filtro == 'nao_lidas':
        avisos = avisos.filter(lida_em__isnull=True)
    pagina = Paginator(avisos.select_related('chamado'), 20).get_page(request.GET.get('page'))
    return render(request, 'helpdesk/notificacoes.html', {'page_obj': pagina, 'filtro': filtro})


@login_required
@require_POST
@transaction.atomic
def ler_notificacao(request, notificacao_id):
    aviso = get_object_or_404(notificacoes_visiveis(request.user).select_for_update(), pk=notificacao_id)
    Notificacao.objects.filter(pk=aviso.pk, lida_em__isnull=True).update(lida_em=timezone.now())
    if request.POST.get('abrir') == '1':
        return redirect('detalhes_chamado', id=aviso.chamado_id)
    return redirect('listar_notificacoes')


@login_required
@require_POST
@transaction.atomic
def ler_todas_notificacoes(request):
    total = notificacoes_visiveis(request.user).filter(lida_em__isnull=True).update(lida_em=timezone.now())
    messages.success(request, f'{total} notificação marcada como lida.' if total == 1 else f'{total} notificações marcadas como lidas.')
    return redirect('listar_notificacoes')
