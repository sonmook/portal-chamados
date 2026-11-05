"""Rascunhos, previsão assinada e publicação explícita de conquistas."""
import hashlib
import json
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Min
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .audit import registrar
from .models import PlanoConquista, RegraConquista, Conquista, ResolucaoConquista
from .visual_conquistas import ICONES

NIVEIS = [('bronze', 'Bronze'), ('prata', 'Prata'), ('ouro', 'Ouro')]
CAMPOS = ('nome', 'descricao', 'icone', 'alvo', 'metrica', 'bronze', 'prata', 'ouro', 'contagem', 'ativa')
SALT = 'portal-publicacao-conquistas-v1'


class ConflitoRascunho(Exception):
    pass


class PlanoForm(forms.ModelForm):
    versao_atual = forms.IntegerField(min_value=0, widget=forms.HiddenInput, initial=0)
    origem_versao = forms.IntegerField(min_value=0, required=False, widget=forms.HiddenInput)

    class Meta:
        model = PlanoConquista
        fields = CAMPOS
        labels = {'nome': 'Nome da conquista', 'descricao': 'Descrição complementar', 'icone': 'Ícone',
                  'alvo': 'Quem recebe?', 'metrica': 'O que conta?', 'bronze': 'Meta Bronze', 'prata': 'Meta Prata',
                  'ouro': 'Meta Ouro', 'contagem': 'Quando começa a contagem?', 'ativa': 'Concessões ativas após publicar'}
        widgets = {'descricao': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome, campo in self.fields.items():
            if nome not in ('versao_atual', 'origem_versao'):
                campo.widget.attrs['class'] = 'form-check-input' if nome == 'ativa' else ('form-select' if nome in ('icone', 'alvo', 'metrica', 'contagem') else 'form-control')
        for nome in ('bronze','prata','ouro'):
            self.fields[nome].widget.attrs.update(min=1,max=100000,step=1)
        self.fields['versao_atual'].initial = self.instance.versao
        if self.instance.regra_origem_id:
            self.fields['origem_versao'].initial = self.instance.regra_origem.versao
            self.fields['bronze'].label = 'Meta proposta'
            for nome in ('alvo', 'metrica', 'contagem', 'prata', 'ouro'):
                self.fields[nome].disabled = True
            self.fields['prata'].widget = forms.HiddenInput()
            self.fields['ouro'].widget = forms.HiddenInput()
        else:
            self.fields['bronze'].initial = 5
            self.fields['prata'].initial = 20
            self.fields['ouro'].initial = 50
            if not self.instance.pk:
                self.initial.update(bronze=5, prata=20, ouro=50, alvo='pessoa', metrica='no_prazo')

    def clean(self):
        dados = super().clean()
        if not self.instance.regra_origem_id:
            bronze, prata, ouro = (dados.get(c) for c in ('bronze', 'prata', 'ouro'))
            if prata is None:
                self.add_error('prata', 'Informe a meta do nível Prata.')
            if ouro is None:
                self.add_error('ouro', 'Informe a meta do nível Ouro.')
            if bronze is not None and prata is not None and prata <= bronze:
                self.add_error('prata', 'Prata deve ter uma meta maior que Bronze.')
            if prata is not None and ouro is not None and ouro <= prata:
                self.add_error('ouro', 'Ouro deve ter uma meta maior que Prata.')
        return dados


class AparenciaPlanoForm(forms.ModelForm):
    versao_atual = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    class Meta:
        model = PlanoConquista
        fields = ['nome', 'descricao', 'icone']
        labels = {'nome': 'Nome', 'descricao': 'Descrição complementar', 'icone': 'Ícone'}
        widgets = {'nome': forms.TextInput(attrs={'class':'form-control'}),
                   'descricao': forms.Textarea(attrs={'class':'form-control','rows':3}),
                   'icone': forms.Select(attrs={'class':'form-select'})}


def inicio_plano(plano):
    if plano.regra_origem_id:
        return plano.regra_origem.inicio_em
    if plano.estado == 'publicada':
        primeira = plano.niveis.order_by('pk').first()
        return primeira.inicio_em if primeira else plano.publicada_em
    return RegraConquista.objects.aggregate(inicio=Min('inicio_em'))['inicio']


def previsao(plano):
    alvos = []
    inicio = inicio_plano(plano)
    usar_eventos = plano.ativa and (plano.estado == 'publicada' or plano.regra_origem_id or plano.contagem == 'historico')
    if usar_eventos and inicio is not None:
        campo = 'usuario_id' if plano.alvo == 'pessoa' else 'equipe_id'
        eventos = ResolucaoConquista.objects.filter(concluido_em__gte=inicio)
        if plano.metrica == 'no_prazo':
            eventos = eventos.filter(no_prazo=True)
        from django.db.models import Count
        alvos = list(eventos.values(campo).annotate(total=Count('pk')).order_by(campo).values_list(campo, 'total'))
    regras = {r.nivel: r for r in plano.niveis.all()} if plano.estado == 'publicada' and not plano.regra_origem_id else {}
    etapas = [('unico', 'Meta', plano.bronze)] if plano.regra_origem_id else [(c, n, getattr(plano, c)) for c, n in NIVEIS]
    resultado = []
    elegiveis = []
    for codigo, nome, meta in etapas:
        regra = plano.regra_origem if plano.regra_origem_id else regras.get(codigo)
        campo = 'usuario_id' if plano.alvo == 'pessoa' else 'equipe_id'
        premiados = set(Conquista.objects.filter(regra=regra).values_list(campo, flat=True)) if regra else set()
        novos = [(pk, total) for pk, total in alvos if total >= meta and pk not in premiados]
        resultado.append({'codigo': codigo, 'nome': nome, 'meta': meta, 'novas': len(novos), 'alvos': novos})
        elegiveis.append([codigo, meta, [pk for pk, _ in novos]])
    estado = [plano.pk, plano.versao, plano.base_versao,
              plano.regra_origem.versao if plano.regra_origem_id else None, elegiveis]
    fingerprint = hashlib.sha256(json.dumps(estado, sort_keys=True).encode()).hexdigest()
    return {'etapas': resultado, 'total': sum(e['novas'] for e in resultado), 'inicio': inicio,
            'fingerprint': fingerprint, 'token': signing.dumps({'pk':plano.pk,'versao':plano.versao,'hash':fingerprint}, salt=SALT)}


@transaction.atomic
def rascunho_de_regra(regra, dados, versao_rascunho):
    plano, _ = PlanoConquista.objects.get_or_create(regra_origem=regra, estado='rascunho', defaults={
        'nome': dados['nome'], 'descricao': dados['descricao'], 'icone': dados['icone'],
        'alvo': regra.alvo, 'metrica': regra.metrica, 'bronze': dados['meta'],
        'contagem': 'historico', 'ativa': dados['ativa'], 'base_versao': regra.versao,
    })
    plano = PlanoConquista.objects.select_for_update().get(pk=plano.pk)
    if plano.versao != versao_rascunho:
        raise ConflitoRascunho
    PlanoConquista.objects.filter(pk=plano.pk).update(
        nome=dados['nome'], descricao=dados['descricao'], icone=dados['icone'], bronze=dados['meta'],
        ativa=dados['ativa'], base_versao=regra.versao, versao=F('versao')+1)
    registrar('helpdesk.planoconquista', plano.pk, 'rascunho', {'regra_origem':regra.pk})
    return plano


def plano_bloqueado(plano_id):
    referencia = get_object_or_404(PlanoConquista.objects.only('regra_origem_id'), pk=plano_id)
    if referencia.regra_origem_id:
        RegraConquista.objects.select_for_update(no_key=True).get(pk=referencia.regra_origem_id)
    return get_object_or_404(PlanoConquista.objects.select_for_update(), pk=plano_id)


def conceder_previa(regra, etapa):
    """Concede somente aos destinatários da previsão validada, nunca a um novo conjunto."""
    from .conquistas import conceder
    return sum(conceder(regra, pk, total) is not None for pk, total in etapa['alvos'])


@login_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def editar_plano(request, plano_id=None):
    if not request.user.is_superuser:
        raise PermissionDenied
    if plano_id is None:
        return HttpResponseForbidden('O portal utiliza conquistas predefinidas. A criação de novas conquistas está desabilitada.')
    plano = plano_bloqueado(plano_id)
    if plano.estado != 'rascunho':
        return redirect('prever_plano', plano_id=plano.pk)
    form = PlanoForm(request.POST if request.method == 'POST' else None, instance=plano)
    status = 200
    if request.method == 'POST' and form.is_valid():
        origem = RegraConquista.objects.select_for_update(no_key=True).get(pk=plano.regra_origem_id) if plano.regra_origem_id else None
        if (plano.versao != form.cleaned_data['versao_atual'] or
                (origem and origem.versao != form.cleaned_data.get('origem_versao'))):
            form.add_error(None, 'O rascunho ou a regra mudou. Reabra a página antes de salvar.')
            status = 409
        else:
            criado = not plano.pk
            plano = form.save(commit=False)
            plano.versao += 1
            plano.base_versao = origem.versao if origem else None
            plano.save()
            registrar('helpdesk.planoconquista',plano.pk,'criado' if criado else 'rascunho',{'versao':plano.versao})
            messages.success(request, 'Rascunho salvo. Confira os critérios e o impacto antes de publicar.')
            return redirect('prever_plano',plano_id=plano.pk)
    return render(request,'helpdesk/conquistas/construtor.html',{'form':form,'plano':plano,'icones':ICONES},status=status)


def contexto_previa(plano, erro=None):
    # Retomar concessões calcula o impacto com a ativação proposta, sem gravar.
    if plano.estado == 'publicada' and not plano.ativa:
        plano.ativa = True
        impacto = previsao(plano)
        plano.ativa = False
    else:
        impacto = previsao(plano)
    return {'plano':plano,'impacto':impacto,'erro':erro,
            'pode_confirmar': plano.estado=='rascunho' or (plano.estado=='publicada' and not plano.ativa and not plano.regra_origem_id),
            'desatualizado': bool(plano.regra_origem_id and plano.estado=='rascunho' and plano.base_versao!=plano.regra_origem.versao)}


@login_required
@require_GET
def prever_plano(request, plano_id):
    if not request.user.is_superuser:
        raise PermissionDenied
    plano = get_object_or_404(PlanoConquista.objects.select_related('regra_origem'),pk=plano_id)
    return render(request,'helpdesk/conquistas/previa.html',contexto_previa(plano))


@login_required
@require_POST
@transaction.atomic
def publicar_plano(request, plano_id):
    if not request.user.is_superuser:
        raise PermissionDenied
    plano = plano_bloqueado(plano_id)
    retomar = plano.estado == 'publicada' and not plano.ativa and not plano.regra_origem_id
    if plano.estado == 'publicada' and not retomar:
        messages.info(request, 'Esta publicação já foi concluída; nenhuma medalha foi duplicada.')
        return redirect('prever_plano',plano_id=plano.pk)
    try:
        token = signing.loads(request.POST.get('confirmacao',''),salt=SALT,max_age=900)
    except signing.BadSignature:
        return render(request,'helpdesk/conquistas/previa.html',contexto_previa(plano,'A prévia expirou ou é inválida. Confira novamente e confirme.'),status=400)
    contexto = contexto_previa(plano)
    atual = contexto['impacto']
    if contexto['desatualizado'] or token != {'pk':plano.pk,'versao':plano.versao,'hash':atual['fingerprint']}:
        contexto['erro'] = 'Os critérios ou o impacto mudaram. Revise esta nova prévia antes de confirmar.'
        return render(request,'helpdesk/conquistas/previa.html',contexto,status=409)
    from django.utils import timezone
    novas = 0
    if retomar:
        regras = list(plano.niveis.select_for_update(no_key=True).order_by('pk'))
        for regra in regras:
            regra.ativa=True;regra.versao+=1;regra.save(update_fields=['ativa','versao'])
            etapa = next(e for e in atual['etapas'] if e['codigo']==regra.nivel)
            novas += conceder_previa(regra, etapa)
        plano.ativa=True
    elif plano.regra_origem_id:
        regra = RegraConquista.objects.select_for_update(no_key=True).get(pk=plano.regra_origem_id)
        if regra.versao != plano.base_versao:
            return render(request,'helpdesk/conquistas/previa.html',contexto_previa(plano,'A regra mudou. Revise o rascunho.'),status=409)
        antes = {'meta':regra.meta,'ativa':regra.ativa}
        regra.nome=plano.nome;regra.descricao=plano.descricao;regra.icone=plano.icone
        regra.meta=plano.bronze;regra.ativa=plano.ativa;regra.versao+=1
        regra.save(update_fields=['nome','descricao','icone','meta','ativa','versao'])
        registrar('helpdesk.regraconquista',regra.pk,'publicado',{'antes':antes,'meta':regra.meta,'ativa':regra.ativa,'plano':plano.pk})
        novas += conceder_previa(regra, atual['etapas'][0])
    else:
        inicio = atual['inicio'] if plano.contagem=='historico' else timezone.now()
        if inicio is None:
            inicio = timezone.now()
        for codigo, nome in NIVEIS:
            regra = RegraConquista.objects.create(codigo=f'trilha-{plano.pk}-{codigo}',plano=plano,nivel=codigo,
                nome=plano.nome,descricao=plano.descricao,icone=plano.icone,alvo=plano.alvo,metrica=plano.metrica,
                meta=getattr(plano,codigo),ativa=plano.ativa,inicio_em=inicio,versao=1)
            registrar('helpdesk.regraconquista',regra.pk,'criado',{'plano':plano.pk,'nivel':codigo,'meta':regra.meta})
            etapa = next(e for e in atual['etapas'] if e['codigo']==codigo)
            novas += conceder_previa(regra, etapa)
    plano.estado='publicada'
    if not retomar:
        plano.publicada_em=timezone.now()
    plano.versao+=1;plano.save(update_fields=['estado','publicada_em','versao','ativa'])
    registrar('helpdesk.planoconquista',plano.pk,'retomado' if retomar else 'publicado',{'novas_medalhas':novas,'versao':plano.versao})
    texto_medalhas = "Nenhuma medalha foi concedida agora." if novas == 0 else f"{novas} {'nova medalha foi concedida' if novas == 1 else 'novas medalhas foram concedidas'}."
    messages.success(request, f"{'Concessões retomadas' if retomar else 'Conquista publicada'}. {texto_medalhas}")
    return redirect('prever_plano',plano_id=plano.pk)


@login_required
@require_POST
@transaction.atomic
def pausar_plano(request, plano_id):
    if not request.user.is_superuser:
        raise PermissionDenied
    plano=get_object_or_404(PlanoConquista.objects.select_for_update(),pk=plano_id,estado='publicada',regra_origem__isnull=True)
    if not plano.ativa:
        return redirect('prever_plano',plano_id=plano.pk)
    if request.POST.get('versao')!=str(plano.versao):
        return render(request,'helpdesk/conquistas/previa.html',contexto_previa(plano,'A trilha mudou. Confira antes de pausar.'),status=409)
    plano.niveis.update(ativa=False,versao=F('versao')+1)
    plano.ativa=False;plano.versao+=1;plano.save(update_fields=['ativa','versao'])
    registrar('helpdesk.planoconquista',plano.pk,'pausado',{'versao':plano.versao})
    messages.success(request,'Trilha pausada. Medalhas e progresso foram preservados.')
    return redirect('prever_plano',plano_id=plano.pk)


@login_required
@require_http_methods(['GET','POST'])
@transaction.atomic
def aparencia_plano(request, plano_id):
    if not request.user.is_superuser:
        raise PermissionDenied
    plano=get_object_or_404(PlanoConquista.objects.select_for_update(),pk=plano_id,estado='publicada',regra_origem__isnull=True)
    form=AparenciaPlanoForm(request.POST if request.method=='POST' else None,instance=plano,initial={'versao_atual':plano.versao})
    status=200
    if request.method=='POST' and form.is_valid():
        if plano.versao!=form.cleaned_data['versao_atual']:
            form.add_error(None,'A trilha mudou. Reabra a página.');status=409
        else:
            plano=form.save(commit=False);plano.versao+=1;plano.save(update_fields=['nome','descricao','icone','versao'])
            plano.niveis.update(nome=plano.nome,descricao=plano.descricao,icone=plano.icone,versao=F('versao')+1)
            registrar('helpdesk.planoconquista',plano.pk,'aparencia',{'versao':plano.versao})
            messages.success(request,'Aparência atualizada. Nenhuma medalha foi concedida ou reescrita.')
            return redirect('prever_plano',plano_id=plano.pk)
    return render(request,'helpdesk/conquistas/aparencia.html',{'form':form,'plano':plano},status=status)
