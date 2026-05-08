from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib.auth.models import User 
from django.utils import timezone
from django.contrib import messages
from datetime import timedelta

from .models import Chamado, Comentario
from .forms import ChamadoForm, ComentarioForm, NovoUsuarioForm, EditarUsuarioForm


@login_required
def dashboard(request):
    """
    Renderiza o painel de indicadores (Dashboard).
    Processa os filtros de data e calcula as métricas (Total, SLA, TMR, Ranking)
    de acordo com o nível de permissão do usuário.
    """
    periodo = request.GET.get('periodo', 'sempre')
    hoje = timezone.now().date()
    
    # Define a base de chamados de acordo com o cargo
    if request.user.is_staff:
        base_chamados = Chamado.objects.all()
    else:
        base_chamados = Chamado.objects.filter(solicitante=request.user)
        
    # Aplicação do Filtro de Data
    if periodo == 'hoje':
        base_chamados = base_chamados.filter(data_criacao__date=hoje)
    elif periodo == '7dias':
        base_chamados = base_chamados.filter(data_criacao__date__gte=hoje - timedelta(days=7))
    elif periodo == 'mes':
        base_chamados = base_chamados.filter(data_criacao__month=hoje.month, data_criacao__year=hoje.year)

    # Inicialização de variáveis locais
    dentro_sla = fora_sla = tmr_horas = minha_produtividade = 0
    produtividade_equipe = []

    # Cálculo de Métricas (Apenas para equipe de TI)
    if request.user.is_staff:
        resolvidos = base_chamados.filter(status='Resolvido')
        
        # Análise de SLA
        dentro_sla = resolvidos.filter(data_vencimento__gt=timezone.now()).count()
        fora_sla = resolvidos.count() - dentro_sla
        
        # Ranking da Equipe
        membros_ti = User.objects.filter(is_staff=True)
        for membro in membros_ti:
            qtd_fechados = base_chamados.filter(status='Resolvido', fechado_por=membro).count()
            produtividade_equipe.append({
                'username': membro.get_full_name() or membro.username,
                'count': qtd_fechados
            })
        produtividade_equipe = sorted(produtividade_equipe, key=lambda x: x['count'], reverse=True)
        minha_produtividade = base_chamados.filter(status='Resolvido', fechado_por=request.user).count()
        
        # Cálculo do Tempo Médio de Resolução (TMR) em Horas
        tempos_resolucao = []
        for chamado in resolvidos:
            data_fim = getattr(chamado, 'data_fechamento', chamado.data_atualizacao)
            if data_fim and chamado.data_criacao:
                tempo_segundos = (data_fim - chamado.data_criacao).total_seconds()
                tempos_resolucao.append(tempo_segundos)
                
        if tempos_resolucao:
            media_segundos = sum(tempos_resolucao) / len(tempos_resolucao)
            tmr_horas = round(media_segundos / 3600, 1)

    # Preparação de dados para os Gráficos de Categoria
    ultimos_chamados = base_chamados.order_by('-data_criacao')[:5]
    dados_categorias = [
        base_chamados.filter(categoria='Software').count(),
        base_chamados.filter(categoria='Hardware').count(),
        base_chamados.filter(categoria='Rede').count(),
        base_chamados.filter(categoria='Acessos').count(),
        base_chamados.filter(categoria='Outros').count(),
    ]

    context = {
        'periodo_atual': periodo,
        'tmr_horas': tmr_horas,
        'total': base_chamados.count(),
        'abertos': base_chamados.filter(status='Aberto').count(),
        'resolvidos': base_chamados.filter(status='Resolvido').count(),
        'vencidos': base_chamados.filter(data_vencimento__lt=timezone.now()).exclude(status='Resolvido').count(),
        'ultimos_chamados': ultimos_chamados,
        'dados_grafico': dados_categorias,
        'dados_sla': [dentro_sla, fora_sla],
        'produtividade_equipe': produtividade_equipe,
        'minha_produtividade': minha_produtividade,
    }
    
    return render(request, 'helpdesk/dashboard.html', context)


@login_required
def lista_chamados(request):
    """
    Exibe a lista de chamados com suporte a busca, filtros e paginação.
    """
    if request.user.is_staff:
        chamados_list = Chamado.objects.all().order_by('-id')
    else:
        chamados_list = Chamado.objects.filter(solicitante=request.user).order_by('-id')

    # Captura parâmetros da URL
    query = request.GET.get('q')
    status_filter = request.GET.get('status')
    categoria_filter = request.GET.get('categoria') 

    # Filtro de Busca (Q objects permitem o uso do operador OR | )
    if query:
        chamados_list = chamados_list.filter(
            Q(titulo__icontains=query) | Q(descricao__icontains=query)
        )

    if status_filter:
        chamados_list = chamados_list.filter(status=status_filter)

    if categoria_filter:
        chamados_list = chamados_list.filter(categoria=categoria_filter)

    # Paginação (10 itens por página)
    paginator = Paginator(chamados_list, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'query': query,
        'status_filter': status_filter,
        'categoria_filter': categoria_filter,
    }
    return render(request, 'helpdesk/lista_chamados.html', context)


