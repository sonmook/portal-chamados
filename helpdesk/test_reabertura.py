from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib import admin
from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.db.models.query import QuerySet
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .atendimento import registrar_ciclo_concluido
from .models import (Chamado, CicloAtendimento, Comentario, Conquista, Equipe,
    HistoricoStatus, IntegranteEquipe, Notificacao, RegistroAuditoria, ResolucaoConquista)
from .notificacoes import notificar_reabertura, notificar_resolucao
from .sla import processar_alertas_sla
from .test_helpers import dados_situacao, dados_atribuicao, restaurar_migracoes_atuais


class ReaberturaTests(TestCase):
    def setUp(self):
        self.cliente = User.objects.create_user('cliente-reabertura')
        self.alheio = User.objects.create_user('alheio-reabertura')
        self.tecnico = User.objects.create_user('tecnico-reabertura', is_staff=True)
        self.outro = User.objects.create_user('outro-reabertura', is_staff=True)
        self.coord = User.objects.create_user('coord-reabertura', is_staff=True)
        self.admin = User.objects.create_superuser('admin-reabertura', password=None)
        self.equipe = Equipe.objects.get(triagem_padrao=True)
        for usuario in (self.tecnico, self.outro, self.coord):
            IntegranteEquipe.objects.create(equipe=self.equipe, usuario=usuario, coordenador=usuario == self.coord)
        self.ticket = Chamado.objects.create(titulo='Problema reincidente', descricao='Fixture',
            solicitante=self.cliente, tecnico=self.tecnico, equipe=self.equipe,
            data_vencimento=timezone.now() + timedelta(hours=4))
        self.detalhes = reverse('detalhes_chamado', args=[self.ticket.pk])
        self.reabrir_url = reverse('reabrir_chamado', args=[self.ticket.pk])
        self.fechar_url = reverse('fechar_chamado', args=[self.ticket.pk])
        self.client.force_login(self.tecnico)
        self.assertEqual(self.fechar().status_code, 302)
        self.ticket.refresh_from_db()

    def fechar(self, **extra):
        return self.client.post(self.fechar_url, {'resolucao': 'Serviço corrigido e validado.',
            **dados_situacao(self.ticket), **extra})

    def reabrir(self, **extra):
        return self.client.post(self.reabrir_url, {'motivo_reabertura': 'O problema voltou após a validação.',
            **dados_situacao(self.ticket), **extra})

    def test_preserva_resultado_solucao_e_abertura_original(self):
        original = CicloAtendimento.objects.get(chamado=self.ticket)
        valores = CicloAtendimento.objects.filter(pk=original.pk).values().get()
        comentarios = list(self.ticket.comentarios.values())
        abertura, prazo = self.ticket.data_criacao, self.ticket.data_vencimento
        self.client.force_login(self.cliente)
        self.assertEqual(self.reabrir().status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.ciclo_atual, 2)
        self.assertEqual(self.ticket.status, 'Em Andamento')
        self.assertEqual(self.ticket.tecnico, self.tecnico)
        self.assertEqual(self.ticket.data_criacao, abertura)
        self.assertEqual(self.ticket.inicio_ciclo, self.ticket.ciclo_iniciado_em)
        self.assertGreater(self.ticket.data_vencimento, prazo)
        self.assertIsNone(self.ticket.data_fechamento)
        self.assertIsNone(self.ticket.fechado_por)
        self.assertIsNone(self.ticket.espera_desde)
        self.assertEqual(self.ticket.motivo_espera, '')
        self.assertEqual(list(self.ticket.comentarios.values()), comentarios)
        self.assertEqual(CicloAtendimento.objects.filter(pk=original.pk).values().get(), valores)
        evento = self.ticket.historico_status.first()
        self.assertEqual((evento.autor, evento.status_anterior, evento.status_novo),
            (self.cliente, 'Resolvido', 'Em Andamento'))
        self.assertEqual(evento.motivo, 'O problema voltou após a validação.')
        self.assertEqual(evento.criado_em, self.ticket.ciclo_iniciado_em)
        self.assertEqual(self.ticket.ultima_interacao_em, evento.criado_em)

    @override_settings(SLA_CALENDARIO={'inicio': '09:00', 'fim': '18:00', 'dias': [0, 1, 2, 3, 4], 'feriados': []})
    def test_novo_prazo_respeita_prioridade_calendario_e_fim_de_semana(self):
        fuso = ZoneInfo('America/Sao_Paulo')
        sexta = datetime(2026, 11, 20, 17, tzinfo=fuso)
        Chamado.objects.filter(pk=self.ticket.pk).update(prioridade='Crítica')
        self.client.force_login(self.cliente)
        with patch('helpdesk.atendimento.timezone.now', return_value=sexta):
            self.assertEqual(self.reabrir().status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.data_vencimento, datetime(2026, 11, 23, 12, tzinfo=fuso))
        self.assertEqual(self.ticket.ciclos_concluidos.get().prioridade, 'Normal')

    def test_tecnico_responsavel_tambem_pode_reabrir(self):
        self.assertEqual(self.reabrir().status_code, 302)
        aviso = Notificacao.objects.get(tipo='reabertura')
        self.assertEqual(aviso.destinatario, self.cliente)
        self.assertFalse(Notificacao.objects.filter(tipo='reabertura', destinatario=self.tecnico).exists())

    def test_coordenador_outro_tecnico_e_admin_nao_reabrem_por_acesso_global(self):
        for usuario in (self.outro, self.coord, self.admin):
            self.client.force_login(usuario)
            self.assertEqual(self.reabrir().status_code, 403)
        self.client.force_login(self.alheio)
        self.assertEqual(self.reabrir().status_code, 404)
        self.assertEqual(self.client.get(self.detalhes).status_code, 404)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.ciclo_atual, 1)

    def test_servico_revalida_ator_desativado_apos_carregar_sessao(self):
        from django.core.exceptions import PermissionDenied
        from .atendimento import reabrir_atendimento
        antigo = dados_situacao(self.ticket)
        User.objects.filter(pk=self.tecnico.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            reabrir_atendimento(self.ticket, self.tecnico, 'Retorno',
                versao_esperada=antigo['versao_status'], atribuicao_esperada=antigo['versao_atribuicao'])
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'Resolvido')

    def test_auditoria_filtra_reabertura_sem_expor_motivo(self):
        self.reabrir(motivo_reabertura='Texto visível somente no histórico do chamado.')
        self.client.force_login(self.admin)
        r = self.client.get(reverse('listar_auditoria'), {'acao': 'reaberto', 'objeto': 'helpdesk.chamado'})
        self.assertEqual(r.context['page_obj'].paginator.count, 1)
        self.assertContains(r, 'Reabertura')
        self.assertNotContains(r, 'Texto visível somente')

    def test_tecnico_sem_vinculo_perde_acesso_e_reabertura(self):
        IntegranteEquipe.objects.filter(usuario=self.tecnico).delete()
        self.assertEqual(self.reabrir().status_code, 404)

    def test_login_post_e_csrf_obrigatorios(self):
        self.assertEqual(self.client.get(self.reabrir_url).status_code, 405)
        seguro = Client(enforce_csrf_checks=True)
        seguro.force_login(self.cliente)
        self.assertEqual(seguro.post(self.reabrir_url, {'motivo_reabertura': 'Retorno',
            **dados_situacao(self.ticket)}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.reabrir().status_code, 302)
        self.assertFalse(Notificacao.objects.filter(tipo='reabertura').exists())

    def test_motivo_obrigatorio_limitado_e_texto_invalido_preservado(self):
        self.client.force_login(self.cliente)
        antes = RegistroAuditoria.objects.count()
        for motivo in ('', ' \n ', 'x' * 501):
            r = self.reabrir(motivo_reabertura=motivo)
            self.assertEqual(r.status_code, 400)
            self.assertIn('motivo_reabertura', r.context['reabertura_form'].errors)
            self.assertEqual(r.context['reabertura_form']['motivo_reabertura'].value(), motivo)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
        self.assertEqual(HistoricoStatus.objects.filter(chamado=self.ticket).count(), 1)

    def test_versoes_obrigatorias_e_tela_antiga_rejeitada(self):
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.post(self.reabrir_url, {'motivo_reabertura': 'Retorno'}).status_code, 400)
        for campo in ('versao_status', 'versao_atribuicao'):
            r = self.reabrir(**{campo: 999})
            self.assertEqual(r.status_code, 409)
            self.assertContains(r, 'Carregar os dados atuais', status_code=409)
        self.assertFalse(Notificacao.objects.filter(tipo='reabertura').exists())

    def test_duplo_envio_nao_cria_dois_ciclos(self):
        antigo = dados_situacao(self.ticket)
        self.assertEqual(self.reabrir(**antigo).status_code, 302)
        self.assertEqual(self.reabrir(**antigo).status_code, 403)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.ciclo_atual, 2)
        self.assertEqual(self.ticket.ciclos_concluidos.count(), 1)
        self.assertEqual(Notificacao.objects.filter(tipo='reabertura').count(), 1)

    def test_formulario_de_outra_reabertura_nao_pode_ser_reutilizado(self):
        antigo = dados_situacao(self.ticket)
        self.reabrir()
        self.fechar()
        self.assertEqual(self.reabrir(**antigo).status_code, 409)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.ciclo_atual, 2)

    def test_resolucao_antiga_nao_encerra_novo_ciclo(self):
        self.reabrir()
        antigo = dados_situacao(self.ticket)
        self.fechar()
        self.reabrir()
        self.assertEqual(self.fechar(**antigo).status_code, 409)
        self.assertEqual(self.client.post(self.fechar_url, {'resolucao': 'Solução sem versão'}).status_code, 400)
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.ciclo_atual), ('Em Andamento', 3))
        self.assertEqual(self.ticket.ciclos_concluidos.count(), 2)

    def test_atribuicao_antiga_tambem_e_invalidada(self):
        antigo = dados_atribuicao(self.ticket)
        self.reabrir()
        self.client.force_login(self.admin)
        r = self.client.post(reverse('redistribuir_chamado', args=[self.ticket.pk]), {
            **antigo, 'tecnico': self.outro.pk, 'responsavel_anterior': self.tecnico.pk, 'motivo': 'Tela antiga'})
        self.assertEqual(r.status_code, 409)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.tecnico, self.tecnico)

    def test_resp_inativo_sem_vinculo_ou_rebaixado_volta_para_fila(self):
        User.objects.filter(pk=self.tecnico.pk).update(is_active=False)
        self.client.force_login(self.cliente)
        self.assertEqual(self.reabrir().status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.tecnico_id), ('Aberto', None))
        self.assertEqual(self.ticket.equipe, self.equipe)
        self.assertTrue(Notificacao.objects.filter(tipo='reabertura', destinatario=self.coord).exists())

    def test_tecnico_removido_nao_e_reatribuido(self):
        IntegranteEquipe.objects.filter(usuario=self.tecnico).delete()
        self.client.force_login(self.cliente)
        self.reabrir()
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.tecnico_id)

    def test_tecnico_rebaixado_nao_e_reatribuido(self):
        User.objects.filter(pk=self.tecnico.pk).update(is_staff=False)
        self.client.force_login(self.cliente)
        self.reabrir()
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.tecnico_id)

    def test_equipe_inativa_retorna_para_triagem_ativa(self):
        antiga = Equipe.objects.create(nome='Equipe antiga encerrada', ativa=False)
        Chamado.objects.filter(pk=self.ticket.pk).update(equipe=antiga)
        self.client.force_login(self.cliente)
        self.assertEqual(self.reabrir().status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.equipe, self.equipe)
        # O técnico continua elegível na triagem, mas a equipe mudou com versão nova.
        self.assertEqual(self.ticket.tecnico, self.tecnico)
        self.assertEqual(self.ticket.ciclos_concluidos.get().equipe, self.equipe)

    def test_sem_responsavel_e_coordenacao_avisa_administradores(self):
        IntegranteEquipe.objects.filter(usuario=self.coord).update(coordenador=False)
        Chamado.objects.filter(pk=self.ticket.pk).update(tecnico=None)
        self.client.force_login(self.cliente)
        self.reabrir()
        self.assertTrue(Notificacao.objects.filter(tipo='reabertura', destinatario=self.admin).exists())
        self.assertFalse(Notificacao.objects.filter(tipo='reabertura', destinatario=self.outro).exists())

    def test_cas_concorrente_nao_cria_historico_ou_aviso(self):
        original = QuerySet.update
        def disputar(qs, **campos):
            return 0 if qs.model is Chamado and 'ciclo_atual' in campos else original(qs, **campos)
        antes = RegistroAuditoria.objects.count()
        with patch.object(QuerySet, 'update', disputar):
            self.assertEqual(self.reabrir().status_code, 409)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'Resolvido')
        self.assertEqual(self.ticket.historico_status.count(), 1)
        self.assertFalse(Notificacao.objects.filter(tipo='reabertura').exists())
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_falha_no_aviso_reverte_reabertura_historico_e_auditoria(self):
        antes = RegistroAuditoria.objects.count()
        with patch('helpdesk.notificacoes.notificar_reabertura', side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError):
                self.reabrir()
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.ciclo_atual), ('Resolvido', 1))
        self.assertEqual(self.ticket.historico_status.count(), 1)
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_nova_solucao_gera_aviso_proprio_e_preserva_leitura_antiga(self):
        aviso = Notificacao.objects.get(tipo='resolucao')
        Notificacao.objects.filter(pk=aviso.pk).update(lida_em=timezone.now())
        self.reabrir()
        self.assertEqual(self.fechar().status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.ciclos_concluidos.count(), 2)
        self.assertEqual(Notificacao.objects.filter(tipo='resolucao').count(), 2)
        self.assertEqual(Notificacao.objects.filter(tipo='resolucao', lida_em__isnull=True).count(), 1)
        notificar_resolucao(self.ticket, self.tecnico.pk)
        notificar_reabertura(self.ticket, self.tecnico.pk)
        self.assertEqual(Notificacao.objects.filter(tipo='resolucao').count(), 2)
        self.assertEqual(Notificacao.objects.filter(tipo='reabertura').count(), 1)

    def test_reabertura_nao_duplica_conquistas_ou_primeira_resolucao(self):
        antes = (Conquista.objects.count(), list(ResolucaoConquista.objects.values()))
        self.reabrir()
        self.fechar()
        self.assertEqual((Conquista.objects.count(), list(ResolucaoConquista.objects.values())), antes)

    def test_alertas_de_sla_tem_identidade_por_ciclo(self):
        self.reabrir()
        prazo = timezone.now() - timedelta(minutes=5)
        Chamado.objects.filter(pk=self.ticket.pk).update(data_vencimento=prazo)
        self.assertEqual(processar_alertas_sla()['sla_vencido'], 1)
        self.assertEqual(processar_alertas_sla()['sla_vencido'], 0)
        self.fechar()
        self.reabrir()
        Chamado.objects.filter(pk=self.ticket.pk).update(data_vencimento=prazo)
        self.assertEqual(processar_alertas_sla()['sla_vencido'], 1)
        self.assertEqual(Notificacao.objects.filter(tipo='sla_vencido').count(), 2)

    def test_esperas_continuam_disponiveis_no_novo_ciclo(self):
        self.reabrir()
        self.client.post(reverse('atualizar_status', args=[self.ticket.pk]), {
            **dados_situacao(self.ticket), 'status': 'Aguardando solicitante', 'motivo': 'Teste de retorno'})
        self.client.force_login(self.cliente)
        self.client.post(self.detalhes, {'texto': 'Retorno solicitado'})
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.ciclo_atual), ('Em Andamento', 2))
        self.assertEqual(self.ticket.ciclos_concluidos.count(), 1)

    def test_indicadores_preservam_primeira_resolucao_e_medem_tempo_por_ciclo(self):
        agora = timezone.now()
        ciclo = self.ticket.ciclos_concluidos.get()
        CicloAtendimento.objects.filter(pk=ciclo.pk).update(data_criacao=agora-timedelta(days=10, hours=2),
            data_fechamento=agora-timedelta(days=10), data_vencimento=agora-timedelta(days=9))
        self.reabrir()
        self.client.force_login(self.admin)
        r = self.client.get(reverse('indicadores_administracao'), {'periodo': 'sempre'})
        self.assertEqual((r.context['resumo']['resolvidos'], r.context['resumo']['ativos']), (1, 1))
        self.assertEqual(self.client.get(reverse('dashboard')).context['dados_sla'], [1, 0])
        self.ticket.refresh_from_db()
        fim = self.ticket.ciclo_iniciado_em + timedelta(hours=1)
        self.client.force_login(self.tecnico)
        with patch('django.utils.timezone.now', return_value=fim):
            self.fechar()
        self.client.force_login(self.admin)
        r = self.client.get(reverse('indicadores_administracao'), {'periodo': 'sempre'})
        self.assertEqual((r.context['resumo']['resolvidos'], r.context['resumo']['ativos']), (2, 0))
        self.assertEqual(r.context['resumo']['tmr_horas'], 1.5)
        self.assertEqual(r.context['analistas'][0]['total'], 2)
        self.assertEqual(r.context['pagina'].paginator.count, 2)
        self.assertContains(r, f'href="{self.detalhes}"')
        hoje = self.client.get(reverse('indicadores_administracao'), {'periodo': 'hoje'})
        self.assertEqual(hoje.context['resumo']['resolvidos'], 1)

    def test_mudar_equipe_nao_reescreve_desempenho_da_equipe_anterior(self):
        self.reabrir()
        destino = Equipe.objects.create(nome='Equipe do novo ciclo')
        IntegranteEquipe.objects.create(equipe=destino, usuario=self.outro)
        self.client.force_login(self.admin)
        r = self.client.post(reverse('redistribuir_chamado', args=[self.ticket.pk]), {
            **dados_atribuicao(self.ticket), 'equipe': destino.pk, 'tecnico': self.outro.pk,
            'responsavel_anterior': self.tecnico.pk, 'motivo': 'Análise especializada'})
        self.assertEqual(r.status_code, 302)
        self.client.force_login(self.outro)
        self.assertEqual(self.fechar().status_code, 302)
        self.client.force_login(self.admin)
        for equipe, tecnico in ((self.equipe, self.tecnico), (destino, self.outro)):
            r = self.client.get(reverse('indicadores_administracao'), {'periodo': 'sempre', 'equipe': equipe.pk})
            self.assertEqual(r.context['resumo']['resolvidos'], 1)
            self.assertEqual(r.context['analistas'][0]['nome'], tecnico.username)

    def test_admin_antigo_nao_reverte_numero_inicio_ou_prazo_do_novo_ciclo(self):
        antiga = Chamado.objects.get(pk=self.ticket.pk)
        self.reabrir()
        self.ticket.refresh_from_db()
        esperado = (self.ticket.ciclo_atual, self.ticket.ciclo_iniciado_em, self.ticket.data_vencimento)
        request = RequestFactory().post('/admin/')
        request.user = self.admin
        antiga.titulo = 'Título corrigido'
        admin.site._registry[Chamado].save_model(request, antiga, None, change=True)
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.ciclo_atual, self.ticket.ciclo_iniciado_em, self.ticket.data_vencimento), esperado)
        self.assertEqual(self.ticket.status, 'Em Andamento')

    def test_detalhe_mostra_ciclos_motivo_escapado_e_formulario_apenas_aos_autorizados(self):
        for usuario in (self.cliente, self.tecnico):
            self.client.force_login(usuario)
            self.assertContains(self.client.get(self.detalhes), 'Por que o chamado precisa ser reaberto?')
        self.client.force_login(self.outro)
        self.assertNotContains(self.client.get(self.detalhes), 'Por que o chamado precisa ser reaberto?')
        self.client.force_login(self.cliente)
        self.reabrir(motivo_reabertura='<script>alert("retorno")</script>')
        r = self.client.get(self.detalhes)
        self.assertContains(r, '&lt;script&gt;')
        self.assertNotContains(r, '<script>alert(')
        self.assertContains(r, 'Ciclos concluídos e resultados de SLA')
        self.assertNotIn('alert("retorno")', str(list(RegistroAuditoria.objects.values())))

    def test_ciclos_paginam_no_detalhe_canonico(self):
        for _ in range(10):
            self.reabrir()
            self.fechar()
        r = self.client.get(self.detalhes, {'ciclos_page': 2})
        self.assertEqual(len(r.context['ciclos_concluidos']), 1)
        self.assertEqual(r.context['ciclos_concluidos'][0].numero, 1)
        self.assertContains(r, f'href="{self.detalhes}?ciclos_page=1')
        self.assertContains(r, '<details class="card card-body mb-4" open>')

    def test_consultas_nao_criam_resultados_avisos_ou_auditoria(self):
        self.client.force_login(self.admin)
        antes = (CicloAtendimento.objects.count(), HistoricoStatus.objects.count(),
            Notificacao.objects.count(), RegistroAuditoria.objects.count())
        for url in (self.detalhes, reverse('dashboard'), reverse('indicadores_administracao')):
            self.client.get(url)
        self.assertEqual((CicloAtendimento.objects.count(), HistoricoStatus.objects.count(),
            Notificacao.objects.count(), RegistroAuditoria.objects.count()), antes)

    def test_legado_fechado_sem_snapshot_e_preservado_antes_de_reabrir(self):
        self.ticket.ciclos_concluidos.all().delete()
        Chamado.objects.filter(pk=self.ticket.pk).update(status='Fechado', data_fechamento=None, data_vencimento=None)
        self.client.force_login(self.cliente)
        self.assertEqual(self.reabrir().status_code, 302)
        ciclo = self.ticket.ciclos_concluidos.get()
        self.assertEqual(ciclo.status, 'Fechado')
        self.assertIsNone(ciclo.data_fechamento)
        self.assertIsNone(ciclo.data_vencimento)
        self.assertEqual(ciclo.resultado_sla, 'Sem dados de SLA')

    def test_resultados_sao_unicos_e_protegem_vinculo_do_chamado(self):
        self.assertEqual(registrar_ciclo_concluido(self.ticket).pk, self.ticket.ciclos_concluidos.get().pk)
        with self.assertRaises(ProtectedError):
            self.ticket.delete()
        campos = self.ticket.ciclos_concluidos.values().get()
        campos.pop('id')
        with self.assertRaises(IntegrityError), transaction.atomic():
            CicloAtendimento.objects.create(**campos)
        for numero in (0,):
            with self.assertRaises(IntegrityError), transaction.atomic():
                CicloAtendimento.objects.create(**(campos | {'numero': numero}))


