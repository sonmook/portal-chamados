from django.urls import path
from . import views

# Define as rotas (URLs) do aplicativo Helpdesk.
# Cada path vincula um endereço web a uma função específica no arquivo views.py.
urlpatterns = [
    # --- Painel e Listagem ---
    path('', views.lista_chamados, name='lista_chamados'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # --- Gestão de Chamados ---
    path('novo/', views.novo_chamado, name='novo_chamado'),
    path('chamado/<int:id>/', views.detalhes_chamado, name='detalhes_chamado'),
    path('chamado/<int:id>/status/', views.atualizar_status, name='atualizar_status'), 
    path('chamado/<int:id>/fechar/', views.fechar_chamado, name='fechar_chamado'),
    path('chamado/<int:chamado_id>/assumir/', views.assumir_chamado, name='assumir_chamado'),
    path('chamado/<int:chamado_id>/devolver/', views.devolver_chamado, name='devolver_chamado'),
    
    # --- Gestão de Usuários (Admin) ---
    path('usuarios/', views.gerenciar_usuarios, name='gerenciar_usuarios'),
    path('novo-usuario/', views.criar_usuario, name='criar_usuario'),
    path('usuarios/editar/<int:user_id>/', views.editar_usuario, name='editar_usuario'),
    path('usuarios/status/<int:user_id>/', views.alternar_status_usuario, name='alternar_status_usuario'),
]