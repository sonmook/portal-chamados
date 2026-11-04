from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.views.decorators.http import require_POST, require_http_methods
from django.db.models import Q, F, Count, Avg, DurationField, ExpressionWrapper
from django.db.models.functions import Coalesce
from .user_security import bloquear_administradores, validar_pendencias
from .audit import registrar
from .encaminhamento import criar_chamado_encaminhado
from .acesso import chamados_acessiveis, equipes_acessiveis, integrante_ativo, pode_distribuir, filtrar_equipe
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib.auth.models import User 
from django.utils import timezone
from django.contrib import messages
from datetime import timedelta

from .models import Chamado, Comentario, Equipe, IntegranteEquipe
from .forms import ChamadoForm, ComentarioForm, NovoUsuarioForm, EditarUsuarioForm, ResolucaoForm, RedistribuirChamadoForm


@login_required
def dashboard(request):
    """
    Renderiza o painel de indicadores (Dashboard).
    Processa os filtros de data e calcula as métricas (Total, SLA, TMR, Ranking)
    de acordo com o nível de permissão do usuário.
    """
    periodo = request.GET.get('periodo', 'sempre')
    hoje = timezone.now().date()
    
    base_chamados = chamados_acessiveis(request.user)
    equipe_filter = request.GET.get('equipe', '')
    base_chamados = filtrar_equipe(base_chamados, equipe_filter)

    # Aplicação do Filtro de Data
    if periodo == 'hoje':
        base_chamados = base_chamados.filter(data_criacao__date=hoje)
    elif periodo == '7dias':
        base_chamados = base_chamados.filter(data_criacao__date__gte=hoje - timedelta(days=7))
    elif periodo == 'mes':
        base_chamados = base_chamados.filter(data_criacao__month=hoje.month, data_criacao__year=hoje.year)

    finalizados = Q(status__in=FINALIZADOS)
    categorias = ('Software', 'Hardware', 'Rede', 'Acessos', 'Outros')
    agregacoes = {
        'total': Count('pk'),
        'abertos': Count('pk', filter=Q(status='Aberto')),
        'resolvidos': Count('pk', filter=finalizados),
        'vencidos': Count('pk', filter=Q(data_vencimento__lt=timezone.now()) & ~finalizados),
        'sla_sem_dados': Count('pk', filter=finalizados & (
            Q(data_fechamento__isnull=True) | Q(data_vencimento__isnull=True)
        )),
        **{f'categoria_{i}': Count('pk', filter=Q(categoria=categoria))
           for i, categoria in enumerate(categorias)},
    }
    if request.user.is_staff:
        agregacoes.update(
            dentro_sla=Count('pk', filter=finalizados & Q(data_fechamento__lte=F('data_vencimento'))),
            fora_sla=Count('pk', filter=finalizados & Q(data_fechamento__gt=F('data_vencimento'))),
            tmr=Avg(ExpressionWrapper(
                Coalesce('data_fechamento', 'data_atualizacao') - F('data_criacao'),
                output_field=DurationField(),
            ), filter=finalizados),
        )
    metricas = base_chamados.aggregate(**agregacoes)
    produtividade_equipe = []
    minha_produtividade = tmr_horas = 0
    if request.user.is_staff:
        # Um agrupamento para toda a equipe, incluindo membros sem resoluções.
        membros = User.objects.filter(is_staff=True)
        if not request.user.is_superuser:
            membros = membros.filter(Q(pk__in=IntegranteEquipe.objects.filter(
                equipe_id__in=equipes_acessiveis(request.user).values('pk')
            ).values('usuario_id')) | Q(pk__in=base_chamados.values('fechado_por_id')) | Q(pk=request.user.pk))
        membros = membros.annotate(
            total_fechados=Count('chamados_fechados', filter=Q(
                chamados_fechados__in=base_chamados.filter(status__in=FINALIZADOS)
            ))
        ).order_by('-total_fechados', 'pk')
        for membro in membros:
            produtividade_equipe.append({
                'username': membro.get_full_name() or membro.username,
                'count': membro.total_fechados,
            })
            if membro.pk == request.user.pk:
                minha_produtividade = membro.total_fechados
        if metricas['tmr'] is not None:
            tmr_horas = round(metricas['tmr'].total_seconds() / 3600, 1)

    context = {
        'periodo_atual': periodo,
        'equipes_filtro': equipes_acessiveis(request.user), 'equipe_filter': equipe_filter,
        'tmr_horas': tmr_horas,
        **{campo: metricas[campo] for campo in ('total', 'abertos', 'resolvidos', 'vencidos', 'sla_sem_dados')},
        'ultimos_chamados': base_chamados.select_related('solicitante').order_by('-data_criacao')[:5],
        'dados_grafico': [metricas[f'categoria_{i}'] for i in range(len(categorias))],
        'dados_sla': [metricas.get('dentro_sla', 0), metricas.get('fora_sla', 0)],
        'produtividade_equipe': produtividade_equipe,
        'minha_produtividade': minha_produtividade,
    }

    return render(request, 'helpdesk/dashboard.html', context)


