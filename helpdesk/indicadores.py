"""Indicadores administrativos: uma resolução por chamado, sem joins de integrantes."""
from datetime import datetime, time, timedelta

from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from .acesso import FINALIZADOS
from .models import Chamado, Equipe


class FiltrosIndicadores(forms.Form):
    periodo = forms.ChoiceField(choices=[('mes', 'Este mês'), ('hoje', 'Hoje'),
        ('7dias', 'Últimos 7 dias'), ('sempre', 'Todo o histórico'),
        ('personalizado', 'Intervalo personalizado')])
    inicio = forms.DateField(required=False, label='Data inicial', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    fim = forms.DateField(required=False, label='Data final', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    equipe = forms.ModelChoiceField(queryset=Equipe.objects.all(), required=False, empty_label='Todas as equipes')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs['class'] = 'form-select' if isinstance(campo.widget, forms.Select) else 'form-control'

    def clean(self):
        dados = super().clean()
        if dados.get('periodo') == 'personalizado':
            inicio, fim = dados.get('inicio'), dados.get('fim')
            if not inicio or not fim:
                raise forms.ValidationError('Informe as datas inicial e final.')
            if inicio > fim:
                raise forms.ValidationError('A data inicial deve ser anterior ou igual à final.')
            if fim.year == 9999:
                raise forms.ValidationError('Escolha uma data final anterior ao ano 9999.')
        return dados


def metricas(chamados):
    finalizados = Q(status__in=FINALIZADOS)
    duracao_valida = finalizados & Q(data_fechamento__gte=F('data_criacao'))
    return chamados.aggregate(
        total=Count('pk'), ativos=Count('pk', filter=~finalizados),
        resolvidos=Count('pk', filter=finalizados),
        dentro_sla=Count('pk', filter=finalizados & Q(data_fechamento__lte=F('data_vencimento'))),
        fora_sla=Count('pk', filter=finalizados & Q(data_fechamento__gt=F('data_vencimento'))),
        sem_sla=Count('pk', filter=finalizados & (Q(data_fechamento__isnull=True) | Q(data_vencimento__isnull=True))),
        sem_data=Count('pk', filter=finalizados & Q(data_fechamento__isnull=True)),
        tmr=Avg(ExpressionWrapper(F('data_fechamento') - F('data_criacao'), output_field=DurationField()), filter=duracao_valida),
    )


def apresentar(dados):
    dados['tmr_horas'] = round(dados['tmr'].total_seconds() / 3600, 1) if dados['tmr'] is not None else None
    conhecidos = dados['dentro_sla'] + dados['fora_sla']
    dados['sla_percentual'] = round(100 * dados['dentro_sla'] / conhecidos, 1) if conhecidos else None
    return dados


@login_required
@require_GET
def painel(request):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied
    parametros = request.GET.copy()
    parametros.setdefault('periodo', 'mes')
    form = FiltrosIndicadores(parametros)
    contexto = {'form': form}
    if form.is_valid():
        dados = form.cleaned_data
        hoje = timezone.localdate()
        periodo = dados['periodo']
        inicio = fim = None
        if periodo == 'hoje':
            inicio = fim = hoje
        elif periodo == '7dias':
            inicio, fim = hoje - timedelta(days=6), hoje
        elif periodo == 'mes':
            inicio, fim = hoje.replace(day=1), hoje
        elif periodo == 'personalizado':
            inicio, fim = dados['inicio'], dados['fim']
        base = Chamado.objects.all()
        if dados['equipe']:
            base = base.filter(equipe=dados['equipe'])
        # Aberturas usam criação; resoluções usam fechamento, mesmo se abertas antes.
        abertos = base
        resolvidos = base.filter(status__in=FINALIZADOS)
        if inicio:
            limite_inicial = timezone.make_aware(datetime.combine(inicio, time.min))
            limite_final = timezone.make_aware(datetime.combine(fim + timedelta(days=1), time.min))
            abertos = abertos.filter(data_criacao__gte=limite_inicial, data_criacao__lt=limite_final)
            resolvidos = resolvidos.filter(data_fechamento__gte=limite_inicial, data_fechamento__lt=limite_final)
        resumo = apresentar(metricas(resolvidos))
        resumo['criados'] = abertos.count()
        resumo['ativos'] = base.exclude(status__in=FINALIZADOS).count()
        # Agrupamento pelo FK do chamado: vínculos e comentários não multiplicam resoluções.
        grupos = resolvidos.values('equipe_id').annotate(total=Count('pk'),
            dentro_sla=Count('pk', filter=Q(data_fechamento__lte=F('data_vencimento'))),
            fora_sla=Count('pk', filter=Q(data_fechamento__gt=F('data_vencimento'))),
            tmr=Avg(ExpressionWrapper(F('data_fechamento') - F('data_criacao'), output_field=DurationField()),
                    filter=Q(data_fechamento__gte=F('data_criacao'))))
        por_equipe = {g['equipe_id']: apresentar(g) for g in grupos}
        equipes = Equipe.objects.all()
        if dados['equipe']:
            equipes = equipes.filter(pk=dados['equipe'].pk)
        linhas = [{'equipe': equipe, **por_equipe.get(equipe.pk, {'total': 0, 'sla_percentual': None, 'tmr_horas': None})} for equipe in equipes]
        pagina = Paginator(resolvidos.select_related('equipe', 'fechado_por').order_by('-data_fechamento', '-pk'), 25).get_page(request.GET.get('page'))
        parametros.pop('page', None)
        contexto.update(resumo=resumo, equipes=linhas, pagina=pagina, filtros_url=parametros.urlencode())
    return render(request, 'helpdesk/indicadores.html', contexto)
