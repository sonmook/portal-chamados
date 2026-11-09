"""Catálogo administrativo e consulta para o técnico responsável por um chamado."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods
from .acesso import chamados_acessiveis, integrante_ativo, FINALIZADOS
from .audit import registrar
from .models import RespostaPronta


class RespostaProntaForm(forms.ModelForm):
    versao_atual = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    class Meta:
        model = RespostaPronta
        fields = ['nome', 'texto', 'ativa']
        labels = {'nome': 'Nome', 'texto': 'Texto da resposta', 'ativa': 'Disponível para os técnicos'}
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'texto': forms.Textarea(attrs={'class': 'form-control', 'rows': 7}),
            'ativa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['versao_atual'].initial = self.instance.versao if self.instance.pk else 0

    def clean_nome(self):
        return self.cleaned_data['nome'].strip()

    def clean_texto(self):
        return self.cleaned_data['texto'].strip()


def exigir_admin(usuario):
    if not usuario.is_active or not usuario.is_superuser:
        raise PermissionDenied


@login_required
@require_GET
@never_cache
def gerenciar(request):
    exigir_admin(request.user)
    respostas = RespostaPronta.objects.all()
    busca = request.GET.get('q', '').strip()[:100]
    estado = request.GET.get('estado', '')
    if estado not in ('', 'ativas', 'inativas'):
        estado = ''
    if busca:
        respostas = respostas.filter(nome__icontains=busca)
    if estado:
        respostas = respostas.filter(ativa=estado == 'ativas')
    return render(request, 'helpdesk/respostas_prontas/lista.html', {
        'page_obj': Paginator(respostas, 20).get_page(request.GET.get('page')),
        'busca': busca, 'estado': estado,
    })


@login_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
@never_cache
def editar(request, resposta_id=None):
    exigir_admin(request.user)
    resposta = get_object_or_404(RespostaPronta.objects.select_for_update(), pk=resposta_id) if resposta_id else RespostaPronta()
    antes = {campo: getattr(resposta, campo) for campo in ('nome', 'texto', 'ativa')}
    criada = resposta.pk is None
    form = RespostaProntaForm(request.POST if request.method == 'POST' else None, instance=resposta)
    status = 200
    if request.method == 'POST' and form.is_valid():
        if form.cleaned_data['versao_atual'] != resposta.versao:
            form.add_error(None, 'Esta resposta foi alterada em outra página. Reabra a edição antes de salvar.')
            status = 409
        else:
            novos = {campo: form.cleaned_data[campo] for campo in ('nome', 'texto', 'ativa')}
            alterados = {campo: valor for campo, valor in novos.items() if criada or antes[campo] != valor}
            try:
                with transaction.atomic():
                    if criada:
                        resposta.save()
                    elif alterados:
                        atualizados = RespostaPronta.objects.filter(pk=resposta.pk, versao=form.cleaned_data['versao_atual']).update(
                            **novos, versao=F('versao')+1)
                        if not atualizados:
                            form.add_error(None, 'Esta resposta foi alterada em outra página. Reabra a edição antes de salvar.')
                            status = 409
                    if status != 409 and alterados:
                        mudancas = {campo: {'alterado': True} for campo in alterados if campo != 'ativa'}
                        if 'ativa' in alterados:
                            mudancas['ativa'] = {'antes': None if criada else antes['ativa'], 'depois': novos['ativa']}
                        registrar('helpdesk.respostapronta', resposta.pk, 'criado' if criada else 'alterado', mudancas)
                if status != 409:
                    messages.success(request, 'Resposta pronta criada.' if criada else 'Resposta pronta atualizada.')
                    return redirect('gerenciar_respostas_prontas')
            except IntegrityError:
                form.add_error('nome', 'Já existe uma resposta com esse nome. Escolha outro.')
    return render(request, 'helpdesk/respostas_prontas/formulario.html', {'form': form, 'resposta': resposta}, status=status)


@login_required
@require_GET
@never_cache
def obter(request, chamado_id, resposta_id):
    chamado = get_object_or_404(chamados_acessiveis(request.user).select_related('equipe'), pk=chamado_id)
    if (chamado.status in FINALIZADOS or not chamado.equipe.ativa
            or chamado.tecnico_id != request.user.pk or not integrante_ativo(request.user, chamado.equipe_id)):
        raise PermissionDenied
    resposta = get_object_or_404(RespostaPronta, pk=resposta_id, ativa=True)
    return JsonResponse({'nome': resposta.nome, 'texto': resposta.texto})
