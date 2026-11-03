from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .audit import registrar
from .forms_equipes import EquipeForm
from .models import Equipe, IntegranteEquipe
from .acesso import FINALIZADOS


class EquipeAlterada(Exception):
    pass


def snapshot(equipe):
    return {'nome': equipe.nome, 'descricao': equipe.descricao, 'ativa': equipe.ativa,
            'integrantes': sorted(equipe.vinculos.values_list('usuario_id', flat=True)),
            'coordenadores': sorted(equipe.vinculos.filter(coordenador=True).values_list('usuario_id', flat=True))}


@login_required
@require_http_methods(['GET'])
def gerenciar_equipes(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    equipes = Equipe.objects.annotate(total_integrantes=Count('vinculos', distinct=True),
        total_pendentes=Count('chamados', filter=~Q(chamados__status__in=FINALIZADOS), distinct=True)).prefetch_related(
        Prefetch('vinculos', queryset=IntegranteEquipe.objects.filter(coordenador=True).select_related('usuario'),
                 to_attr='coordenacao')
    ).order_by('nome', 'pk')
    busca = request.GET.get('q', '').strip()
    if busca:
        equipes = equipes.filter(nome__icontains=busca)
    return render(request, 'helpdesk/equipes/lista.html', {
        'page_obj': Paginator(equipes, 20).get_page(request.GET.get('page')), 'busca': busca,
    })


@login_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def editar_equipe(request, equipe_id=None):
    if not request.user.is_superuser:
        raise PermissionDenied
    equipe = get_object_or_404(Equipe.objects.select_for_update(), pk=equipe_id) if equipe_id else Equipe()
    antes = snapshot(equipe) if equipe.pk else None
    form = EquipeForm(request.POST if request.method == 'POST' else None, instance=equipe)
    status = 200
    if request.method == 'POST' and form.is_valid():
        if equipe.pk and form.cleaned_data['versao_atual'] != equipe.versao:
            form.add_error(None, 'A equipe foi alterada por outra pessoa. Reabra a página antes de salvar.')
            status = 409
        else:
            ids = sorted(u.pk for u in form.cleaned_data['integrantes'])
            usuarios = list(User.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
            if len(usuarios) != len(ids) or any(not u.is_active or not u.is_staff for u in usuarios):
                form.add_error('integrantes', 'A situação de um integrante mudou. Atualize a seleção.')
            else:
                try:
                    with transaction.atomic():
                        equipe = form.save(commit=False)
                        equipe.versao += 1
                        if equipe.pk:
                            atualizado = Equipe.objects.filter(pk=equipe.pk, versao=form.cleaned_data['versao_atual']).update(
                                nome=equipe.nome, descricao=equipe.descricao, ativa=equipe.ativa, versao=F('versao') + 1)
                            if not atualizado:
                                raise EquipeAlterada
                        else:
                            equipe.save()
                        coordenadores = {u.pk for u in form.cleaned_data['coordenadores']}
                        equipe.vinculos.exclude(usuario_id__in=ids).delete()
                        for usuario_id in ids:
                            IntegranteEquipe.objects.update_or_create(equipe=equipe, usuario_id=usuario_id,
                                defaults={'coordenador': usuario_id in coordenadores})
                        depois = snapshot(equipe)
                        alteracoes = {}
                        for campo, valor in depois.items():
                            if antes is None or antes[campo] != valor:
                                alteracoes[campo] = {'alterado': True} if campo in ('nome', 'descricao') else {
                                    'antes': antes[campo] if antes else None, 'depois': valor,
                                }
                        if alteracoes:
                            registrar('helpdesk.equipe', equipe.pk, 'criado' if antes is None else 'alterado', alteracoes)
                except EquipeAlterada:
                    form.add_error(None, 'A equipe foi alterada por outra pessoa. Reabra a página antes de salvar.')
                    status = 409
                except IntegrityError:
                    form.add_error('nome', 'Não foi possível salvar. Confira se já existe uma equipe com esse nome.')
                else:
                    messages.success(request, 'Equipe salva com sucesso.')
                    return redirect('gerenciar_equipes')
    return render(request, 'helpdesk/equipes/formulario.html', {'form': form, 'equipe': equipe}, status=status)
