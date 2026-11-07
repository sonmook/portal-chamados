"""Consulta administrativa do histórico, sem operações de escrita."""
import json
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from .models import RegistroAuditoria

OBJETOS = {
    'auth.user': 'Usuário', 'helpdesk.chamado': 'Chamado', 'helpdesk.comentario': 'Comentário',
    'helpdesk.equipe': 'Equipe', 'helpdesk.regraencaminhamento': 'Regra de encaminhamento',
    'helpdesk.regraconquista': 'Regra de conquista', 'helpdesk.planoconquista': 'Plano de conquista',
    'helpdesk.conquista': 'Conquista', 'helpdesk.perfil': 'Perfil',
}
ACOES = {
    'criado': 'Criação', 'alterado': 'Alteração', 'excluido': 'Exclusão',
    'permissoes': 'Permissões alteradas', 'redistribuido': 'Redistribuição',
    'encaminhado': 'Encaminhamento', 'concedido': 'Conquista concedida', 'rascunho': 'Rascunho',
    'publicado': 'Publicação', 'retomado': 'Retomada', 'pausado': 'Pausa', 'aparencia': 'Aparência',
}
ORIGENS = {'portal': 'Portal', 'admin': 'Painel administrativo', 'sistema': 'Sistema'}


class FiltrosAuditoria(forms.Form):
    q = forms.CharField(label='Responsável ou ID', max_length=100, required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Usuário, ID do registro ou do item'}))
    objeto = forms.ChoiceField(label='Tipo de registro', required=False, choices=[('', 'Todos os tipos'), *OBJETOS.items()])
    acao = forms.ChoiceField(label='Ação', required=False, choices=[('', 'Todas as ações'), *ACOES.items()])
    origem = forms.ChoiceField(label='Origem', required=False, choices=[('', 'Todas as origens'), *ORIGENS.items()])
    inicio = forms.DateField(label='De', required=False, input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}))
    fim = forms.DateField(label='Até', required=False, input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-select form-select-sm' if isinstance(field, forms.ChoiceField) else 'form-control form-control-sm'

    def clean(self):
        dados = super().clean()
        if dados.get('inicio') and dados.get('fim') and dados['inicio'] > dados['fim']:
            raise forms.ValidationError('A data inicial deve ser anterior ou igual à data final.')
        return dados


def apresentar(registro):
    registro.tipo_legivel = OBJETOS.get(registro.objeto, registro.objeto)
    registro.acao_legivel = ACOES.get(registro.acao, registro.acao)
    registro.origem_legivel = ORIGENS.get(registro.origem, registro.origem)
    return registro


@login_required
@require_GET
@never_cache
def listar_auditoria(request):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied
    form = FiltrosAuditoria(request.GET)
    registros = RegistroAuditoria.objects.select_related('ator').order_by('-criado_em', '-pk')
    if form.is_valid():
        filtros = form.cleaned_data
        for campo in ('objeto', 'acao', 'origem'):
            if filtros[campo]:
                registros = registros.filter(**{campo: filtros[campo]})
        if filtros['inicio']:
            registros = registros.filter(criado_em__date__gte=filtros['inicio'])
        if filtros['fim']:
            registros = registros.filter(criado_em__date__lte=filtros['fim'])
        if filtros['q']:
            busca = Q(ator__username__icontains=filtros['q'])
            # IDs fora do limite do banco não viram parâmetros numéricos inválidos.
            if filtros['q'].isascii() and filtros['q'].isdigit() and len(filtros['q']) <= 19:
                numero = int(filtros['q'])
                if numero <= 9223372036854775807:
                    busca |= Q(pk=numero) | Q(objeto_id=numero)
            registros = registros.filter(busca)
    else:
        registros = registros.none()
    page = Paginator(registros, 20).get_page(request.GET.get('page'))
    page.object_list = [apresentar(r) for r in page.object_list]
    return render(request, 'helpdesk/auditoria/lista.html', {'form': form, 'page_obj': page})


CAMPOS = {
    'is_active': 'Conta ativa', 'is_staff': 'Técnico', 'is_superuser': 'Administrador',
    'username': 'Nome de usuário', 'email': 'E-mail', 'first_name': 'Nome', 'last_name': 'Sobrenome',
    'password': 'Senha', 'titulo': 'Título', 'descricao': 'Descrição', 'texto': 'Texto',
    'status': 'Status', 'categoria': 'Categoria', 'prioridade': 'Prioridade', 'anexo': 'Anexo',
    'tecnico_id': 'ID do responsável', 'solicitante_id': 'ID do solicitante', 'equipe_id': 'ID da equipe',
    'data_vencimento': 'Prazo SLA', 'data_fechamento': 'Data de resolução', 'motivo': 'Motivo',
    'ativa': 'Ativa', 'meta': 'Meta', 'nome': 'Nome', 'integrantes': 'Integrantes',
    'coordenadores': 'Coordenadores', 'versao': 'Versão',
}


def formatar(valor):
    if valor is None:
        return '—'
    if isinstance(valor, bool):
        return 'Sim' if valor else 'Não'
    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False, indent=2)
    return str(valor)


def detalhar(alteracoes):
    if not alteracoes:
        return []
    if not isinstance(alteracoes, dict):
        return [{'campo': 'Detalhes', 'antes': '—', 'depois': formatar(alteracoes)}]
    linhas = []
    for campo, valor in alteracoes.items():
        antes, depois = '—', formatar(valor)
        if isinstance(valor, dict):
            if 'antes' in valor or 'depois' in valor:
                antes, depois = formatar(valor.get('antes')), formatar(valor.get('depois'))
            elif valor == {'alterado': True}:
                antes, depois = 'Não armazenado', 'Alteração registrada'
        linhas.append({'campo': CAMPOS.get(campo, campo.replace('_', ' ').capitalize()),
                       'antes': antes, 'depois': depois})
    return linhas


@login_required
@require_GET
@never_cache
def detalhe_auditoria(request, registro_id):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied
    registro = apresentar(get_object_or_404(RegistroAuditoria.objects.select_related('ator'), pk=registro_id))
    return render(request, 'helpdesk/auditoria/detalhe.html', {
        'registro': registro,
        'alteracoes': detalhar(registro.alteracoes),
    })
