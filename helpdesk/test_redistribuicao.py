from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .admin import UsuarioProtegidoForm
from .models import Chamado, RegistroAuditoria


class RedistribuicaoTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin-transferencia', is_staff=True, is_superuser=True)
        self.tecnico = User.objects.create_user('tecnico', is_staff=True)
        self.novo = User.objects.create_user('novo-tecnico', is_staff=True)
        self.cliente = User.objects.create_user('cliente')
        self.chamado = Chamado.objects.create(titulo='Transferência', descricao='Fixture',
                                             solicitante=self.cliente, tecnico=self.tecnico)
        self.url = reverse('redistribuir_chamado', args=[self.chamado.pk])
        self.client.force_login(self.admin)

    def dados(self, **extras):
        dados = {'tecnico': self.novo.pk, 'responsavel_anterior': self.tecnico.pk, 'motivo': 'Férias do responsável'}
        dados.update(extras)
        return dados

    def test_transferencia_auditada_com_ator_e_motivo(self):
        anterior = self.chamado.data_atualizacao
        resposta = self.client.post(self.url, self.dados())
        self.assertRedirects(resposta, reverse('detalhes_chamado', args=[self.chamado.pk]))
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.tecnico, self.novo)
        self.assertGreater(self.chamado.data_atualizacao, anterior)
        evento = RegistroAuditoria.objects.get(acao='redistribuido', objeto_id=self.chamado.pk)
        self.assertEqual(evento.ator, self.admin)
        self.assertEqual(evento.origem, 'portal')
        self.assertEqual(evento.alteracoes, {'tecnico_id': {'antes': self.tecnico.pk, 'depois': self.novo.pk},
                                            'motivo': 'Férias do responsável'})

    def test_apenas_admin_e_csrf(self):
        for user in (self.cliente, self.tecnico):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.post(self.url, self.dados()).status_code, 403)
        anonimo = Client()
        self.assertEqual(anonimo.get(self.url).status_code, 302)
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.admin)
        self.assertEqual(protegido.post(self.url, self.dados()).status_code, 403)

    def test_get_nao_transfere_e_mostra_formulario(self):
        self.assertContains(self.client.get(self.url), 'Confirmar transferência')
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.tecnico, self.tecnico)
        self.assertFalse(RegistroAuditoria.objects.filter(acao='redistribuido').exists())

    def test_alvo_e_motivo_invalidos(self):
        inativo = User.objects.create_user('inativo', is_staff=True, is_active=False)
        for dados in (self.dados(tecnico=inativo.pk), self.dados(tecnico=self.cliente.pk),
                      self.dados(tecnico=self.tecnico.pk), self.dados(tecnico=999999),
                      self.dados(motivo='  '), self.dados(motivo='x' * 501)):
            with self.subTest(dados=dados):
                resposta = self.client.post(self.url, dados)
                self.assertEqual(resposta.status_code, 200)
                self.assertTrue(resposta.context['form'].errors)
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.tecnico, self.tecnico)

    def test_terminais_preservam_responsavel(self):
        for status in ('Resolvido', 'Fechado'):
            Chamado.objects.filter(pk=self.chamado.pk).update(status=status, fechado_por=self.tecnico)
            self.assertEqual(self.client.post(self.url, self.dados()).status_code, 403)
            self.chamado.refresh_from_db()
            self.assertEqual(self.chamado.tecnico, self.tecnico)
            self.assertEqual(self.chamado.fechado_por, self.tecnico)

    def test_pagina_desatualizada_nao_sobrescreve_atribuicao(self):
        Chamado.objects.filter(pk=self.chamado.pk).update(tecnico=None)
        self.assertEqual(self.client.post(self.url, self.dados()).status_code, 409)
        self.chamado.refresh_from_db()
        self.assertIsNone(self.chamado.tecnico)
        self.assertFalse(RegistroAuditoria.objects.filter(acao='redistribuido').exists())

    def test_falha_auditoria_reverte_transferencia(self):
        with patch('helpdesk.views.registrar', side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, self.dados())
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.tecnico, self.tecnico)

    def test_recupera_chamado_de_tecnico_inativo_e_atribui_da_fila(self):
        self.tecnico.is_active = False
        self.tecnico.save()
        self.assertEqual(self.client.post(self.url, self.dados()).status_code, 302)
        Chamado.objects.filter(pk=self.chamado.pk).update(tecnico=None)
        self.assertEqual(self.client.post(self.url, self.dados(responsavel_anterior='')).status_code, 302)

    def test_desativacao_bloqueada_e_pendencias_visiveis(self):
        resposta = self.client.post(reverse('alternar_status_usuario', args=[self.tecnico.pk]))
        self.assertRedirects(resposta, reverse('editar_usuario', args=[self.tecnico.pk]))
        self.tecnico.refresh_from_db()
        self.assertTrue(self.tecnico.is_active)
        self.assertContains(self.client.get(reverse('editar_usuario', args=[self.tecnico.pk])), self.url)
        self.client.post(self.url, self.dados())
        self.client.post(reverse('alternar_status_usuario', args=[self.tecnico.pk]))
        self.tecnico.refresh_from_db()
        self.assertFalse(self.tecnico.is_active)

    def test_rebaixamento_bloqueado_no_portal_e_admin(self):
        resposta = self.client.post(reverse('editar_usuario', args=[self.tecnico.pk]), {
            'username': self.tecnico.username, 'nivel_acesso': 'cliente', 'is_active': 'on',
        })
        self.assertContains(resposta, 'Redistribua os chamados pendentes')
        form = UsuarioProtegidoForm({'username': self.tecnico.username, 'is_active': 'on'}, instance=self.tecnico)
        self.assertFalse(form.is_valid())
        self.assertIn('Redistribua os chamados pendentes', str(form.errors))
        self.tecnico.refresh_from_db()
        self.assertTrue(self.tecnico.is_staff)

    def test_finalizados_nao_bloqueiam_desativacao(self):
        Chamado.objects.filter(pk=self.chamado.pk).update(status='Resolvido')
        self.client.post(reverse('alternar_status_usuario', args=[self.tecnico.pk]))
        self.tecnico.refresh_from_db()
        self.assertFalse(self.tecnico.is_active)
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.tecnico, self.tecnico)

    def test_transferencia_altera_quem_pode_responder(self):
        self.client.post(self.url, self.dados())
        detalhes = reverse('detalhes_chamado', args=[self.chamado.pk])
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.post(detalhes, {'texto': 'Resposta antiga'}).status_code, 403)
        self.client.force_login(self.novo)
        self.assertEqual(self.client.post(detalhes, {'texto': 'Novo responsável'}).status_code, 302)

    def test_admin_nao_altera_tecnico_sem_fluxo_auditado(self):
        from django.contrib import admin
        self.assertIn('tecnico', admin.site._registry[Chamado].readonly_fields)
        self.assertEqual(self.client.put(self.url).status_code, 405)