@login_required
def lista_chamados(request):
    """
    Exibe a lista de chamados com suporte a busca, filtros e paginação.
    """
    chamados_list = chamados_acessiveis(request.user).order_by('-id')

    # Captura parâmetros da URL
    query = request.GET.get('q')
    status_filter = request.GET.get('status')
    categoria_filter = request.GET.get('categoria')
    equipe_filter = request.GET.get('equipe', '')
    chamados_list = filtrar_equipe(chamados_list, equipe_filter)
    ordenacao = request.GET.get('ordenacao', 'novos')
    if ordenacao not in ('novos', 'interacao_recente', 'sem_interacao'):
        ordenacao = 'novos'

    # Filtro de Busca (Q objects permitem o uso do operador OR | )
    if query:
        chamados_list = chamados_list.filter(
            Q(titulo__icontains=query) | Q(descricao__icontains=query)
        )

    if status_filter:
        chamados_list = chamados_list.filter(status=status_filter)

    if categoria_filter:
        chamados_list = chamados_list.filter(categoria=categoria_filter)

    if ordenacao == 'sem_interacao':
        chamados_list = chamados_list.exclude(status__in=FINALIZADOS).order_by(
            Coalesce('ultima_interacao_em', 'data_criacao').asc(), 'pk'
        )
    elif ordenacao == 'interacao_recente':
        chamados_list = chamados_list.order_by(Coalesce('ultima_interacao_em', 'data_criacao').desc(), '-pk')
    chamados_list = chamados_list.select_related('solicitante', 'solicitante__perfil', 'tecnico', 'tecnico__perfil', 'equipe')

    # Paginação (10 itens por página)
    paginator = Paginator(chamados_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'query': query,
        'status_filter': status_filter,
        'categoria_filter': categoria_filter,
        'ordenacao': ordenacao,
        'equipes_filtro': equipes_acessiveis(request.user), 'equipe_filter': equipe_filter,
    }
    return render(request, 'helpdesk/lista_chamados.html', context)


@login_required
@transaction.atomic
def novo_chamado(request):
    """
    Processa a criação de um novo ticket de suporte.
    """
    if request.method == 'POST':
        form = ChamadoForm(request.POST, request.FILES)
        if form.is_valid():
            chamado = form.save(commit=False)
            chamado.solicitante = request.user
            criar_chamado_encaminhado(chamado)
            return redirect('lista_chamados')
    else:
        form = ChamadoForm()
    return render(request, 'helpdesk/novo_chamado.html', {'form': form})


FINALIZADOS = ('Resolvido', 'Fechado')


def _chamado_visivel(user, id, *, bloquear=False):
    chamados = chamados_acessiveis(user).select_related('equipe')
    chamado = get_object_or_404(chamados, pk=id)
    if bloquear:
        get_object_or_404(Equipe.objects.select_for_update(), pk=chamado.equipe_id)
        chamado = get_object_or_404(chamados.select_for_update(), pk=id, equipe_id=chamado.equipe_id)
    return chamado


