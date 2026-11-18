from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models.query import QuerySet
from django.test import Client, RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .estados import AGUARDANDO_SOLICITANTE, AGUARDANDO_FORNECEDOR, EM_ANDAMENTO, EM_ESPERA
from .models import Chamado, Comentario, Equipe, HistoricoStatus, IntegranteEquipe, Notificacao, RegistroAuditoria, ResolucaoConquista
from .sla import processar_alertas_sla
from .test_helpers import dados_situacao, dados_atribuicao, restaurar_migracoes_atuais
from .user_security import validar_pendencias


class EstadosEsperaTests(TestCase):
    def setUp(self):
        self.cliente = User.objects.create_user('cliente-espera')
        self.alheio = User.objects.create_user('cliente-alheio-espera')
        self.tecnico = User.objects.create_user('tecnico-espera', is_staff=True)
        self.outro = User.objects.create_user('tecnico-outro-espera', is_staff=True)
        self.admin = User.objects.create_user('admin-espera', is_staff=True, is_superuser=True)
        self.equipe = Equipe.objects.get(triagem_padrao=True)
        for usuario in (self.tecnico, self.outro):
            IntegranteEquipe.objects.create(usuario=usuario, equipe=self.equipe)
        self.ticket = Chamado.objects.create(titulo='Rede aguardando retorno', descricao='Fixture',
            solicitante=self.cliente, tecnico=self.tecnico, equipe=self.equipe, categoria='Rede',
            data_vencimento=timezone.now() + timedelta(minutes=30))
        self.status_url = reverse('atualizar_status', args=[self.ticket.pk])
        self.detalhes = reverse('detalhes_chamado', args=[self.ticket.pk])
        self.client.force_login(self.tecnico)

    def alterar(self, destino, motivo='Aguardando evidência para continuar.', **extra):
        return self.client.post(self.status_url, {'status': destino, 'motivo': motivo,
            **dados_situacao(self.ticket), **extra})

    def test_estados_de_espera_registram_motivo_autor_e_data_sem_alterar_prazo(self):
        prazo, abertura = self.ticket.data_vencimento, self.ticket.data_criacao
        for destino in EM_ESPERA:
            resposta = self.alterar(destino)
            self.assertEqual(resposta.status_code, 302)
            self.ticket.refresh_from_db()
            self.assertEqual(self.ticket.status, destino)
            self.assertTrue(self.ticket.em_espera)
            self.assertEqual(self.ticket.motivo_espera, 'Aguardando evidência para continuar.')
            self.assertIsNotNone(self.ticket.espera_desde)
            self.assertEqual(self.ticket.data_vencimento, prazo)
            self.assertEqual(self.ticket.data_criacao, abertura)
            self.assertIsNone(self.ticket.ultima_interacao_em)
            evento = self.ticket.historico_status.first()
            self.assertEqual(evento.autor, self.tecnico)
            self.assertEqual(evento.criado_em, self.ticket.espera_desde)
            self.assertEqual(evento.status_novo, destino)
        self.assertFalse(self.ticket.comentarios.exists())

    def test_motivo_obrigatorio_e_limitado_sem_gravacao_invalida(self):
        antes = RegistroAuditoria.objects.count()
        for motivo in ('', '  \n ', 'x' * 501):
            resposta = self.alterar(AGUARDANDO_SOLICITANTE, motivo)
            self.assertEqual(resposta.status_code, 400)
            self.assertIn('motivo', resposta.context['situacao_form'].errors)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'Aberto')
        self.assertFalse(HistoricoStatus.objects.exists())
        self.assertFalse(Notificacao.objects.exists())
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_somente_responsavel_altera_estado_e_acesso_alheio_e_oculto(self):
        for usuario, codigo in ((self.cliente, 403), (self.outro, 403), (self.admin, 403), (self.alheio, 404)):
            self.client.force_login(usuario)
            self.assertEqual(self.alterar(AGUARDANDO_SOLICITANTE).status_code, codigo)
        self.assertFalse(HistoricoStatus.objects.exists())

    def test_acao_exige_post_login_e_csrf(self):
        self.assertEqual(self.client.get(self.status_url).status_code, 405)
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.tecnico)
        self.assertEqual(cliente.post(self.status_url, {'status': AGUARDANDO_SOLICITANTE,
            'motivo': 'Retorno', **dados_situacao(self.ticket)}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.alterar(AGUARDANDO_SOLICITANTE).status_code, 302)
        self.assertFalse(HistoricoStatus.objects.exists())

    def test_versoes_obrigatorias_e_estados_finais_nao_burlam_solucao(self):
        self.assertEqual(self.client.post(self.status_url,
            {'status': AGUARDANDO_SOLICITANTE, 'motivo': 'Retorno'}).status_code, 400)
        for destino in ('Resolvido', 'Fechado', 'Inexistente'):
            self.assertEqual(self.alterar(destino).status_code, 400)
        self.assertFalse(HistoricoStatus.objects.exists())

    def test_tela_antiga_nao_sobrescreve_mudanca_mais_recente(self):
        antigo = dados_situacao(self.ticket)
        self.alterar(AGUARDANDO_SOLICITANTE)
        resposta = self.client.post(self.status_url, {'status': AGUARDANDO_FORNECEDOR,
            'motivo': 'Novo retorno', **antigo})
        self.assertEqual(resposta.status_code, 409)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, AGUARDANDO_SOLICITANTE)
        self.assertEqual(self.ticket.historico_status.count(), 1)
        self.assertEqual(Notificacao.objects.count(), 1)

    def test_ciclo_de_atribuicao_novo_invalida_formulario_antigo(self):
        antigo = dados_situacao(self.ticket)
        Chamado.objects.filter(pk=self.ticket.pk).update(versao_atribuicao=1)
        resposta = self.client.post(self.status_url, {'status': AGUARDANDO_SOLICITANTE,
            'motivo': 'Retorno', **antigo})
        self.assertEqual(resposta.status_code, 409)
        self.assertFalse(HistoricoStatus.objects.exists())

    def test_conflito_entre_leitura_e_gravacao_nao_cria_evento(self):
        original = QuerySet.update
        def disputar(consulta, **campos):
            if consulta.model is Chamado and 'versao_status' in campos:
                return 0
            return original(consulta, **campos)
        antes = RegistroAuditoria.objects.count()
        with patch.object(QuerySet, 'update', disputar):
            self.assertEqual(self.alterar(AGUARDANDO_SOLICITANTE).status_code, 409)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'Aberto')
        self.assertFalse(HistoricoStatus.objects.exists())
        self.assertFalse(Notificacao.objects.exists())
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_edicao_administrativa_antiga_nao_reverte_espera(self):
        antiga = Chamado.objects.get(pk=self.ticket.pk)
        self.alterar(AGUARDANDO_FORNECEDOR)
        self.ticket.refresh_from_db()
        inicio = self.ticket.espera_desde
        antiga.titulo = 'Título administrativo corrigido'
        request = RequestFactory().post('/admin/')
        request.user = self.admin
        admin.site._registry[Chamado].save_model(request, antiga, None, change=True)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, AGUARDANDO_FORNECEDOR)
        self.assertEqual(self.ticket.versao_status, 1)
        self.assertEqual(self.ticket.espera_desde, inicio)
        self.assertEqual(self.ticket.motivo_espera, 'Aguardando evidência para continuar.')
        self.assertEqual(self.ticket.titulo, 'Título administrativo corrigido')

    def test_selecionar_estado_atual_nao_cria_evento_ou_notificacao(self):
        atualizado = self.ticket.data_atualizacao
        self.assertEqual(self.alterar('Aberto', '').status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.data_atualizacao, atualizado)
        self.assertFalse(HistoricoStatus.objects.exists())
        self.assertFalse(Notificacao.objects.exists())

    def test_retomada_manual_limpa_espera_e_preserva_historico(self):
        self.alterar(AGUARDANDO_FORNECEDOR, 'Peça solicitada ao fornecedor.')
        self.alterar(EM_ANDAMENTO, 'Peça recebida.')
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.espera_desde)
        self.assertEqual(self.ticket.motivo_espera, '')
        self.assertEqual(self.ticket.historico_status.count(), 2)
        self.assertEqual(self.ticket.historico_status.last().motivo, 'Peça solicitada ao fornecedor.')

    def test_resposta_do_solicitante_retoma_sem_duplicar_aviso_de_resposta(self):
        self.alterar(AGUARDANDO_SOLICITANTE)
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.post(self.detalhes, {'texto': 'Enviei as informações solicitadas.'}).status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, EM_ANDAMENTO)
        self.assertIsNone(self.ticket.espera_desde)
        self.assertEqual(self.ticket.historico_status.first().autor, self.cliente)
        self.assertEqual(self.ticket.historico_status.count(), 2)
        self.assertEqual(Notificacao.objects.filter(destinatario=self.tecnico, tipo='resposta').count(), 1)
        self.assertEqual(Notificacao.objects.filter(tipo='status').count(), 1)

    def test_resposta_do_tecnico_nao_encerra_espera_do_solicitante(self):
        self.alterar(AGUARDANDO_SOLICITANTE)
        self.client.post(self.detalhes, {'texto': 'Lembrete das informações necessárias.'})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, AGUARDANDO_SOLICITANTE)
        self.assertEqual(self.ticket.historico_status.count(), 1)

    def test_resposta_do_solicitante_nao_encerra_espera_de_fornecedor(self):
        self.alterar(AGUARDANDO_FORNECEDOR)
        self.client.force_login(self.cliente)
        self.client.post(self.detalhes, {'texto': 'Alguma previsão?'})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, AGUARDANDO_FORNECEDOR)

    def test_resposta_invalida_nao_retoma_atendimento(self):
        self.alterar(AGUARDANDO_SOLICITANTE)
        self.client.force_login(self.cliente)
        self.client.post(self.detalhes, {'texto': '  '})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, AGUARDANDO_SOLICITANTE)
        self.assertEqual(self.ticket.historico_status.count(), 1)

    def test_falha_na_mensagem_reverte_a_retomada_automatica(self):
        self.alterar(AGUARDANDO_SOLICITANTE)
        self.client.force_login(self.cliente)
        with patch('helpdesk.views.Comentario.save', side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.detalhes, {'texto': 'Retorno válido'})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, AGUARDANDO_SOLICITANTE)
        self.assertEqual(self.ticket.historico_status.count(), 1)
        self.assertFalse(Comentario.objects.exists())

    def test_falha_na_notificacao_reverte_estado_historico_e_auditoria(self):
        antes = RegistroAuditoria.objects.count()
        with patch('helpdesk.notificacoes.notificar_status', side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError):
                self.alterar(AGUARDANDO_SOLICITANTE)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'Aberto')
        self.assertFalse(HistoricoStatus.objects.exists())
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_solucao_na_espera_limpa_estado_e_registra_uma_resolucao(self):
        self.alterar(AGUARDANDO_FORNECEDOR)
        prazo = self.ticket.data_vencimento
        self.assertEqual(self.client.post(reverse('fechar_chamado', args=[self.ticket.pk]),
            {'resolucao': 'Funcionamento validado após troca da peça.'}).status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'Resolvido')
        self.assertEqual(self.ticket.data_vencimento, prazo)
        self.assertIsNone(self.ticket.espera_desde)
        self.assertEqual(self.ticket.motivo_espera, '')
        self.assertEqual(self.ticket.historico_status.first().status_novo, 'Resolvido')
        self.assertEqual(ResolucaoConquista.objects.filter(chamado=self.ticket).count(), 1)
        self.assertEqual(self.alterar(EM_ANDAMENTO).status_code, 403)

    def test_espera_continua_na_fila_prazo_resumo_e_indicadores(self):
        self.alterar(AGUARDANDO_SOLICITANTE)
        r = self.client.get(reverse('lista_chamados'), {'fila': 'minha', 'sla': 'proximos', 'status': AGUARDANDO_SOLICITANTE})
        self.assertEqual([c.pk for c in r.context['page_obj']], [self.ticket.pk])
        self.assertEqual(next(c['total'] for c in r.context['resumo_operacional'] if c['chave'] == 'minha'), 1)
        self.assertContains(r, 'Resposta do solicitante')
        self.assertEqual(self.client.get(reverse('dashboard')).context['em_espera'], 1)
        Chamado.objects.filter(pk=self.ticket.pk).update(data_vencimento=timezone.now()-timedelta(minutes=1))
        self.assertEqual(processar_alertas_sla()['sla_vencido'], 1)
        self.client.force_login(self.admin)
        resumo = self.client.get(reverse('indicadores_administracao'), {'periodo': 'sempre'}).context['resumo']
        self.assertEqual(resumo['ativos'], 1)
        self.assertEqual(resumo['resolvidos'], 0)
        self.assertEqual(resumo['ativos_vencidos'], 1)

    def test_historico_e_formularios_respeitam_visibilidade_e_escapam_html(self):
        self.alterar(AGUARDANDO_SOLICITANTE, '<script>alert("x")</script> Evidência solicitada.')
        self.client.force_login(self.cliente)
        r = self.client.get(self.detalhes)
        self.assertContains(r, '&lt;script&gt;')
        self.assertNotContains(r, '<script>alert(')
        self.assertNotContains(r, 'Salvar situação')
        self.assertContains(r, 'Histórico de situações')
        self.assertContains(r, 'O SLA continua contando durante a espera.')
        self.client.force_login(self.alheio)
        self.assertEqual(self.client.get(self.detalhes).status_code, 404)
        self.assertNotIn('Evidência solicitada', str(list(RegistroAuditoria.objects.values())))

    def test_historico_paginado_e_formulario_de_comentario_apontam_ao_detalhe(self):
        for i in range(21):
            self.alterar(EM_ANDAMENTO if i % 2 == 0 else 'Aberto', '')
        r = self.client.get(self.detalhes, {'historico_page': 2})
        self.assertEqual(len(r.context['historico_status']), 1)
        self.assertContains(r, f'action="{self.detalhes}" method="POST"')
        r = self.alterar(AGUARDANDO_SOLICITANTE, '')
        self.assertContains(r, f'href="{self.detalhes}?historico_page=2', status_code=400)
        self.assertContains(r, f'action="{self.detalhes}" method="POST"', status_code=400)

    def test_espera_permanece_pendente_para_desativacao_e_redistribuicao(self):
        self.alterar(AGUARDANDO_FORNECEDOR)
        with self.assertRaises(ValidationError):
            validar_pendencias(self.tecnico.pk, False, True)
        destino = Equipe.objects.get(nome='Infraestrutura e Redes')
        IntegranteEquipe.objects.create(equipe=destino, usuario=self.outro)
        self.client.force_login(self.admin)
        resposta = self.client.post(reverse('redistribuir_chamado', args=[self.ticket.pk]), {
            **dados_atribuicao(self.ticket), 'equipe': destino.pk, 'tecnico': self.outro.pk,
            'responsavel_anterior': self.tecnico.pk, 'motivo': 'Acompanhamento especializado'})
        self.assertEqual(resposta.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, AGUARDANDO_FORNECEDOR)
        self.assertEqual(self.ticket.tecnico_id, self.outro.pk)