@login_required
def novo_chamado(request):
    """
    Processa a criação de um novo ticket de suporte.
    """
    if request.method == 'POST':
        form = ChamadoForm(request.POST, request.FILES)
        if form.is_valid():
            chamado = form.save(commit=False)
            chamado.solicitante = request.user
            chamado.save()
            return redirect('lista_chamados')
    else:
        form = ChamadoForm()
    return render(request, 'helpdesk/novo_chamado.html', {'form': form})


@login_required
def detalhes_chamado(request, id):
    """
    Exibe os detalhes de um chamado específico e processa a inclusão de novos comentários.
    """
    chamado = get_object_or_404(Chamado, id=id)
    comentarios = chamado.comentarios.all().order_by('data_criacao') 

    if request.method == 'POST':
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
        'comentarios': comentarios,
        'form': form
    })


@login_required
def atualizar_status(request, id):
    """
    Endpoint para alteração rápida do status de um chamado.
    """
    chamado = get_object_or_404(Chamado, id=id)
    
    if request.method == 'POST':
        novo_status = request.POST.get('status')
        if novo_status in dict(Chamado.STATUS_CHOICES).keys():
            chamado.status = novo_status
            chamado.save() 
            
    return redirect('detalhes_chamado', id=chamado.id)


@login_required
def fechar_chamado(request, id):
    """
    Finaliza o chamado, registrando a data de encerramento e o usuário responsável.
    Adiciona a solução fornecida como um comentário no histórico.
    """
    chamado = get_object_or_404(Chamado, id=id)
    
    if request.method == 'POST':
        if request.user.is_staff:
            chamado.status = 'Resolvido'
            chamado.fechado_por = request.user 
            chamado.data_fechamento = timezone.now()
            chamado.save()
            
            texto_resolucao = request.POST.get('resolucao')
            anexo = request.FILES.get('anexo_resolucao')
            
            if texto_resolucao:
                Comentario.objects.create(
                    chamado=chamado,
                    autor=request.user,
                    texto=f"✅ TICKET ENCERRADO POR TI - SOLUÇÃO:\n\n{texto_resolucao}",
                    anexo=anexo
                )
        
        elif chamado.solicitante == request.user:
             chamado.status = 'Resolvido'
             chamado.data_fechamento = timezone.now()
             chamado.save()
                
    return redirect('detalhes_chamado', id=chamado.id)


@login_required
def assumir_chamado(request, chamado_id):
    """
    Atribui o chamado ao técnico que clicou no botão (Ticket Locking).
    """
    chamado = get_object_or_404(Chamado, id=chamado_id)
    
    if not chamado.tecnico:
        chamado.tecnico = request.user
        chamado.save()
        messages.success(request, f"Você assumiu o chamado #{chamado.id}.")
        
    return redirect('detalhes_chamado', id=chamado_id) 


@login_required
def devolver_chamado(request, chamado_id):
    """
    Remove a atribuição do chamado, devolvendo-o para a fila geral.
    """
    chamado = get_object_or_404(Chamado, id=chamado_id)
    
    if chamado.tecnico == request.user:
        chamado.tecnico = None
        chamado.save()
        messages.warning(request, f"Chamado #{chamado.id} devolvido para a fila.")
        
    return redirect('detalhes_chamado', id=chamado_id)


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
def editar_usuario(request, user_id):
    """
    Permite a edição dos dados e nível de acesso de um usuário específico.
    """
    if not request.user.is_superuser:
        return redirect('lista_chamados')
        
    usuario = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        form = EditarUsuarioForm(request.POST, instance=usuario)
        if form.is_valid():
            form.save()
            messages.success(request, f'Usuário {usuario.username} atualizado com sucesso!')
            return redirect('gerenciar_usuarios')
    else:
        form = EditarUsuarioForm(instance=usuario)
        
    return render(request, 'helpdesk/editar_usuario.html', {'form': form, 'usuario': usuario})


@login_required
def alternar_status_usuario(request, user_id):
    """
    Ativa ou desativa o acesso de um usuário ao sistema.
    Impede que o administrador desative a própria conta por acidente.
    """
    if not request.user.is_superuser:
        return redirect('lista_chamados')
        
    usuario = get_object_or_404(User, id=user_id)
    
    if usuario == request.user:
        messages.error(request, "Você não pode desativar sua própria conta.")
        return redirect('gerenciar_usuarios')
        
    usuario.is_active = not usuario.is_active
    usuario.save()
    
    status = "ativado" if usuario.is_active else "inativado"
    messages.success(request, f'Usuário {usuario.username} {status} com sucesso!')
    return redirect('gerenciar_usuarios')