def _exigir_responsavel(user, chamado):
    if chamado.tecnico_id != user.pk or not integrante_ativo(user, chamado.equipe_id):
        raise PermissionDenied


@login_required
@transaction.atomic
def detalhes_chamado(request, id):
    chamado = _chamado_visivel(request.user, id, bloquear=request.method == 'POST')
    ativo = chamado.status not in FINALIZADOS and chamado.equipe.ativa
    pode_responder = ativo and (
        chamado.solicitante_id == request.user.pk
        or (chamado.tecnico_id == request.user.pk and integrante_ativo(request.user, chamado.equipe_id))
    )
    if request.method == 'POST':
        if not pode_responder:
            raise PermissionDenied
        form = ComentarioForm(request.POST, request.FILES)
        if form.is_valid():
            comentario = form.save(commit=False)
            comentario.chamado = chamado
            comentario.autor = request.user
            comentario.save()
            return redirect('detalhes_chamado', id=chamado.id)
    else:
        form = ComentarioForm()
    return render(request, 'helpdesk/detalhes_chamado.html', {
        'chamado': chamado,
        'comentarios': chamado.comentarios.select_related('autor', 'autor__perfil').all().order_by('data_criacao'),
        'form': form,
        'ativo': ativo,
        'pode_responder': pode_responder,
        'pode_fechar': ativo and chamado.tecnico_id == request.user.pk and integrante_ativo(request.user, chamado.equipe_id),
        'pode_assumir': ativo and chamado.tecnico_id is None and integrante_ativo(request.user, chamado.equipe_id),
        'pode_distribuir': pode_distribuir(request.user, chamado),
    })


@login_required
@require_POST
@transaction.atomic
def atualizar_status(request, id):
    chamado = _chamado_visivel(request.user, id, bloquear=True)
    _exigir_responsavel(request.user, chamado)
    if chamado.status in FINALIZADOS:
        raise PermissionDenied
    # Encerramento deve passar por fechar_chamado para registrar solução e auditoria.
    novo_status = request.POST.get('status')
    if novo_status not in ('Aberto', 'Em Andamento'):
        return HttpResponseBadRequest('Status inválido. Use o encerramento com solução.')
    chamado.status = novo_status
    chamado.save()
    return redirect('detalhes_chamado', id=chamado.id)


@login_required
@require_POST
@transaction.atomic
def fechar_chamado(request, id):
    chamado = _chamado_visivel(request.user, id, bloquear=True)
    _exigir_responsavel(request.user, chamado)
    if chamado.status in FINALIZADOS:
        raise PermissionDenied
    form = ResolucaoForm(request.POST, request.FILES)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_text(), content_type='text/plain; charset=utf-8')
    texto_resolucao = form.cleaned_data['resolucao']
    Comentario.objects.create(
        chamado=chamado,
        autor=request.user,
        texto=f"✅ TICKET ENCERRADO POR TI - SOLUÇÃO:\n\n{texto_resolucao}",
        anexo=form.cleaned_data['anexo_resolucao'],
    )
    chamado.status = 'Resolvido'
    chamado.fechado_por = request.user
    chamado.data_fechamento = timezone.now()
    # O comentário de solução já atualizou a interação no banco.
    chamado.save(update_fields=['status', 'fechado_por', 'data_fechamento', 'data_atualizacao', 'data_vencimento'])
    return redirect('detalhes_chamado', id=chamado.id)


@login_required
@require_POST
@transaction.atomic
def assumir_chamado(request, chamado_id):
    chamado = _chamado_visivel(request.user, chamado_id, bloquear=True)
    if not integrante_ativo(request.user, chamado.equipe_id):
        raise PermissionDenied
    get_object_or_404(User.objects.select_for_update(), pk=request.user.pk, is_active=True, is_staff=True)
    # A atualização condicional impede sobrescrever uma atribuição concorrente.
    atualizado = Chamado.objects.filter(pk=chamado.pk, tecnico__isnull=True).exclude(
        status__in=FINALIZADOS
    ).update(tecnico=request.user, data_atualizacao=timezone.now(), versao_atribuicao=F('versao_atribuicao') + 1)
    if atualizado:
        registrar('helpdesk.chamado', chamado.pk, 'alterado', {'tecnico_id': {'antes': None, 'depois': request.user.pk}})
        messages.success(request, "Você assumiu o chamado.")
    return redirect('detalhes_chamado', id=chamado.id)


