"""Exemplos locais, identificados e repetíveis, sem substituir dados existentes."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from helpdesk.models import Chamado, Comentario, Equipe, IntegranteEquipe, Perfil


USUARIOS = (
    ('demo.lucas', 'Lucas', 'Almeida', True, 'Analista de suporte', 'TI'),
    ('demo.ana', 'Ana', 'Costa', True, 'Analista de redes', 'TI'),
    ('demo.bruno', 'Bruno', 'Lima', True, 'Analista de sistemas', 'TI'),
    ('demo.marina', 'Marina', 'Souza', False, 'Analista financeiro', 'Financeiro'),
    ('demo.pedro', 'Pedro', 'Santos', False, 'Assistente comercial', 'Comercial'),
    ('demo.julia', 'Júlia', 'Oliveira', False, 'Analista de pessoas', 'RH'),
)
EQUIPES = ('[DEMO] Suporte Especializado - N2', '[DEMO] Infraestrutura e Redes', '[DEMO] Sistemas')
# Assunto, categoria, prioridade, status, solicitante, equipe, técnico, prazo em minutos.
CHAMADOS = (
    ('Impressora do financeiro não imprime', 'Hardware', 'Alta', 'Aberto', 3, 0, None, -90),
    ('Instalar segundo monitor', 'Hardware', 'Baixa', 'Aberto', 4, 0, 0, 480),
    ('Notebook com lentidão', 'Hardware', 'Normal', 'Em Andamento', 5, 0, 0, 180),
    ('Configurar acesso à VPN', 'Rede', 'Alta', 'Em Andamento', 3, 1, 1, 45),
    ('Wi-Fi instável na sala de reuniões', 'Rede', 'Crítica', 'Aberto', 4, 1, None, -30),
    ('Ponto de rede sem conexão', 'Rede', 'Normal', 'Em Andamento', 5, 1, 1, 30),
    ('Erro ao abrir relatório de vendas', 'Software', 'Alta', 'Em Andamento', 4, 2, 2, 90),
    ('Solicitar acesso ao sistema de RH', 'Acessos', 'Normal', 'Aberto', 5, 2, None, 300),
    ('Atualizar aplicativo financeiro', 'Software', 'Baixa', 'Aberto', 3, 2, 2, 600),
    ('Configuração de e-mail concluída', 'Software', 'Normal', 'Resolvido', 3, 2, 2, 120),
    ('Teclado substituído', 'Hardware', 'Baixa', 'Fechado', 4, 0, 0, 240),
    ('Acesso à pasta compartilhada', 'Acessos', 'Alta', 'Resolvido', 5, 1, 1, -60),
)


class Command(BaseCommand):
    help = 'Cria 6 usuários e 12 chamados fictícios para demonstração local (DEBUG=True).'
    requires_migrations_checks = True

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Dados fictícios disponíveis somente no ambiente local com DEBUG=True.')
        credenciais = []
        novos_chamados = 0
        with transaction.atomic():
            # Recusa colisões antes de criar qualquer registro.
            for login, *_ in USUARIOS:
                existente = User.objects.filter(username=login).first()
                if existente and existente.email != f'{login}@example.invalid':
                    raise CommandError(f'O login {login} já pertence a outro cadastro. Nenhum dado foi criado.')
            usuarios = []
            for login, nome, sobrenome, tecnico, cargo, departamento in USUARIOS:
                usuario = User.objects.filter(username=login).first()
                if usuario is None:
                    senha = secrets.token_urlsafe(15)
                    usuario = User.objects.create_user(
                        login, email=f'{login}@example.invalid', password=senha,
                        first_name=nome, last_name=sobrenome, is_staff=tecnico,
                    )
                    Perfil.objects.get_or_create(usuario=usuario, defaults={
                        'cargo': cargo, 'departamento': departamento,
                    })
                    credenciais.append((login, senha))
                usuarios.append(usuario)
            equipes = []
            for i, nome in enumerate(EQUIPES):
                equipe, _ = Equipe.objects.get_or_create(nome=nome, defaults={
                    'descricao': 'Equipe fictícia para demonstração local.',
                })
                IntegranteEquipe.objects.get_or_create(equipe=equipe, usuario=usuarios[i])
                equipes.append(equipe)
            agora = timezone.now()
            for i, (assunto, categoria, prioridade, status, cliente, equipe, tecnico, minutos) in enumerate(CHAMADOS):
                titulo = f'[DEMO] {assunto}'
                if Chamado.objects.filter(titulo=titulo, solicitante=usuarios[cliente]).exists():
                    continue
                encerrado = status in ('Resolvido', 'Fechado')
                chamado = Chamado.objects.create(
                    titulo=titulo, descricao='Exemplo fictício para explorar o Portal de TI. Sem dados reais.',
                    categoria=categoria, prioridade=prioridade, status=status,
                    solicitante=usuarios[cliente], equipe=equipes[equipe],
                    tecnico=usuarios[tecnico] if tecnico is not None else None,
                    data_vencimento=agora + timedelta(minutes=minutos),
                    data_fechamento=agora - timedelta(hours=1) if encerrado else None,
                )
                criacao = agora - timedelta(hours=24 + i)
                Chamado.objects.filter(pk=chamado.pk).update(data_criacao=criacao, ultima_interacao_em=criacao)
                if tecnico is not None:
                    comentario = Comentario.objects.create(
                        chamado=chamado, autor=usuarios[tecnico],
                        texto='Ajuste concluído e validado neste exemplo fictício.' if encerrado
                        else 'Atendimento iniciado. Estamos analisando esta solicitação fictícia.',
                    )
                    interacao = agora - timedelta(hours=1 if encerrado else 2)
                    Comentario.objects.filter(pk=comentario.pk).update(data_criacao=interacao)
                    Chamado.objects.filter(pk=chamado.pk).update(ultima_interacao_em=interacao)
                novos_chamados += 1
        self.stdout.write(self.style.SUCCESS(
            f'Demonstração pronta: {len(credenciais)} novos usuários e {novos_chamados} novos chamados.'))
        for login, senha in credenciais:
            self.stdout.write(f'Usuário: {login} | Senha: {senha}')
        self.stdout.write('Guarde as senhas acima. Repetir o comando preserva cadastros, senhas e chamados existentes.')
        self.stdout.write('Use seu administrador atual para visualizar todos os chamados. Contas demo não são administradores.')
