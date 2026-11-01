from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .audit import ator_atual
from .models import Chamado, Comentario, RegistroAuditoria


class HistoricoTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='gestor', is_staff=True, is_superuser=True)
        self.user = User.objects.create_user(username='cliente')
        self.tecnico = User.objects.create_user(username='tecnico', is_staff=True)
        self.ticket = Chamado.objects.create(titulo='Privado', descricao='Dados privados', solicitante=self.user)
        self.client.force_login(self.admin)

    def test_excluir_solicitante_preserva_chamado(self):
        with self.assertRaises(ProtectedError):
            self.user.delete()
        self.assertTrue(Chamado.objects.filter(pk=self.ticket.pk).exists())

    def test_autor_de_comentario_protegido(self):
        Comentario.objects.create(chamado=self.ticket, autor=self.tecnico, texto='Histórico')
        with self.assertRaises(ProtectedError):
            self.tecnico.delete()
        self.assertEqual(self.ticket.comentarios.count(), 1)

    def test_responsaveis_preservados(self):
        for campo in ['tecnico', 'fechado_por']:
            setattr(self.ticket, campo, self.tecnico)
            self.ticket.save()
            with self.subTest(campo=campo), self.assertRaises(ProtectedError):
                User.objects.filter(pk=self.tecnico.pk).delete()

    def test_chamado_com_comentario_nao_cascateia(self):
        Comentario.objects.create(chamado=self.ticket, autor=self.user, texto='Histórico')
        with self.assertRaises(ProtectedError):
            self.ticket.delete()
        self.assertEqual(self.ticket.comentarios.count(), 1)

    def test_admin_exclusao_individual_e_lote_protegidos(self):
        for model, obj in [(User, self.user), (Chamado, self.ticket)]:
            url = reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_delete', args=[obj.pk])
            self.client.post(url, {'post':'yes'})
            self.assertTrue(model.objects.filter(pk=obj.pk).exists())
        request = RequestFactory().post('/admin/')
        request.user = self.admin
        with self.assertRaises(PermissionDenied):
            admin.site._registry[Chamado].delete_queryset(request, Chamado.objects.all())

    def test_terminal_imutavel_no_admin(self):
        for estado in ['Resolvido','Fechado']:
            self.ticket.status = estado;self.ticket.save()
            url = reverse('admin:helpdesk_chamado_change', args=[self.ticket.pk])
            self.assertEqual(self.client.post(url, {'titulo':'Adulterado'}).status_code, 403)
            self.ticket.refresh_from_db()
            self.assertEqual(self.ticket.titulo, 'Privado')
            self.assertEqual(self.ticket.status, estado)

    def test_comentarios_nao_editaveis_no_admin(self):
        comentario = Comentario.objects.create(chamado=self.ticket, autor=self.user, texto='Original')
        url = reverse('admin:helpdesk_comentario_change', args=[comentario.pk])
        self.assertEqual(self.client.post(url, {'texto':'Adulterado'}).status_code, 403)
        comentario.refresh_from_db()
        self.assertEqual(comentario.texto, 'Original')

    def eventos(self):
        return RegistroAuditoria.objects.filter(objeto='helpdesk.chamado', objeto_id=self.ticket.pk, acao='alterado')

    def test_trilha_assumir_status_devolver_com_ator(self):
        self.client.force_login(self.tecnico)
        for rota, dados, campo in [('assumir_chamado',{},'tecnico_id'),
                                  ('atualizar_status',{'status':'Em Andamento'},'status'),
                                  ('devolver_chamado',{},'tecnico_id')]:
            self.assertEqual(self.client.post(reverse(rota,args=[self.ticket.pk]),dados).status_code,302)
            evento = self.eventos().first()
            self.assertEqual(evento.ator, self.tecnico)
            self.assertEqual(evento.origem, 'portal')
            self.assertIn(campo, evento.alteracoes)
        self.assertEqual(self.eventos().count(),3)
        self.assertIsNone(ator_atual.get())

    def test_encerramento_auditado(self):
        self.ticket.tecnico=self.tecnico;self.ticket.save()
        self.client.force_login(self.tecnico)
        self.client.post(reverse('fechar_chamado',args=[self.ticket.pk]), {'resolucao':'Solução privada'})
        evento=self.eventos().first()
        self.assertEqual(evento.alteracoes['status'], {'antes':'Aberto','depois':'Resolvido'})
        self.assertEqual(evento.alteracoes['fechado_por_id']['depois'],self.tecnico.pk)
        self.assertNotIn('Solução privada', str(list(RegistroAuditoria.objects.values())))

    def test_alteracao_conta_auditada_sem_senha_ou_dados_pessoais(self):
        self.client.post(reverse('editar_usuario',args=[self.user.pk]), {
            'username':'novo_nome','email':'privado@example.invalid','nivel_acesso':'ti','is_active':'on',
        })
        evento=RegistroAuditoria.objects.filter(objeto='auth.user',objeto_id=self.user.pk,acao='alterado').first()
        self.assertEqual(evento.ator,self.admin)
        self.assertEqual(evento.alteracoes['is_staff'],{'antes':False,'depois':True})
        self.assertEqual(evento.alteracoes['email'],{'alterado':True})
        self.assertNotIn('privado@example.invalid', str(evento.alteracoes))
        self.user.refresh_from_db()
        self.user.set_password('Segredo-de-teste-19!');self.user.save()
        eventos=str(list(RegistroAuditoria.objects.values_list('alteracoes',flat=True)))
        self.assertNotIn('Segredo-de-teste-19!',eventos)
        self.assertNotIn(self.user.password,eventos)

    def test_registro_admin_origem_e_permissoes(self):
        grupo=Group.objects.create(name='Suporte')
        token=ator_atual.set(self.admin.pk)
        try:self.user.groups.add(grupo)
        finally:ator_atual.reset(token)
        evento=RegistroAuditoria.objects.filter(objeto='auth.user',objeto_id=self.user.pk,acao='permissoes').first()
        self.assertEqual(evento.ator,self.admin)
        self.assertEqual(evento.alteracoes['groups']['ids'],[grupo.pk])
        # Alteração real pela view de admin, com o middleware preenchendo a origem.
        self.client.post(reverse('admin:auth_user_change',args=[self.user.pk]), {
            'username':self.user.username,'is_active':'on','first_name':'Novo nome',
            'date_joined_0':self.user.date_joined.strftime('%Y-%m-%d'),
            'date_joined_1':self.user.date_joined.strftime('%H:%M:%S'),
        })
        evento=RegistroAuditoria.objects.filter(objeto='auth.user',objeto_id=self.user.pk,acao='alterado',origem='admin').first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.ator,self.admin)

    def test_falha_na_auditoria_reverte_atribuicao(self):
        self.client.force_login(self.tecnico)
        with patch('helpdesk.views.registrar', side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('assumir_chamado',args=[self.ticket.pk]))
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.tecnico)
        self.assertEqual(self.eventos().count(),0)

    def test_rollback_nao_deixa_auditoria(self):
        antes=RegistroAuditoria.objects.count()
        with transaction.atomic():
            self.ticket.status='Em Andamento';self.ticket.save()
            transaction.set_rollback(True)
        self.assertEqual(RegistroAuditoria.objects.count(),antes)

    def test_trilha_somente_leitura_e_admin(self):
        evento=RegistroAuditoria.objects.first()
        url=reverse('admin:helpdesk_registroauditoria_change',args=[evento.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.post(url,{'acao':'adulterado'}).status_code,403)
        self.assertEqual(self.client.post(reverse('admin:helpdesk_registroauditoria_delete',args=[evento.pk]),{'post':'yes'}).status_code,403)
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.get(url).status_code,403)