@login_required
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def redistribuir_chamado(request, id):
    chamado = _chamado_visivel(request.user, id)
    if not pode_distribuir(request.user, chamado):
        raise PermissionDenied
    destino_id = request.POST.get('equipe') if request.method == 'POST' else request.GET.get('destino', chamado.equipe_id)
    try:
        destino_id = int(destino_id)
    except (TypeError, ValueError):
        destino_id = chamado.equipe_id
    form = RedistribuirChamadoForm(request.POST if request.method == 'POST' else None,
                                  chamado=chamado, initial={'equipe': destino_id})
    status = 200
    if request.method == 'POST' and form.is_valid():
        destino = form.cleaned_data['equipe']
        # Equipes antes dos chamados: a edição de integrantes usa os mesmos bloqueios.
        list(Equipe.objects.select_for_update().filter(pk__in=sorted({chamado.equipe_id, destino.pk})).order_by('pk'))
        chamado = _chamado_visivel(request.user, id, bloquear=True)
        if not pode_distribuir(request.user, chamado):
            raise PermissionDenied
        if not Equipe.objects.filter(pk=destino.pk, ativa=True).exists():
            form.add_error('equipe', 'A equipe de destino foi desativada. Escolha outra.')
        else:
            tecnico = form.cleaned_data['tecnico']
            if tecnico:
                tecnico = get_object_or_404(User.objects.select_for_update(), pk=tecnico.pk, is_active=True, is_staff=True)
                if not integrante_ativo(tecnico, destino.pk):
                    raise PermissionDenied
            anterior = form.cleaned_data['responsavel_anterior']
            atualizado = Chamado.objects.filter(
                pk=id, tecnico_id=anterior, equipe_id=form.cleaned_data['equipe_anterior'],
                versao_atribuicao=form.cleaned_data['versao_atribuicao'],
            ).exclude(status__in=FINALIZADOS).update(
                equipe=destino, tecnico=tecnico, data_atualizacao=timezone.now(),
                versao_atribuicao=F('versao_atribuicao') + 1,
            )
            if atualizado:
                alteracoes = {'tecnico_id': {'antes': anterior, 'depois': tecnico.pk if tecnico else None},
                              'motivo': form.cleaned_data['motivo']}
                if chamado.equipe_id != destino.pk:
                    alteracoes['equipe_id'] = {'antes': chamado.equipe_id, 'depois': destino.pk}
                registrar('helpdesk.chamado', id, 'redistribuido', alteracoes)
                messages.success(request, 'Chamado redistribuído e registrado na auditoria.')
                # O coordenador pode deixar de ter acesso após encaminhar a outra equipe.
                return redirect('lista_chamados')
            form.add_error(None, 'O chamado foi alterado por outra pessoa. Reabra a página antes de transferir.')
            status = 409
    return render(request, 'helpdesk/redistribuir_chamado.html', {
        'form': form, 'chamado': chamado, 'equipes_destino': Equipe.objects.filter(ativa=True), 'destino_id': destino_id,
    }, status=status)


@login_required
@require_POST
@transaction.atomic
def devolver_chamado(request, chamado_id):
    chamado = _chamado_visivel(request.user, chamado_id, bloquear=True)
    _exigir_responsavel(request.user, chamado)
    if chamado.status in FINALIZADOS:
        raise PermissionDenied
    chamado.tecnico = None
    chamado.versao_atribuicao += 1
    chamado.save()
    messages.warning(request, "Chamado devolvido para a fila.")
    return redirect('detalhes_chamado', id=chamado.id)


