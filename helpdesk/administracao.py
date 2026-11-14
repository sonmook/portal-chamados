"""Entrada única para as ferramentas administrativas existentes."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views.decorators.http import require_GET

SECOES = {
    'central_administracao': 'Administração',
    'indicadores_administracao': 'Indicadores',
    'listar_auditoria': 'Auditoria',
    'detalhe_auditoria': 'Auditoria',
    **dict.fromkeys(('gerenciar_respostas_prontas', 'criar_resposta_pronta', 'editar_resposta_pronta'), 'Respostas prontas'),
    **dict.fromkeys(('gerenciar_usuarios', 'criar_usuario', 'editar_usuario'), 'Usuários'),
    **dict.fromkeys(('gerenciar_equipes', 'criar_equipe', 'editar_equipe'), 'Equipes'),
    **dict.fromkeys(('listar_regras_encaminhamento', 'criar_regra_encaminhamento', 'editar_regra_encaminhamento'), 'Encaminhamento'),
    **dict.fromkeys(('gerenciar_conquistas', 'editar_conquista', 'criar_plano', 'editar_plano', 'prever_plano', 'aparencia_plano'), 'Conquistas'),
}

FERRAMENTAS = [
    {'nome': 'Indicadores', 'icone': 'bar-chart', 'url': 'indicadores_administracao',
     'descricao': 'Consulte o resumo geral, desempenho por equipe e resoluções por período.'},
    {'nome': 'Usuários', 'icone': 'people', 'url': 'gerenciar_usuarios',
     'descricao': 'Gerencie contas, permissões e acesso ao portal.'},
    {'nome': 'Equipes', 'icone': 'diagram-3', 'url': 'gerenciar_equipes',
     'descricao': 'Organize integrantes, coordenadores e responsabilidades.'},
    {'nome': 'Encaminhamento', 'icone': 'signpost-split', 'url': 'listar_regras_encaminhamento',
     'descricao': 'Defina a equipe de destino para cada categoria de chamado.'},
    {'nome': 'Conquistas', 'icone': 'trophy', 'url': 'gerenciar_conquistas',
     'descricao': 'Revise as configurações das conquistas existentes.'},
    {'nome': 'Respostas prontas', 'icone': 'chat-left-quote', 'url': 'gerenciar_respostas_prontas',
     'descricao': 'Crie e organize modelos de texto para o atendimento.'},
    {'nome': 'Auditoria', 'icone': 'clock-history', 'url': 'listar_auditoria',
     'descricao': 'Consulte o histórico de alterações e seus responsáveis.'},
]


@login_required
@require_GET
def central_administracao(request):
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied
    return render(request, 'helpdesk/administracao.html', {'ferramentas': FERRAMENTAS})