class MigracaoCiclosTests(TransactionTestCase):
    def tearDown(self):
        restaurar_migracoes_atuais()
        super().tearDown()

    def test_migracao_preserva_legados_sem_reabrir_avisar_ou_recalcular_prazos(self):
        anterior = ('helpdesk', '0027_estados_espera')
        alvo = ('helpdesk', '0028_reabertura_ciclos')
        executor = MigrationExecutor(connection)
        executor.migrate([anterior])
        apps = executor.loader.project_state([anterior]).apps
        usuario = apps.get_model('auth', 'User').objects.create(username='legado-ciclos')
        equipe, _ = apps.get_model('helpdesk', 'Equipe').objects.get_or_create(triagem_padrao=True,
            defaults={'nome': 'Triagem legada', 'ativa': True})
        Ticket = apps.get_model('helpdesk', 'Chamado')
        agora = timezone.now()
        legados = [Ticket.objects.create(titulo=status, descricao='Preservar', status=status, equipe=equipe,
            solicitante=usuario, fechado_por=usuario, data_fechamento=agora if status == 'Resolvido' else None,
            data_vencimento=agora-timedelta(hours=1), espera_desde=agora if status.startswith('Aguardando') else None,
            motivo_espera='Aguardar' if status.startswith('Aguardando') else '')
            for status in ('Resolvido', 'Fechado', 'Aguardando fornecedor', 'Aberto')]
        antes = {t.pk: Ticket.objects.filter(pk=t.pk).values().get() for t in legados}
        executor = MigrationExecutor(connection)
        executor.migrate([alvo])
        self.assertEqual(CicloAtendimento.objects.count(), 2)
        for t in legados:
            atual = Chamado.objects.get(pk=t.pk)
            self.assertEqual(Chamado.objects.filter(pk=t.pk).values(*antes[t.pk]).get(), antes[t.pk])
            self.assertEqual(atual.ciclo_atual, 1)
            self.assertIsNone(atual.ciclo_iniciado_em)
            if t.status in ('Resolvido', 'Fechado'):
                ciclo = atual.ciclos_concluidos.get()
                self.assertEqual((ciclo.status, ciclo.data_fechamento, ciclo.data_vencimento),
                    (t.status, t.data_fechamento, t.data_vencimento))
                self.assertEqual((ciclo.data_criacao, ciclo.equipe_id, ciclo.fechado_por_id),
                    (t.data_criacao, equipe.pk, usuario.pk))
        self.assertFalse(Notificacao.objects.exists())
        self.assertFalse(HistoricoStatus.objects.exists())
        self.assertFalse(ResolucaoConquista.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.filter(acao='reaberto').exists())