# ==========================================
# FUNÇÕES ADMINISTRATIVAS (GERENCIAMENTO DE USUÁRIOS)
# ==========================================

@login_required
def gerenciar_usuarios(request):
    """
    Lista todos os usuários do sistema com barra de pesquisa. 
    Acesso restrito a superusuários.
    """
    if not request.user.is_superuser:
        return redirect('lista_chamados')
        
    usuarios = User.objects.all().order_by('-is_active', 'first_name')
    query = request.GET.get('q')
    
    if query:
        usuarios = usuarios.filter(
            Q(username__icontains=query) | 
            Q(first_name__icontains=query) | 
            Q(last_name__icontains=query) | 
            Q(email__icontains=query)
        )
        
    return render(request, 'helpdesk/gerenciar_usuarios.html', {
        'usuarios': usuarios,
        'query': query
    })


@login_required
@transaction.atomic
def criar_usuario(request):
    """
    Permite a criação manual de contas através da interface.
    """
    if not request.user.is_superuser:
        return redirect('lista_chamados')

    if request.method == 'POST':
        form = NovoUsuarioForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('lista_chamados')
    else:
        form = NovoUsuarioForm()
        
    return render(request, 'helpdesk/criar_usuario.html', {'form': form})


@login_required
@transaction.atomic
def editar_usuario(request, user_id):
    """
    Permite a edição dos dados e nível de acesso de um usuário específico.
    """
    if not request.user.is_superuser:
        return redirect('lista_chamados')
        
    bloquear_administradores()
    usuario = get_object_or_404(User.objects.select_for_update(), id=user_id)
    
    if request.method == 'POST':
        form = EditarUsuarioForm(request.POST, instance=usuario)
        if form.is_valid():
            form.save()
            messages.success(request, f'Usuário {usuario.username} atualizado com sucesso!')
            return redirect('gerenciar_usuarios')
    else:
        form = EditarUsuarioForm(instance=usuario)
        
    pendentes = Chamado.objects.filter(tecnico_id=user_id).exclude(status__in=FINALIZADOS).order_by('pk')
    return render(request, 'helpdesk/editar_usuario.html', {
        'form': form, 'usuario': usuario, 'pendentes': pendentes[:20], 'total_pendentes': pendentes.count(),
    })


@login_required
@require_POST
@transaction.atomic
def alternar_status_usuario(request, user_id):
    """
    Ativa ou desativa o acesso de um usuário ao sistema.
    Impede que o administrador desative a própria conta por acidente.
    """
    if not request.user.is_superuser:
        return redirect('lista_chamados')
        
    bloquear_administradores()
    usuario = get_object_or_404(User.objects.select_for_update(), id=user_id)
    
    if usuario == request.user:
        messages.error(request, "Você não pode desativar sua própria conta.")
        return redirect('gerenciar_usuarios')
        
    try:
        validar_pendencias(usuario.pk, not usuario.is_active, usuario.is_staff)
    except ValidationError as erro:
        messages.error(request, erro.messages[0])
        return redirect('editar_usuario', user_id=user_id)
    usuario.is_active = not usuario.is_active
    usuario.save()
    
    status = "ativado" if usuario.is_active else "inativado"
    messages.success(request, f'Usuário {usuario.username} {status} com sucesso!')
    return redirect('gerenciar_usuarios')

@login_required
def baixar_anexo(request, id, comentario_id=None):
    chamado = _chamado_visivel(request.user, id)
    if comentario_id is None:
        arquivo = chamado.anexo
    else:
        arquivo = get_object_or_404(chamado.comentarios, pk=comentario_id).anexo
    if not arquivo:
        raise Http404
    try:
        aberto = arquivo.open('rb')
    except FileNotFoundError:
        raise Http404
    resposta = FileResponse(aberto, as_attachment=True, content_type='application/octet-stream')
    resposta['X-Content-Type-Options'] = 'nosniff'
    resposta['Content-Security-Policy'] = "sandbox; default-src 'none'"
    resposta['Cache-Control'] = 'private, no-store'
    return resposta
