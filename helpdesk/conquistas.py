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
from .models import Chamado, Conquista, RegraConquista, ResolucaoConquista, PlanoConquista
from .visual_conquistas import ICONES


def eventos_regra(regra):
    eventos = ResolucaoConquista.objects.filter(concluido_em__gte=regra.inicio_em)
    return eventos.filter(no_prazo=True) if regra.metrica == 'no_prazo' else eventos


def conceder(regra, destinatario_id, valor):
    campo = 'usuario_id' if regra.alvo == 'pessoa' else 'equipe_id'
    conquista, criada = Conquista.objects.get_or_create(regra=regra, **{campo: destinatario_id}, defaults={
        'nome': regra.nome, 'descricao': regra.descricao, 'meta': regra.meta, 'versao_regra': regra.versao, 'icone': regra.icone, 'nivel': regra.nivel,
    })
    if criada:
        registrar('helpdesk.conquista', conquista.pk, 'concedido', {
            'regra_id': regra.pk, campo: destinatario_id, 'meta': regra.meta,
            'versao_regra': regra.versao, 'valor': valor, 'icone': regra.icone,
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
    totais = {}
    for regra in regras:
        campo = 'usuario_id' if regra.alvo == 'pessoa' else 'equipe_id'
        destinatario = chamado.tecnico_id if regra.alvo == 'pessoa' else chamado.equipe_id
        chave = (campo, destinatario, regra.metrica, regra.inicio_em)
        if chave not in totais:
            totais[chave] = eventos_regra(regra).filter(**{campo: destinatario}).count()
        total = totais[chave]
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
    grupos = {}
    for regra in regras:
        chave = ('plano', regra.plano_id) if regra.plano_id else ('regra', regra.pk)
        grupos.setdefault(chave, []).append(regra)
    resultado = []
    totais = {}
    for niveis in grupos.values():
        niveis.sort(key=lambda r: r.meta)
        pendentes = [r for r in niveis if r.pk not in recebidas]
        regra = pendentes[0] if pendentes else niveis[-1]
        chave = (regra.metrica, regra.inicio_em)
        if chave not in totais:
            totais[chave] = eventos_regra(regra).filter(**destinatario).count()
        total = totais[chave]
        conquista = recebidas.get(regra.pk)
        resultado.append({'regra': regra, 'total': total, 'percentual': min(100, total * 100 // regra.meta),
                          'conquista': conquista, 'visual': (conquista or regra).visual,
                          'faltam': max(0, regra.meta-total), 'plano': regra.plano if regra.plano_id else None,
                          'niveis': [{'regra':r,'conquista':recebidas.get(r.pk)} for r in niveis] if regra.plano_id else [],
                          'desbloqueadas': sum(r.pk in recebidas for r in niveis), 'total_medalhas':len(niveis)})
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
    regras = list(RegraConquista.objects.select_related('plano').all())
    pessoais = cartoes([r for r in regras if r.alvo == 'pessoa'], usuario=request.user)
    return render(request, 'helpdesk/conquistas/lista.html', {
        'pessoais': pessoais, 'total_pessoais': sum(item['total_medalhas'] for item in pessoais), 'desbloqueadas': sum(item['desbloqueadas'] for item in pessoais),
        'coletivas': cartoes([r for r in regras if r.alvo == 'equipe'], equipe=equipe) if equipe else [],
        'equipes': equipes, 'equipe_selecionada': equipe,
    })


class RegraConquistaForm(forms.ModelForm):
    versao_atual = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    rascunho_versao = forms.IntegerField(min_value=0, required=False, widget=forms.HiddenInput)

    class Meta:
        model = RegraConquista
        fields = ['nome', 'descricao', 'icone', 'meta', 'ativa']
        labels = {'nome': 'Nome', 'descricao': 'Descrição', 'meta': 'Meta', 'ativa': 'Concessões ativas', 'icone': 'Ícone da conquista'}
        widgets = {'icone': forms.Select(attrs={'class': 'form-select'}), 'nome': forms.TextInput(attrs={'class': 'form-control'}),
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
        'regras': RegraConquista.objects.filter(plano__isnull=True),
        'planos': PlanoConquista.objects.select_related('regra_origem').order_by('-pk'),
        'recentes': Conquista.objects.select_related('usuario', 'equipe')[:20],
    })


@login_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def editar_conquista(request, regra_id):
    if not request.user.is_superuser:
        raise PermissionDenied
    regra = get_object_or_404(RegraConquista.objects.select_for_update(no_key=True), pk=regra_id)
    if regra.plano_id:
        return redirect('aparencia_plano',plano_id=regra.plano_id)
    from .construtor_conquistas import rascunho_de_regra, ConflitoRascunho
    rascunho = PlanoConquista.objects.filter(regra_origem=regra,estado='rascunho').first()
    antes = {c: getattr(regra,c) for c in ('nome','descricao','icone','meta','ativa')}
    form = RegraConquistaForm(request.POST if request.method=='POST' else None,instance=regra,
                            initial={'rascunho_versao':rascunho.versao if rascunho else 0})
    status=200
    if request.method=='POST' and form.is_valid():
        if regra.versao!=form.cleaned_data['versao_atual']:
            form.add_error(None,'Esta regra foi alterada. Reabra a página antes de salvar.');status=409
        else:
            campos={c:form.cleaned_data[c] for c in antes}
            criterio_mudou = campos['meta']!=antes['meta'] or (campos['ativa'] and not antes['ativa'])
            if criterio_mudou:
                try:
                    plano=rascunho_de_regra(regra,campos,form.cleaned_data.get('rascunho_versao') or 0)
                except ConflitoRascunho:
                    form.add_error(None,'O rascunho foi alterado. Reabra a página antes de salvar.');status=409
                else:
                    messages.info(request,'Proposta salva como rascunho. Nenhuma medalha foi concedida. Confira a prévia.')
                    return redirect('prever_plano',plano_id=plano.pk)
            else:
                atualizado=RegraConquista.objects.filter(pk=regra.pk,versao=form.cleaned_data['versao_atual']).update(**campos,versao=F('versao')+1)
                if not atualizado:
                    form.add_error(None,'Esta regra foi alterada. Reabra a página.');status=409
                else:
                    registrar('helpdesk.regraconquista',regra.pk,'alterado',{
                        c:{'alterado':True} if c in ('nome','descricao') else {'antes':antes[c],'depois':valor}
                        for c,valor in campos.items() if antes[c]!=valor})
                    messages.success(request,'Aparência ou pausa atualizada. Nenhuma medalha foi concedida ou reescrita.')
                    return redirect('gerenciar_conquistas')
    return render(request,'helpdesk/conquistas/formulario.html',{'form':form,'regra':regra,'icones':ICONES,'rascunho':rascunho},status=status)
