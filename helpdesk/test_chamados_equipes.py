import tempfile
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from .models import Chamado, Comentario, Equipe, IntegranteEquipe, RegistroAuditoria
from .test_helpers import dados_atribuicao


class ChamadosEquipeTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = override_settings(MEDIA_ROOT=tmp.name)
        config.enable()
        self.addCleanup(config.disable)
        self.n1 = Equipe.objects.get(triagem_padrao=True)
        self.n2 = Equipe.objects.get(nome='Suporte Especializado — N2')
        self.admin = User.objects.create_user('admin', is_staff=True, is_superuser=True)
        self.cliente = User.objects.create_user('cliente')
        self.alheio = User.objects.create_user('alheio')
        self.tec1 = User.objects.create_user('tecnico-n1', is_staff=True)
        self.tec2 = User.objects.create_user('tecnico-n2', is_staff=True)
        self.coord = User.objects.create_user('coordenador-n1', is_staff=True)
        self.reserva = User.objects.create_user('reserva-n1', is_staff=True)
        self.sem_equipe = User.objects.create_user('tecnico-sem-equipe', is_staff=True)
        for usuario in (self.tec1, self.coord, self.reserva):
            IntegranteEquipe.objects.create(equipe=self.n1, usuario=usuario, coordenador=usuario == self.coord)
        IntegranteEquipe.objects.create(equipe=self.n2, usuario=self.tec2)
        self.t1 = Chamado.objects.create(titulo='Privado N1', descricao='Fixture N1', equipe=self.n1,
                                         solicitante=self.cliente, tecnico=self.tec1)
        self.t2 = Chamado.objects.create(titulo='Segredo N2', descricao='Fixture N2', equipe=self.n2,
                                         solicitante=self.alheio, tecnico=self.tec2)
        self.t2.anexo.save('privado.pdf', self.pdf())
        self.comentario = Comentario.objects.create(chamado=self.t2, autor=self.alheio, texto='Mensagem privada N2', anexo=self.pdf())
        self.client.force_login(self.tec1)

    def pdf(self):
        return SimpleUploadedFile('privado.pdf', b'%PDF-1.7 fixture', content_type='application/pdf')

    def transferir(self, chamado=None, equipe=None, tecnico=None, **extras):
        chamado = chamado or self.t1
        dados = {**dados_atribuicao(chamado), 'tecnico': tecnico.pk if tecnico else '',
                 'responsavel_anterior': chamado.tecnico_id or '', 'motivo': 'Encaminhamento especializado'}
        dados['equipe'] = (equipe or self.n2).pk
        dados.update(extras)
        return self.client.post(reverse('redistribuir_chamado', args=[chamado.pk]), dados)

    def test_tecnico_so_ve_equipes_e_nao_baixa_anexos_alheios(self):
        resposta = self.client.get(reverse('lista_chamados'))
        self.assertContains(resposta, self.t1.titulo)
        self.assertNotContains(resposta, self.t2.titulo)
        for nome, args in [('detalhes_chamado', [self.t2.pk]), ('baixar_anexo', [self.t2.pk]),
                           ('baixar_anexo_comentario', [self.t2.pk, self.comentario.pk])]:
            self.assertEqual(self.client.get(reverse(nome, args=args)).status_code, 404)

    def test_acoes_em_equipe_alheia_nao_alteram_chamado(self):
        for nome, dados in [('assumir_chamado', {}), ('devolver_chamado', {}),
                            ('atualizar_status', {'status': 'Aberto'}), ('fechar_chamado', {'resolucao': 'Intrusão'}),
                            ('detalhes_chamado', {'texto': 'Intrusão'}), ('redistribuir_chamado', {})]:
            with self.subTest(nome=nome):
                self.assertEqual(self.client.post(reverse(nome, args=[self.t2.pk]), dados).status_code, 404)
        self.t2.refresh_from_db()
        self.assertEqual(self.t2.tecnico, self.tec2)
        self.assertEqual(self.t2.comentarios.count(), 1)

    def test_solicitante_e_admin_preservam_acesso(self):
        for usuario in (self.alheio, self.admin):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse('detalhes_chamado', args=[self.t2.pk])).status_code, 200)
            resposta = self.client.get(reverse('baixar_anexo_comentario', args=[self.t2.pk, self.comentario.pk]))
            self.assertEqual(resposta.status_code, 200)
            resposta.close()

    def test_tecnico_solicitante_fora_da_equipe_comenta_sem_atuar_como_responsavel(self):
        Chamado.objects.filter(pk=self.t2.pk).update(solicitante=self.tec1)
        self.assertEqual(self.client.post(reverse('detalhes_chamado', args=[self.t2.pk]), {'texto': 'Sou solicitante'}).status_code, 302)
        self.assertEqual(self.client.post(reverse('fechar_chamado', args=[self.t2.pk]), {'resolucao': 'Não permitido'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('assumir_chamado', args=[self.t2.pk])).status_code, 403)

    def test_sem_vinculo_nao_ganha_acesso_por_is_staff_ou_por_atribuicao_direta(self):
        self.client.force_login(self.sem_equipe)
        self.assertEqual(self.client.get(reverse('dashboard')).context['total'], 0)
        Chamado.objects.filter(pk=self.t1.pk).update(tecnico=self.sem_equipe)
        self.assertEqual(self.client.get(reverse('detalhes_chamado', args=[self.t1.pk])).status_code, 404)

    def test_apenas_coordenador_da_origem_ou_admin_distribui(self):
        self.assertEqual(self.transferir().status_code, 403)
        self.client.force_login(self.tec2)
        self.assertEqual(self.transferir().status_code, 404)
        self.client.force_login(self.coord)
        self.assertEqual(self.transferir().status_code, 302)

    def test_coordenacao_nao_dispensa_assumir_o_atendimento(self):
        self.client.force_login(self.coord)
        self.assertEqual(self.client.post(reverse('detalhes_chamado', args=[self.t1.pk]), {'texto': 'Sem atribuição'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('fechar_chamado', args=[self.t1.pk]), {'resolucao': 'Sem atribuição'}).status_code, 403)
        self.assertEqual(self.transferir(equipe=self.n1, tecnico=self.coord).status_code, 302)
        self.assertEqual(self.client.post(reverse('fechar_chamado', args=[self.t1.pk]), {'resolucao': 'Atendimento concluído'}).status_code, 302)

    def test_transferencia_limpa_responsavel_e_muda_acesso_sem_mudar_sla(self):
        self.client.force_login(self.coord)
        prazo, interacao = self.t1.data_vencimento, self.t1.ultima_interacao_em
        resposta = self.transferir()
        self.assertRedirects(resposta, reverse('lista_chamados'))
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.equipe, self.n2)
        self.assertIsNone(self.t1.tecnico)
        self.assertEqual(self.t1.data_vencimento, prazo)
        self.assertEqual(self.t1.ultima_interacao_em, interacao)
        evento = RegistroAuditoria.objects.get(objeto_id=self.t1.pk, acao='redistribuido')
        self.assertEqual(evento.ator, self.coord)
        self.assertEqual(evento.alteracoes['equipe_id'], {'antes': self.n1.pk, 'depois': self.n2.pk})
        self.assertEqual(self.client.get(reverse('detalhes_chamado', args=[self.t1.pk])).status_code, 404)
        self.client.force_login(self.tec2)
        self.assertEqual(self.client.get(reverse('detalhes_chamado', args=[self.t1.pk])).status_code, 200)
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(reverse('detalhes_chamado', args=[self.t1.pk])).status_code, 200)

    def test_transferencia_pode_atribuir_a_integrante_do_destino(self):
        self.client.force_login(self.coord)
        self.assertEqual(self.transferir(tecnico=self.tec2).status_code, 302)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.tecnico, self.tec2)
        self.assertEqual(self.t1.equipe, self.n2)

    def test_nao_atribui_a_usuario_fora_do_destino_inativo_ou_equipe_inativa(self):
        self.client.force_login(self.coord)
        self.assertTrue(self.transferir(tecnico=self.tec1).context['form'].errors)
        self.tec2.is_active = False
        self.tec2.save()
        self.assertTrue(self.transferir(tecnico=self.tec2).context['form'].errors)
        self.n2.ativa = False
        self.n2.save()
        self.assertTrue(self.transferir().context['form'].errors)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.equipe, self.n1)

    def test_distribuicao_na_propria_equipe_e_tecnico_assume_fila(self):
        self.client.force_login(self.coord)
        self.assertEqual(self.transferir(equipe=self.n1, tecnico=self.reserva).status_code, 302)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.tecnico, self.reserva)
        self.assertEqual(self.transferir(equipe=self.n1).status_code, 302)
        self.client.force_login(self.tec1)
        self.assertEqual(self.client.post(reverse('assumir_chamado', args=[self.t1.pk])).status_code, 302)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.tecnico, self.tec1)

    def test_coordenador_nao_distribui_equipe_nao_coordenada_mesmo_como_solicitante(self):
        IntegranteEquipe.objects.create(equipe=self.n2, usuario=self.coord)
        Chamado.objects.filter(pk=self.t2.pk).update(solicitante=self.coord)
        self.client.force_login(self.coord)
        self.assertEqual(self.transferir(chamado=self.t2, equipe=self.n1).status_code, 403)

    def test_versao_rejeita_tela_antiga_apos_ida_e_volta_de_equipe(self):
        self.client.force_login(self.admin)
        antigo = {**dados_atribuicao(self.t1), 'responsavel_anterior': self.tec1.pk,
                  'equipe': self.n2.pk, 'tecnico': '', 'motivo': 'Tela antiga'}
        self.transferir(equipe=self.n2)
        self.transferir(equipe=self.n1, tecnico=self.tec1)
        resposta = self.client.post(reverse('redistribuir_chamado', args=[self.t1.pk]), antigo)
        self.assertEqual(resposta.status_code, 409)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.equipe, self.n1)
        self.assertEqual(RegistroAuditoria.objects.filter(acao='redistribuido', objeto_id=self.t1.pk).count(), 2)

    def test_falha_auditoria_reverte_equipe_e_responsavel(self):
        self.client.force_login(self.coord)
        with patch('helpdesk.views.registrar', side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):
                self.transferir(tecnico=self.tec2)
        self.t1.refresh_from_db()
        self.assertEqual(self.t1.equipe, self.n1)
        self.assertEqual(self.t1.tecnico, self.tec1)

    def test_dashboard_e_filtros_nao_expoem_chamados_ou_ranking_alheios(self):
        contexto = self.client.get(reverse('dashboard')).context
        self.assertEqual(contexto['total'], 1)
        self.assertNotIn(self.tec2.username, [p['username'] for p in contexto['produtividade_equipe']])
        for valor in (str(self.n2.pk), 'invalida', str(2**100)):
            self.assertEqual(self.client.get(reverse('dashboard'), {'equipe': valor}).context['total'], 0)
            self.assertEqual(len(self.client.get(reverse('lista_chamados'), {'equipe': valor}).context['page_obj']), 0)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('dashboard'), {'equipe': self.n2.pk}).context['total'], 1)

    def test_django_admin_tambem_respeita_escopo(self):
        permissoes = Permission.objects.filter(content_type__app_label='helpdesk', codename__in=[
            'view_chamado', 'change_chamado', 'view_comentario', 'change_comentario'])
        self.tec1.user_permissions.add(*permissoes)
        request = RequestFactory().get('/admin/')
        request.user = User.objects.get(pk=self.tec1.pk)
        self.assertEqual(list(admin.site._registry[Chamado].get_queryset(request)), [self.t1])
        self.assertFalse(admin.site._registry[Chamado].has_change_permission(request, self.t1))
        self.assertFalse(admin.site._registry[Comentario].get_queryset(request).filter(pk=self.comentario.pk).exists())
        resposta = self.client.get(reverse('admin:helpdesk_chamado_changelist'))
        self.assertContains(resposta, self.t1.titulo)
        self.assertNotContains(resposta, self.t2.titulo)
        self.assertEqual(self.client.get(reverse('admin:helpdesk_chamado_change', args=[self.t2.pk])).status_code, 302)

    def test_remocao_de_responsavel_com_pendencia_e_desativacao_bloqueadas(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('editar_equipe', args=[self.n1.pk]), {
            'nome': self.n1.nome, 'ativa': 'on', 'integrantes': [self.coord.pk], 'coordenadores': [self.coord.pk],
            'versao_atual': self.n1.versao})
        self.assertContains(resposta, 'Redistribua os chamados ativos')
        self.assertTrue(IntegranteEquipe.objects.filter(equipe=self.n1, usuario=self.tec1).exists())
        resposta = self.client.post(reverse('editar_equipe', args=[self.n2.pk]), {
            'nome': self.n2.nome, 'integrantes': [self.tec2.pk], 'coordenadores': [], 'versao_atual': self.n2.versao})
        self.assertContains(resposta, 'Transfira os chamados pendentes')
        self.n2.refresh_from_db()
        self.assertTrue(self.n2.ativa)

    def test_triagem_permanece_ativa_e_recebe_chamados_apesar_de_renomeada(self):
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('editar_equipe', args=[self.n1.pk]), {
            'nome': self.n1.nome, 'integrantes': [self.tec1.pk], 'versao_atual': self.n1.versao})
        self.assertContains(resposta, 'triagem deve permanecer ativa')
        self.n1.nome = 'Triagem corporativa'
        self.n1.save()
        self.client.force_login(self.cliente)
        self.client.post(reverse('novo_chamado'), {'titulo': 'Novo', 'descricao': 'Fixture', 'categoria': 'Rede',
                                                 'prioridade': 'Normal', 'equipe': self.n2.pk})
        chamado = Chamado.objects.get(titulo='Novo')
        self.assertEqual(chamado.equipe_id, self.n1.pk)

    def test_equipe_inativa_e_remocao_de_vinculo_revogam_acesso(self):
        self.n1.ativa = False
        self.n1.save()
        self.assertEqual(self.client.get(reverse('detalhes_chamado', args=[self.t1.pk])).status_code, 404)
        self.n1.ativa = True
        self.n1.save()
        IntegranteEquipe.objects.filter(usuario=self.tec1, equipe=self.n1).delete()
        self.assertEqual(self.client.get(reverse('detalhes_chamado', args=[self.t1.pk])).status_code, 404)

    def test_admin_com_copia_antiga_nao_desfaz_transferencia(self):
        copia = Chamado.objects.get(pk=self.t1.pk)
        self.client.force_login(self.admin)
        self.transferir(tecnico=self.tec2)
        copia.titulo = 'Título ajustado no admin'
        request = RequestFactory().post('/admin/')
        request.user = self.admin
        admin.site._registry[Chamado].save_model(request, copia, None, True)
        copia.refresh_from_db()
        self.assertEqual(copia.equipe, self.n2)
        self.assertEqual(copia.tecnico, self.tec2)
        self.assertEqual(copia.versao_atribuicao, 1)

    def test_transferencia_requer_csrf_e_finalizados_nao_mudam_de_equipe(self):
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.coord)
        self.assertEqual(protegido.post(reverse('redistribuir_chamado', args=[self.t1.pk]), {}).status_code, 403)
        self.client.force_login(self.coord)
        for status in ('Resolvido', 'Fechado'):
            Chamado.objects.filter(pk=self.t1.pk).update(status=status)
            self.assertEqual(self.transferir().status_code, 403)
            self.t1.refresh_from_db()
            self.assertEqual(self.t1.equipe, self.n1)

    def test_contadores_de_equipe_nao_duplicam_integrantes_com_varios_chamados(self):
        Chamado.objects.create(titulo='Mais um', descricao='Fixture', equipe=self.n1, solicitante=self.cliente)
        self.client.force_login(self.admin)
        equipes = self.client.get(reverse('gerenciar_equipes')).context['page_obj']
        n1 = next(e for e in equipes if e.pk == self.n1.pk)
        self.assertEqual(n1.total_integrantes, 3)
        self.assertEqual(n1.total_pendentes, 2)

    def test_paginacao_preserva_equipe_sem_ampliar_escopo(self):
        for i in range(10):
            Chamado.objects.create(titulo=f'Fila {i}', descricao='Fixture', equipe=self.n1, solicitante=self.cliente)
        resposta = self.client.get(reverse('lista_chamados'), {'equipe': self.n1.pk})
        self.assertContains(resposta, f'equipe={self.n1.pk}')
        self.assertContains(resposta, 'page=2')
        self.assertNotContains(resposta, self.t2.titulo)
