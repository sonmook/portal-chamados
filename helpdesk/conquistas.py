"""Concessões idempotentes a partir de resoluções válidas registradas pelo portal."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, F
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from django import forms

from .acesso import equipes_acessiveis, integrante_ativo
from .audit import registrar
from .models import Chamado, Conquista, RegraConquista, ResolucaoConquista


def eventos_regra(regra):
    eventos = ResolucaoConquista.objects.filter(concluido_em__gte=regra.inicio_em)
    return eventos.filter(no_prazo=True) if regra.metrica == 'no_prazo' else eventos


def conceder(regra, destinatario_id, valor):
    campo = 'usuario_id' if regra.alvo == 'pessoa' else 'equipe_id'
    conquista, criada = Conquista.objects.get_or_create(regra=regra, **{campo: destinatario_id}, defaults={
        'nome': regra.nome, 'descricao': regra.descricao, 'meta': regra.meta, 'versao_regra': regra.versao,
    })
    if criada:
        registrar('helpdesk.conquista', conquista.pk, 'concedido', {
            'regra_id': regra.pk, campo: destinatario_id, 'meta': regra.meta,
            'versao_regra': regra.versao, 'valor': valor,
        })
    return conquista if criada else None


@transaction.atomic
def registrar_resolucao(chamado):
    chamado = Chamado.objects.select_related('tecnico').get(pk=chamado.pk)
    regras = list(RegraConquista.objects.filter(ativa=True))
    if (chamado.status != 'Resolvido' or not chamado.data_fechamento
            or chamado.fechado_por_id != chamado.tecnico_id
            or chamado.solicitante_id == chamado.tecnico_id
            or not chamado.tecnico_id or not integrante_ativo(chamado.tecnico, chamado.equipe_id)):
        return []
    # Sem retroatividade: só o fluxo de encerramento chama este serviço.
    _, criado = ResolucaoConquista.objects.get_or_create(chamado=chamado, defaults={
        'usuario_id': chamado.tecnico_id, 'equipe_id': chamado.equipe_id,
        'concluido_em': chamado.data_fechamento,
        'no_prazo': bool(chamado.data_vencimento and chamado.data_fechamento <= chamado.data_vencimento),
    })
    if not criado:
        return []
    novas = []
    for regra in regras:
        campo = 'usuario_id' if regra.alvo == 'pessoa' else 'equipe_id'
        destinatario = chamado.tecnico_id if regra.alvo == 'pessoa' else chamado.equipe_id
        total = eventos_regra(regra).filter(**{campo: destinatario}).count()
        if total >= regra.meta:
            conquista = conceder(regra, destinatario, total)
            if conquista:
                novas.append(conquista)
    return novas


def reavaliar_regra(regra):
    if not regra.ativa:
        return
    campo = 'usuario_id' if regra.alvo == 'pessoa' else 'equipe_id'
    for linha in eventos_regra(regra).values(campo).annotate(total=Count('pk')).filter(total__gte=regra.meta):
        conceder(regra, linha[campo], linha['total'])


def cartoes(regras, *, usuario=None, equipe=None):
    destinatario = {'usuario': usuario} if usuario else {'equipe': equipe}
    recebidas = {c.regra_id: c for c in Conquista.objects.filter(**destinatario)}
    resultado = []
    for regra in regras:
        total = eventos_regra(regra).filter(**destinatario).count()
        resultado.append({'regra': regra, 'total': total, 'percentual': min(100, total * 100 // regra.meta),
                          'conquista': recebidas.get(regra.pk)})
    return resultado


@login_required
@require_GET
def minhas_conquistas(request):
    equipes = equipes_acessiveis(request.user).order_by('nome')
    equipe = None
    if request.GET.get('equipe'):
        try:
            equipe = get_object_or_404(equipes, pk=int(request.GET['equipe']))
        except (ValueError, OverflowError):
            from django.http import Http404
            raise Http404
    else:
        equipe = equipes.first()
    regras = list(RegraConquista.objects.all())
    return render(request, 'helpdesk/conquistas/lista.html', {
        'pessoais': cartoes([r for r in regras if r.alvo == 'pessoa'], usuario=request.user),
        'coletivas': cartoes([r for r in regras if r.alvo == 'equipe'], equipe=equipe) if equipe else [],
        'equipes': equipes, 'equipe_selecionada': equipe,
    })


class RegraConquistaForm(forms.ModelForm):
    versao_atual = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    class Meta:
        model = RegraConquista
        fields = ['nome', 'descricao', 'meta', 'ativa']
        labels = {'nome': 'Nome', 'descricao': 'Descrição', 'meta': 'Meta', 'ativa': 'Concessões ativas'}
        widgets = {'nome': forms.TextInput(attrs={'class': 'form-control'}),
                   'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                   'meta': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 100000})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['versao_atual'].initial = self.instance.versao


@login_required
@require_GET
def gerenciar_conquistas(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    return render(request, 'helpdesk/conquistas/gerenciar.html', {
        'regras': RegraConquista.objects.all(),
        'recentes': Conquista.objects.select_related('usuario', 'equipe')[:20],
    })


@login_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def editar_conquista(request, regra_id):
    if not request.user.is_superuser:
        raise PermissionDenied
    regra = get_object_or_404(RegraConquista.objects.select_for_update(), pk=regra_id)
    antes = {c: getattr(regra, c) for c in ('nome', 'descricao', 'meta', 'ativa')}
    form = RegraConquistaForm(request.POST if request.method == 'POST' else None, instance=regra)
    status = 200
    if request.method == 'POST' and form.is_valid():
        if regra.versao != form.cleaned_data['versao_atual']:
            form.add_error(None, 'Esta regra foi alterada. Reabra a página antes de salvar.')
            status = 409
        else:
            campos = {c: form.cleaned_data[c] for c in antes}
            alterada = RegraConquista.objects.filter(pk=regra.pk, versao=form.cleaned_data['versao_atual']).update(
                **campos, versao=F('versao') + 1)
            if not alterada:
                form.add_error(None, 'Esta regra foi alterada. Reabra a página antes de salvar.')
                status = 409
            else:
                regra.refresh_from_db()
                registrar('helpdesk.regraconquista', regra.pk, 'alterado', {
                    c: {'alterado': True} if c in ('nome', 'descricao') else {'antes': antes[c], 'depois': valor}
                    for c, valor in campos.items() if antes[c] != valor
                })
                reavaliar_regra(regra)
                messages.success(request, 'Regra salva. As resoluções elegíveis desde o início da contagem foram reavaliadas.')
                return redirect('gerenciar_conquistas')
    return render(request, 'helpdesk/conquistas/formulario.html', {'form': form, 'regra': regra}, status=status)
