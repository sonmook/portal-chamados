from django.urls import path
from . import perfis
from . import views
from . import equipes
from . import regras_encaminhamento

# Define as rotas (URLs) do aplicativo Helpdesk.
# Cada path vincula um endereço web a uma função específica no arquivo views.py.
urlpatterns = [
    path('meu-perfil/foto-base/', perfis.foto_base_perfil, name='foto_base_perfil'),
    path('meu-perfil/', perfis.meu_perfil, name='meu_perfil'),
    path('perfil/foto/<int:usuario_id>/', perfis.foto_perfil, name='foto_perfil'),
    path('equipes/encaminhamento/', regras_encaminhamento.listar_regras, name='listar_regras_encaminhamento'),
    path('equipes/encaminhamento/nova/', regras_encaminhamento.editar_regra, name='criar_regra_encaminhamento'),
    path('equipes/encaminhamento/<int:regra_id>/editar/', regras_encaminhamento.editar_regra, name='editar_regra_encaminhamento'),
    path('equipes/', equipes.gerenciar_equipes, name='gerenciar_equipes'),
    path('equipes/nova/', equipes.editar_equipe, name='criar_equipe'),
    path('equipes/<int:equipe_id>/editar/', equipes.editar_equipe, name='editar_equipe'),
    # --- Painel e Listagem ---
    path('', views.lista_chamados, name='lista_chamados'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # --- Gestão de Chamados ---
    path('chamado/<int:id>/anexo/', views.baixar_anexo, name='baixar_anexo'),
    path('chamado/<int:id>/comentario/<int:comentario_id>/anexo/', views.baixar_anexo, name='baixar_anexo_comentario'),
    path('novo/', views.novo_chamado, name='novo_chamado'),
    path('chamado/<int:id>/', views.detalhes_chamado, name='detalhes_chamado'),
    path('chamado/<int:id>/status/', views.atualizar_status, name='atualizar_status'), 
    path('chamado/<int:id>/fechar/', views.fechar_chamado, name='fechar_chamado'),
    path('chamado/<int:chamado_id>/assumir/', views.assumir_chamado, name='assumir_chamado'),
    path('chamado/<int:chamado_id>/devolver/', views.devolver_chamado, name='devolver_chamado'),
    path('chamado/<int:id>/redistribuir/', views.redistribuir_chamado, name='redistribuir_chamado'),
    
    # --- Gestão de Usuários (Admin) ---
    path('usuarios/', views.gerenciar_usuarios, name='gerenciar_usuarios'),
    path('novo-usuario/', views.criar_usuario, name='criar_usuario'),
    path('usuarios/editar/<int:user_id>/', views.editar_usuario, name='editar_usuario'),
    path('usuarios/status/<int:user_id>/', views.alternar_status_usuario, name='alternar_status_usuario'),
]
