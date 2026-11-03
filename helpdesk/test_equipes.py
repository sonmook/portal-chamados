from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase
from django.urls import reverse

from .models import Chamado, Equipe, IntegranteEquipe, RegistroAuditoria


class EquipesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin-equipes', is_staff=True, is_superuser=True)
        self.tecnico = User.objects.create_user('tecnico', is_staff=True)
        self.outro = User.objects.create_user('outro', is_staff=True)
        self.cliente = User.objects.create_user('cliente')
        self.inativo = User.objects.create_user('inativo', is_staff=True, is_active=False)
        self.equipe = Equipe.objects.create(nome='Equipe de teste')
        self.lista = reverse('gerenciar_equipes')
        self.nova = reverse('criar_equipe')
        self.editar = reverse('editar_equipe', args=[self.equipe.pk])
        self.client.force_login(self.admin)

    def dados(self, **extras):
        self.equipe.refresh_from_db()
        dados = {'nome': self.equipe.nome, 'descricao': 'Responsabilidades', 'ativa': 'on',
                 'integrantes': [self.tecnico.pk, self.outro.pk], 'coordenadores': [self.tecnico.pk],
                 'versao_atual': self.equipe.versao}
        dados.update(extras)
        return dados

    def test_somente_administrador_gerencia_equipes(self):
        for user in (self.tecnico, self.cliente):
            self.client.force_login(user)
            for url in (self.lista, self.nova, self.editar):
                self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(self.editar, self.dados()).status_code, 403)
            self.assertNotContains(self.client.get(reverse('lista_chamados')), 'Gerenciar Equipes')
        self.assertEqual(Client().get(self.lista).status_code, 302)

    def test_menu_listagem_e_criacao_auditada(self):
        self.assertContains(self.client.get(reverse('lista_chamados')), 'Gerenciar Equipes')
        self.assertContains(self.client.get(self.lista), self.equipe.nome)
        resposta = self.client.post(self.nova, self.dados(nome='Nova equipe', versao_atual=0))
        self.assertRedirects(resposta, self.lista)
        equipe = Equipe.objects.get(nome='Nova equipe')
        self.assertEqual(equipe.vinculos.count(), 2)
        self.assertTrue(equipe.vinculos.get(usuario=self.tecnico).coordenador)
        evento = RegistroAuditoria.objects.get(objeto='helpdesk.equipe', objeto_id=equipe.pk)
        self.assertEqual(evento.ator, self.admin)
        self.assertEqual(evento.origem, 'portal')
        self.assertEqual(evento.acao, 'criado')
        self.assertEqual(evento.alteracoes['coordenadores']['depois'], [self.tecnico.pk])
        self.assertEqual(evento.alteracoes['nome'], {'alterado': True})

    def test_coordenador_deve_ser_integrante(self):
        resposta = self.client.post(self.editar, self.dados(integrantes=[self.outro.pk]))
        self.assertContains(resposta, 'Coordenadores devem fazer parte')
        self.assertFalse(self.equipe.vinculos.exists())

    def test_contas_sem_acesso_tecnico_nao_podem_ser_adicionadas(self):
        for user in (self.cliente, self.inativo):
            resposta = self.client.post(self.editar, self.dados(integrantes=[user.pk], coordenadores=[]))
            self.assertTrue(resposta.context['form'].errors)
            self.assertFalse(self.equipe.vinculos.exists())

    def test_tecnico_pode_integrar_varias_equipes_sem_mudar_permissoes(self):
        self.client.post(self.editar, self.dados())
        self.client.post(self.nova, self.dados(nome='Outra equipe'))
        self.assertEqual(self.tecnico.vinculos_equipes.count(), 2)
        self.tecnico.refresh_from_db()
        self.assertFalse(self.tecnico.is_superuser)
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.get(self.lista).status_code, 403)

    def test_remocao_e_troca_de_coordenador_auditadas(self):
        self.client.post(self.editar, self.dados())
        self.client.post(self.editar, self.dados(integrantes=[self.outro.pk], coordenadores=[self.outro.pk]))
        self.assertEqual(list(self.equipe.vinculos.values_list('usuario_id', flat=True)), [self.outro.pk])
        evento = RegistroAuditoria.objects.filter(objeto='helpdesk.equipe', objeto_id=self.equipe.pk).first()
        self.assertEqual(evento.alteracoes['coordenadores'], {'antes': [self.tecnico.pk], 'depois': [self.outro.pk]})

    def test_desativacao_e_reativacao_preservam_integrantes(self):
        self.client.post(self.editar, self.dados())
        self.client.post(self.editar, self.dados(ativa=''))
        self.equipe.refresh_from_db()
        self.assertFalse(self.equipe.ativa)
        self.assertEqual(self.equipe.vinculos.count(), 2)
        self.client.post(self.editar, self.dados())
        self.equipe.refresh_from_db()
        self.assertTrue(self.equipe.ativa)

    def test_copia_antiga_nao_sobrescreve_equipe(self):
        antiga = self.dados()
        self.client.post(self.editar, self.dados(nome='Nome atualizado'))
        resposta = self.client.post(self.editar, antiga)
        self.assertEqual(resposta.status_code, 409)
        self.equipe.refresh_from_db()
        self.assertEqual(self.equipe.nome, 'Nome atualizado')

    def test_csrf_get_e_campos_invalidos(self):
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.admin)
        self.assertEqual(protegido.post(self.editar, self.dados()).status_code, 403)
        self.client.get(self.editar)
        self.assertFalse(self.equipe.vinculos.exists())
        for dados in (self.dados(nome=' '), self.dados(nome='x' * 101), self.dados(descricao='x' * 1001)):
            self.assertTrue(self.client.post(self.editar, dados).context['form'].errors)
        self.assertEqual(self.client.delete(self.editar).status_code, 405)

    def test_nome_e_vinculo_unicos_no_banco(self):
        self.assertTrue(self.client.post(self.nova, self.dados(nome='EQUIPE DE TESTE')).context['form'].errors)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Equipe.objects.create(nome='EQUIPE DE TESTE')
        IntegranteEquipe.objects.create(equipe=self.equipe, usuario=self.tecnico)
        with self.assertRaises(IntegrityError), transaction.atomic():
            IntegranteEquipe.objects.create(equipe=self.equipe, usuario=self.tecnico)

    def test_falha_de_auditoria_reverte_equipe_e_vinculos(self):
        with patch('helpdesk.equipes.registrar', side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.editar, self.dados(nome='Não persistir'))
        self.equipe.refresh_from_db()
        self.assertEqual(self.equipe.nome, 'Equipe de teste')
        self.assertFalse(self.equipe.vinculos.exists())

    def test_integrante_inativo_nao_e_removido_silenciosamente(self):
        IntegranteEquipe.objects.create(equipe=self.equipe, usuario=self.inativo)
        self.assertContains(self.client.get(self.editar), 'sem acesso de técnico ativo')
        resposta = self.client.post(self.editar, self.dados(integrantes=[self.inativo.pk], coordenadores=[]))
        self.assertContains(resposta, 'Remova da seleção')
        self.assertTrue(self.equipe.vinculos.filter(usuario=self.inativo).exists())

    def test_cadastro_inicial_idempotente_com_seis_equipes(self):
        nomes = ['Central de Serviços — N1', 'Suporte Especializado — N2', 'Infraestrutura e Redes',
                 'Sistemas e Aplicações', 'Identidades e Acessos', 'Segurança da Informação']
        for nome in nomes:
            self.assertTrue(Equipe.objects.filter(nome=nome).exists())
        total = Equipe.objects.count()
        apps = MigrationExecutor(connection).loader.project_state([('helpdesk', '0013_equipes_cadastro')]).apps
        import_module('helpdesk.migrations.0013_equipes_cadastro').cadastrar_equipes(apps, SimpleNamespace(connection=connection))
        self.assertEqual(Equipe.objects.count(), total)

    def test_busca_e_admin_somente_consulta(self):
        resposta = self.client.get(self.lista, {'q': 'Equipe de teste'})
        self.assertEqual(list(resposta.context['page_obj']), [self.equipe])
        for model in (Equipe, IntegranteEquipe):
            registro = admin.site._registry[model]
            self.assertFalse(registro.has_add_permission(None))
            self.assertFalse(registro.has_change_permission(None))
            self.assertFalse(registro.has_delete_permission(None))

    def test_primeira_etapa_nao_restringe_chamados_existentes(self):
        chamado = Chamado.objects.create(titulo='Sem equipe', descricao='Fixture', solicitante=self.cliente)
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.get(reverse('detalhes_chamado', args=[chamado.pk])).status_code, 200)

    def test_paginacao_deterministica_preserva_busca(self):
        Equipe.objects.bulk_create([Equipe(nome=f'Paginação {i:02d}') for i in range(25)])
        resposta = self.client.get(self.lista, {'q': 'Paginação'})
        self.assertEqual(len(resposta.context['page_obj']), 20)
        self.assertContains(resposta, 'page=2')
        segunda = self.client.get(self.lista, {'q': 'Paginação', 'page': 2})
        self.assertEqual(len(segunda.context['page_obj']), 5)
        self.assertEqual(segunda.context['page_obj'][0].nome, 'Paginação 20')

    def test_falha_de_auditoria_na_criacao_nao_deixa_registro_parcial(self):
        with patch('helpdesk.equipes.registrar', side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.nova, self.dados(nome='Não criar'))
        self.assertFalse(Equipe.objects.filter(nome='Não criar').exists())