class MigracaoEstadosEsperaTests(TransactionTestCase):
    def tearDown(self):
        restaurar_migracoes_atuais()
        super().tearDown()

    def test_migracao_preserva_dados_e_nao_cria_historico_retroativo(self):
        anterior = ('helpdesk', '0026_respostas_prontas')
        executor = MigrationExecutor(connection)
        executor.migrate([anterior])
        apps = executor.loader.project_state([anterior]).apps
        Usuario = apps.get_model('auth', 'User')
        Ticket = apps.get_model('helpdesk', 'Chamado')
        usuario = Usuario.objects.create(username='legado-espera')
        equipe, _ = apps.get_model('helpdesk', 'Equipe').objects.get_or_create(
            triagem_padrao=True, defaults={'nome': 'Triagem da migração de espera', 'ativa': True})
        t = Ticket.objects.create(titulo='Chamado legado', descricao='Preservar', solicitante=usuario,
            equipe=equipe, status='Resolvido', data_vencimento=timezone.now(), data_fechamento=timezone.now())
        antes = Ticket.objects.filter(pk=t.pk).values().get()
        Aviso = apps.get_model('helpdesk', 'Notificacao')
        n = Aviso.objects.create(destinatario=usuario, chamado=t, tipo='resposta', evento='legado', lida_em=timezone.now())
        aviso = Aviso.objects.filter(pk=n.pk).values().get()
        executor = MigrationExecutor(connection)
        executor.migrate([('helpdesk', '0027_estados_espera')])
        self.assertEqual(Chamado.objects.filter(pk=t.pk).values(*antes).get(), antes)
        self.assertEqual(Notificacao.objects.filter(pk=n.pk).values().get(), aviso)
        self.assertFalse(HistoricoStatus.objects.exists())
        ticket = Chamado.objects.get(pk=t.pk)
        self.assertEqual(ticket.versao_status, 0)
        self.assertIsNone(ticket.espera_desde)
        self.assertEqual(ticket.motivo_espera, '')
