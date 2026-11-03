from datetime import timedelta
from html import unescape
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import re

from django.contrib.auth.models import User
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Chamado, Comentario, RegistroAuditoria


class UltimaInteracaoTests(TestCase):
    def setUp(self):
        self.cliente = User.objects.create_user('cliente')
        self.tecnico = User.objects.create_user('tecnico', is_staff=True)
        self.admin = User.objects.create_user('admin', is_staff=True, is_superuser=True)
        self.chamado = Chamado.objects.create(titulo='Rede & Acesso', descricao='Fixture', categoria='Rede',
                                             solicitante=self.cliente, tecnico=self.tecnico)
        self.client.force_login(self.cliente)
        self.detalhes = reverse('detalhes_chamado', args=[self.chamado.pk])

    def test_sem_comentario_usa_abertura(self):
        self.assertEqual(self.chamado.data_ultima_interacao, self.chamado.data_criacao)

    def test_comentarios_cliente_tecnico_e_solucao_atualizam_interacao(self):
        atualizacao = self.chamado.data_atualizacao
        for i, user in enumerate((self.cliente, self.tecnico)):
            instante = timezone.now() + timedelta(hours=i + 1)
            self.client.force_login(user)
            with patch('django.utils.timezone.now', return_value=instante):
                self.assertEqual(self.client.post(self.detalhes, {'texto': 'Nova resposta'}).status_code, 302)
            self.chamado.refresh_from_db()
            self.assertEqual(self.chamado.ultima_interacao_em, instante)
            self.assertEqual(self.chamado.data_atualizacao, atualizacao)
        instante += timedelta(hours=1)
        with patch('django.utils.timezone.now', return_value=instante):
            self.assertEqual(self.client.post(reverse('fechar_chamado', args=[self.chamado.pk]),
                                             {'resolucao': 'Funcionamento validado'}).status_code, 302)
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.status, 'Resolvido')
        self.assertEqual(self.chamado.ultima_interacao_em, instante)

    def test_requisicoes_sem_nova_mensagem_nao_atualizam(self):
        self.client.get(self.detalhes)
        self.client.post(self.detalhes, {'texto': '  '})
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.detalhes, {'texto': 'Sem responsabilidade'}).status_code, 403)
        self.chamado.refresh_from_db()
        self.assertIsNone(self.chamado.ultima_interacao_em)

    def test_transferencia_nao_disfarca_inatividade(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('redistribuir_chamado', args=[self.chamado.pk]), {
            'tecnico': self.admin.pk, 'responsavel_anterior': self.tecnico.pk, 'motivo': 'Cobertura',
        }).status_code, 302)
        self.chamado.refresh_from_db()
        self.assertIsNone(self.chamado.ultima_interacao_em)

    def test_interacao_nao_recua_com_data_mais_antiga(self):
        futura = timezone.now() + timedelta(hours=1)
        Chamado.objects.filter(pk=self.chamado.pk).update(ultima_interacao_em=futura)
        Comentario.objects.create(chamado=self.chamado, autor=self.cliente, texto='Mensagem')
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.ultima_interacao_em, futura)

    def test_salvar_copia_antiga_do_chamado_nao_apaga_interacao(self):
        comentario = Comentario.objects.create(chamado=self.chamado, autor=self.cliente, texto='Mensagem')
        self.chamado.prioridade = 'Alta'
        self.chamado.save()
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.ultima_interacao_em, comentario.data_criacao)

    def test_salvamento_com_campos_adiados_preserva_interacao(self):
        parcial = Chamado.objects.only('titulo').get(pk=self.chamado.pk)
        comentario = Comentario.objects.create(chamado=self.chamado, autor=self.cliente, texto='Mensagem')
        parcial.titulo = 'Título atualizado'
        parcial.save()
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.titulo, 'Título atualizado')
        self.assertEqual(self.chamado.ultima_interacao_em, comentario.data_criacao)

    def test_rollback_do_fechamento_preserva_interacao(self):
        self.client.force_login(self.tecnico)
        with patch('helpdesk.models.Chamado.save', side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('fechar_chamado', args=[self.chamado.pk]), {'resolucao': 'Solução'})
        self.chamado.refresh_from_db()
        self.assertIsNone(self.chamado.ultima_interacao_em)
        self.assertFalse(Comentario.objects.filter(chamado=self.chamado).exists())

    def test_ordenacao_exclui_finalizados_e_isola_clientes(self):
        antiga = self.chamado.data_criacao - timedelta(days=3)
        Chamado.objects.filter(pk=self.chamado.pk).update(data_criacao=antiga)
        outro = Chamado.objects.create(titulo='Mais recente', descricao='Fixture', solicitante=self.cliente)
        encerrado = Chamado.objects.create(titulo='Resolvido', descricao='Fixture', solicitante=self.cliente, status='Resolvido')
        Chamado.objects.create(titulo='Outro solicitante', descricao='Fixture', solicitante=self.admin)
        url = reverse('lista_chamados')
        resposta = self.client.get(url, {'ordenacao': 'sem_interacao'})
        self.assertEqual([c.pk for c in resposta.context['page_obj']], [self.chamado.pk, outro.pk])
        resposta = self.client.get(url, {'ordenacao': 'interacao_recente'})
        self.assertEqual([c.pk for c in resposta.context['page_obj']], [encerrado.pk, outro.pk, self.chamado.pk])
        self.assertContains(resposta, 'Última interação')
        resposta = self.client.get(url, {'ordenacao': 'invalida'})
        self.assertEqual(resposta.context['ordenacao'], 'novos')

    def test_paginacao_preserva_filtros_e_ordem_com_encoding(self):
        for _ in range(10):
            Chamado.objects.create(titulo='Rede & Acesso', descricao='Fixture', categoria='Rede', solicitante=self.cliente)
        filtros = {'q': 'Rede & Acesso', 'status': 'Aberto', 'categoria': 'Rede', 'ordenacao': 'sem_interacao'}
        resposta = self.client.get(reverse('lista_chamados'), filtros)
        links = re.findall(r'href="([^"]+)"', resposta.content.decode())
        proximo = next(link for link in links if 'page=2' in link)
        parametros = parse_qs(urlsplit(unescape(proximo)).query)
        for chave, valor in filtros.items():
            self.assertEqual(parametros[chave], [valor])

    def test_preenchimento_historico_usa_datas_registradas(self):
        inicio = timezone.now() - timedelta(days=5)
        encerramento = inicio + timedelta(days=2)
        Chamado.objects.filter(pk=self.chamado.pk).update(
            data_criacao=inicio, data_fechamento=encerramento, ultima_interacao_em=None,
        )
        comentario = Comentario.objects.create(chamado=self.chamado, autor=self.cliente, texto='Histórico')
        Comentario.objects.filter(pk=comentario.pk).update(data_criacao=inicio + timedelta(days=1))
        sem_comentarios = Chamado.objects.create(titulo='Sem mensagens', descricao='Fixture', solicitante=self.cliente)
        apps = MigrationExecutor(connection).loader.project_state([('helpdesk', '0012_ultima_interacao')]).apps
        total_auditoria = RegistroAuditoria.objects.count()
        import_module('helpdesk.migrations.0012_ultima_interacao').preencher_interacoes(apps, SimpleNamespace(connection=connection))
        self.chamado.refresh_from_db()
        sem_comentarios.refresh_from_db()
        self.assertEqual(self.chamado.ultima_interacao_em, encerramento)
        self.assertEqual(sem_comentarios.ultima_interacao_em, sem_comentarios.data_criacao)
        Comentario.objects.filter(pk=comentario.pk).update(data_criacao=encerramento + timedelta(days=1))
        import_module('helpdesk.migrations.0012_ultima_interacao').preencher_interacoes(apps, SimpleNamespace(connection=connection))
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.ultima_interacao_em, encerramento + timedelta(days=1))
        self.assertEqual(RegistroAuditoria.objects.count(), total_auditoria)
