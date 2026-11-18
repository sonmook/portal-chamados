from .test_helpers import dados_situacao
from datetime import datetime, timedelta, timezone as utc
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Chamado, Equipe, IntegranteEquipe, Notificacao, RegistroAuditoria, ResolucaoConquista


class BuscaCategoriaTests(TestCase):
    def setUp(self):
        self.solicitante = User.objects.create_user('solicitante-busca')
        self.outro = User.objects.create_user('outro-solicitante-busca')
        self.tecnico = User.objects.create_user('tecnico-busca', is_staff=True)
        self.equipe = Equipe.objects.get(triagem_padrao=True)
        self.outra_equipe = Equipe.objects.get(nome='Infraestrutura e Redes')
        IntegranteEquipe.objects.create(equipe=self.equipe, usuario=self.tecnico)
        self.chamado = Chamado.objects.create(pk=424242, titulo='Impressora indisponível',
            descricao='Erro de comunicação', categoria='Hardware', solicitante=self.solicitante,
            equipe=self.equipe, tecnico=self.tecnico)
        self.url = reverse('lista_chamados')
        self.client.force_login(self.solicitante)

    def resultados(self, **filtros):
        return {c.pk for c in self.client.get(self.url, filtros).context['page_obj']}

    def test_busca_numero_com_e_sem_cerquilha_e_espacos(self):
        for termo in ('424242', '#424242', '  #424242  '):
            with self.subTest(termo=termo):
                self.assertEqual(self.resultados(q=termo), {self.chamado.pk})

    def test_numero_nao_amplia_acesso_de_solicitante_ou_tecnico(self):
        privado = Chamado.objects.create(pk=424243, titulo='Privado', descricao='Detalhes',
            solicitante=self.outro, equipe=self.outra_equipe)
        for usuario in (self.solicitante, self.tecnico):
            self.client.force_login(usuario)
            self.assertEqual(self.resultados(q=f'#{privado.pk}'), set())
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {'q': '#424242'}).status_code, 302)

    def test_numero_respeita_status_categoria_equipe_e_fila(self):
        self.client.force_login(self.tecnico)
        filtros = {'q': '#424242', 'categoria': 'Hardware', 'status': 'Aberto',
            'equipe': self.equipe.pk, 'fila': 'minha'}
        self.assertEqual(self.resultados(**filtros), {self.chamado.pk})
        for chave, valor in (('categoria', 'Rede'), ('status', 'Resolvido'), ('equipe', self.outra_equipe.pk)):
            self.assertEqual(self.resultados(**{**filtros, chave: valor}), set())

    def test_busca_textual_preservada_inclusive_termo_numerico(self):
        outro = Chamado.objects.create(titulo='Erro 424242 no PDV', descricao='Rede & acesso',
            solicitante=self.solicitante, equipe=self.equipe)
        self.assertEqual(self.resultados(q='424242'), {self.chamado.pk, outro.pk})
        self.assertEqual(self.resultados(q='Rede & acesso'), {outro.pk})
        self.assertEqual(self.resultados(q='comunicação'), {self.chamado.pk})

    def test_numeros_invalidos_ou_extensos_nao_causam_erro(self):
        for termo in ('#', '#0', '#-1', '#9223372036854775808', '#' + '9' * 5000, '１２３'):
            with self.subTest(termo=termo[:30]):
                self.assertEqual(self.resultados(q=termo), set())

    def test_categoria_visivel_e_selecionada_sem_precisar_de_outros_filtros(self):
        resposta = self.client.get(self.url, {'categoria': 'Hardware'})
        self.assertContains(resposta, '<select name="categoria"')
        self.assertContains(resposta, 'value="Hardware" selected')
        self.assertContains(resposta, 'Hardware/Periféricos')
        self.assertContains(resposta, 'Filtros aplicados:')
        self.assertContains(resposta, 'Categoria:')
        self.assertEqual({c.pk for c in resposta.context['page_obj']}, {self.chamado.pk})


@override_settings(TIME_ZONE='America/Sao_Paulo')
class PeriodosCompartilhadosTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin-periodos', is_staff=True, is_superuser=True)
        self.client.force_login(self.admin)

    def chamado_em(self, instante):
        chamado = Chamado.objects.create(titulo='Limite de período', descricao='Fixture', solicitante=self.admin)
        Chamado.objects.filter(pk=chamado.pk).update(data_criacao=timezone.make_aware(instante))
        return chamado

    def comparar(self, periodo, esperado):
        dashboard = self.client.get(reverse('dashboard'), {'periodo': periodo}).context
        relatorio = self.client.get(reverse('indicadores_administracao'), {'periodo': periodo}).context
        self.assertEqual(dashboard['total'], esperado)
        self.assertEqual(relatorio['resumo']['criados'], esperado)

    def test_sete_dias_incluem_hoje_e_seis_anteriores_com_mesmos_limites(self):
        hoje = datetime(2026, 11, 17)
        for instante in (hoje - timedelta(days=7), hoje - timedelta(days=6),
                hoje + timedelta(hours=23, minutes=59, seconds=59), hoje + timedelta(days=1)):
            self.chamado_em(instante)
        with patch('django.utils.timezone.now', return_value=timezone.make_aware(hoje.replace(hour=12))):
            self.comparar('7dias', 2)
            self.comparar('hoje', 1)

    def test_data_local_e_usada_perto_da_virada_em_utc(self):
        # Em UTC já é dia 17; em São Paulo ainda é dia 16.
        self.chamado_em(datetime(2026, 11, 16, 22))
        self.chamado_em(datetime(2026, 11, 17))
        with patch('django.utils.timezone.now', return_value=datetime(2026, 11, 17, 1, 30, tzinfo=utc.utc)):
            self.comparar('hoje', 1)
            self.comparar('7dias', 1)

    def test_mes_exclui_dia_anterior_e_dias_posteriores_a_hoje(self):
        for instante in (datetime(2026, 10, 31, 23, 59), datetime(2026, 11, 1),
                datetime(2026, 11, 17, 23, 59), datetime(2026, 11, 18)):
            self.chamado_em(instante)
        with patch('django.utils.timezone.now', return_value=timezone.make_aware(datetime(2026, 11, 17, 12))):
            self.comparar('mes', 2)
            self.comparar('sempre', 4)

    def test_sete_dias_atravessam_ano_sem_incluir_oitava_data(self):
        for instante in (datetime(2025, 12, 25, 23, 59), datetime(2025, 12, 26),
                datetime(2026, 1, 1, 23, 59), datetime(2026, 1, 2)):
            self.chamado_em(instante)
        with patch('django.utils.timezone.now', return_value=timezone.make_aware(datetime(2026, 1, 1, 12))):
            self.comparar('7dias', 2)


class ErrosResolucaoTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        configuracao = override_settings(MEDIA_ROOT=media.name)
        configuracao.enable()
        self.addCleanup(configuracao.disable)
        self.solicitante = User.objects.create_user('solicitante-resolucao')
        self.tecnico = User.objects.create_user('tecnico-resolucao', is_staff=True)
        self.outro = User.objects.create_user('outro-resolucao', is_staff=True)
        equipe = Equipe.objects.get(triagem_padrao=True)
        IntegranteEquipe.objects.create(equipe=equipe, usuario=self.tecnico)
        IntegranteEquipe.objects.create(equipe=equipe, usuario=self.outro)
        self.chamado = Chamado.objects.create(titulo='Chamado com solução', descricao='Fixture',
            solicitante=self.solicitante, tecnico=self.tecnico, equipe=equipe)
        self.url = reverse('fechar_chamado', args=[self.chamado.pk])
        self.client.force_login(self.tecnico)

    def test_anexo_invalido_preserva_texto_e_reabre_formulario_sem_gravacao(self):
        texto = 'Reiniciei o serviço. <script>alert("teste")</script>'
        auditoria = RegistroAuditoria.objects.count()
        resposta = self.client.post(self.url, {**dados_situacao(self.chamado), 'resolucao': texto,
            'anexo_resolucao': SimpleUploadedFile('erro.pdf', b'<html>arquivo invalido</html>')})
        self.assertEqual(resposta.status_code, 400)
        self.assertTemplateUsed(resposta, 'helpdesk/detalhes_chamado.html')
        self.assertContains(resposta, 'data-resolucao-invalida', status_code=400)
        self.assertContains(resposta, 'Seu texto foi mantido.', status_code=400)
        self.assertContains(resposta, '&lt;script&gt;', status_code=400)
        self.assertNotContains(resposta, '<script>alert(', status_code=400)
        self.assertEqual(resposta.context['resolucao_form']['resolucao'].value(), texto)
        self.assertIn('anexo_resolucao', resposta.context['resolucao_form'].errors)
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.status, 'Aberto')
        self.assertIsNone(self.chamado.data_fechamento)
        self.assertFalse(self.chamado.comentarios.exists())
        self.assertFalse(Notificacao.objects.exists())
        self.assertFalse(ResolucaoConquista.objects.exists())
        self.assertEqual(RegistroAuditoria.objects.count(), auditoria)

    def test_solucao_vazia_mostra_erro_no_campo(self):
        resposta = self.client.post(self.url, {**dados_situacao(self.chamado), 'resolucao': '   '})
        self.assertContains(resposta, 'id_resolucao_error', status_code=400)
        self.assertContains(resposta, 'aria-invalid="true"', status_code=400)
        self.assertTrue(resposta.context['abrir_resolucao'])
        self.assertIn('resolucao', resposta.context['resolucao_form'].errors)

    def test_reenvio_corrigido_resolve_uma_unica_vez(self):
        self.client.post(self.url, {**dados_situacao(self.chamado), 'resolucao': ''})
        resposta = self.client.post(self.url, {**dados_situacao(self.chamado), 'resolucao': 'Serviço reiniciado e validado',
            'anexo_resolucao': SimpleUploadedFile('solucao.pdf', b'%PDF-1.4\nconteudo')})
        self.assertRedirects(resposta, reverse('detalhes_chamado', args=[self.chamado.pk]))
        self.chamado.refresh_from_db()
        self.assertEqual(self.chamado.status, 'Resolvido')
        self.assertEqual(self.chamado.fechado_por, self.tecnico)
        self.assertEqual(self.chamado.comentarios.count(), 1)
        self.assertEqual(ResolucaoConquista.objects.filter(chamado=self.chamado).count(), 1)

    def test_formulario_so_e_exibido_ao_responsavel(self):
        detalhes = reverse('detalhes_chamado', args=[self.chamado.pk])
        for usuario in (self.solicitante, self.outro):
            self.client.force_login(usuario)
            self.assertNotContains(self.client.get(detalhes), 'id="modalResolucao"')
            self.assertEqual(self.client.post(self.url, {**dados_situacao(self.chamado), 'resolucao': ''}).status_code, 403)
