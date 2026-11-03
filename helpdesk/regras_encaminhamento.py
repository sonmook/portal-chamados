from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Exists, F, OuterRef
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .audit import registrar
from .forms_encaminhamento import RegraEncaminhamentoForm
from .models import Chamado, Equipe, IntegranteEquipe, RegraEncaminhamento


@login_required
@require_http_methods(['GET'])
def listar_regras(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    regras = RegraEncaminhamento.objects.select_related('equipe').annotate(
        tem_tecnico=Exists(IntegranteEquipe.objects.filter(
            equipe_id=OuterRef('equipe_id'), usuario__is_active=True, usuario__is_staff=True,
        ))
    )
    categorias = set(RegraEncaminhamento.objects.values_list('categoria', flat=True))
    return render(request, 'helpdesk/encaminhamento/lista.html', {
        'regras': regras, 'pode_criar': any(c not in categorias for c, _ in Chamado.CATEGORIA_CHOICES),
        'triagem': Equipe.objects.filter(triagem_padrao=True).first(),
    })


@login_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def editar_regra(request, regra_id=None):
    if not request.user.is_superuser:
        raise PermissionDenied
    regra = get_object_or_404(RegraEncaminhamento.objects.select_for_update(), pk=regra_id) if regra_id else RegraEncaminhamento()
    antes = {'categoria': regra.categoria, 'equipe_id': regra.equipe_id, 'ativa': regra.ativa,
             'versao': regra.versao} if regra.pk else None
    form = RegraEncaminhamentoForm(request.POST if request.method == 'POST' else None, instance=regra)
    status = 200
    if request.method == 'POST' and form.is_valid():
        if regra.pk and form.cleaned_data['versao_atual'] != regra.versao:
            form.add_error(None, 'A regra foi alterada por outra pessoa. Reabra a página antes de salvar.')
            status = 409
        else:
            destino = get_object_or_404(Equipe.objects.select_for_update(), pk=form.cleaned_data['equipe'].pk)
            if form.cleaned_data['ativa'] and not destino.ativa:
                form.add_error('equipe', 'A equipe foi desativada. Escolha outra ou desative a regra.')
            else:
                try:
                    with transaction.atomic():
                        if regra.pk:
                            atualizado = RegraEncaminhamento.objects.filter(pk=regra.pk,
                                versao=form.cleaned_data['versao_atual']).update(
                                    equipe=destino, ativa=form.cleaned_data['ativa'], versao=F('versao') + 1)
                        else:
                            regra = form.save(commit=False)
                            regra.versao = 1
                            regra.save()
                            atualizado = 1
                        if atualizado:
                            regra.refresh_from_db()
                            depois = {'categoria': regra.categoria, 'equipe_id': regra.equipe_id,
                                      'ativa': regra.ativa, 'versao': regra.versao}
                            registrar('helpdesk.regraencaminhamento', regra.pk, 'alterado' if antes else 'criado', {
                                c: {'antes': antes[c] if antes else None, 'depois': valor}
                                for c, valor in depois.items() if antes is None or antes[c] != valor
                            })
                except IntegrityError:
                    form.add_error(None, 'Já existe uma regra para essa categoria. Atualize a página e edite a existente.')
                else:
                    if not atualizado:
                        form.add_error(None, 'A regra foi alterada por outra pessoa. Reabra a página antes de salvar.')
                        status = 409
                    else:
                        messages.success(request, 'Regra salva. O encaminhamento vale para novos chamados.')
                        return redirect('listar_regras_encaminhamento')
    return render(request, 'helpdesk/encaminhamento/formulario.html', {'form': form, 'regra': regra}, status=status)
