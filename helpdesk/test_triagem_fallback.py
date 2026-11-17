from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .acesso import chamados_acessiveis
from .models import Chamado, Equipe, IntegranteEquipe, Notificacao, RegistroAuditoria
from .sla import processar_alertas_sla


class TriagemFallbackTests(TestCase):
    def setUp(self):
        self.equipe = Equipe.objects.get(triagem_padrao=True)
        self.admin = User.objects.create_user('admin-fallback', is_staff=True, is_superuser=True)
        self.coordenador = User.objects.create_user('coord-fallback', is_staff=True)
        self.tecnico = User.objects.create_user('tecnico-fallback', is_staff=True)
        self.cliente = User.objects.create_user('cliente-fallback')
        IntegranteEquipe.objects.create(equipe=self.equipe, usuario=self.tecnico)
        self.agora = timezone.now()
        self.chamado = Chamado.objects.create(titulo='Fila aguardando atribuição', descricao='Fixture',
            solicitante=self.cliente, equipe=self.equipe, data_vencimento=self.agora + timedelta(minutes=30))

    def test_sem_coordenador_envia_falta_de_responsavel_e_prazo_ao_admin(self):
        resultado = processar_alertas_sla(self.agora)
        self.assertEqual(resultado['sem_responsavel'], 1)
        self.assertEqual(resultado['sla_proximo'], 1)
        self.assertEqual(resultado['sem_destinatario'], 0)
        self.assertEqual(set(Notificacao.objects.values_list('destinatario_id', 'tipo')),
            {(self.admin.pk, 'sem_responsavel'), (self.admin.pk, 'sla_proximo')})
        self.assertTrue(chamados_acessiveis(self.admin).filter(pk=self.chamado.pk).exists())

    def test_fallback_so_inclui_administradores_ativos_com_acesso_administrativo(self):
        User.objects.create_user('admin-inativo-fallback', is_staff=True, is_superuser=True, is_active=False)
        User.objects.create_user('super-sem-staff-fallback', is_superuser=True)
        outro = User.objects.create_user('outro-admin-fallback', is_staff=True, is_superuser=True)
        processar_alertas_sla(self.agora)
        self.assertEqual(set(Notificacao.objects.values_list('destinatario_id', flat=True)), {self.admin.pk, outro.pk})

    def test_coordenador_elegivel_tem_preferencia_e_fallback_nao_recebe(self):
        IntegranteEquipe.objects.create(equipe=self.equipe, usuario=self.coordenador, coordenador=True)
        processar_alertas_sla(self.agora)
        self.assertEqual(set(Notificacao.objects.values_list('destinatario_id', flat=True)), {self.coordenador.pk})

    def test_repeticao_e_leitura_nao_duplicam_avisos_do_fallback(self):
        processar_alertas_sla(self.agora)
        Notificacao.objects.update(lida_em=self.agora)
        resultado = processar_alertas_sla(self.agora)
        self.assertEqual(resultado['sem_responsavel'], 0)
        self.assertEqual(resultado['sla_proximo'], 0)
        self.assertEqual(Notificacao.objects.count(), 2)

    def test_novo_coordenador_recebe_avisos_sem_reenviar_ao_administrador(self):
        processar_alertas_sla(self.agora)
        IntegranteEquipe.objects.create(equipe=self.equipe, usuario=self.coordenador, coordenador=True)
        processar_alertas_sla(self.agora)
        self.assertEqual(Notificacao.objects.filter(destinatario=self.admin).count(), 2)
        self.assertEqual(Notificacao.objects.filter(destinatario=self.coordenador).count(), 2)

    def test_sem_admin_e_sem_coordenador_registra_ausencia_de_destinatario(self):
        User.objects.filter(pk=self.admin.pk).update(is_active=False)
        resultado = processar_alertas_sla(self.agora)
        self.assertEqual(resultado['sem_destinatario'], 1)
        self.assertFalse(Notificacao.objects.exists())
        saida = StringIO()
        call_command('processar_alertas_sla', stdout=saida)
        self.assertIn('chamados sem destinatário elegível: 1', saida.getvalue())

    def test_responsavel_valido_continua_recebendo_prazo_sem_fallback(self):
        Chamado.objects.filter(pk=self.chamado.pk).update(tecnico=self.tecnico)
        processar_alertas_sla(self.agora)
        self.assertEqual(set(Notificacao.objects.values_list('destinatario_id', 'tipo')),
            {(self.tecnico.pk, 'sla_proximo')})

    def test_avisos_de_cobertura_sao_administrativos_e_nao_gravam_em_get(self):
        for usuario in (self.cliente, self.tecnico):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse('central_administracao')).status_code, 403)
            self.assertEqual(self.client.get(reverse('gerenciar_equipes')).status_code, 403)
        self.client.force_login(self.admin)
        antes = RegistroAuditoria.objects.count()
        r = self.client.get(reverse('central_administracao'))
        self.assertGreater(r.context['total_sem_coordenacao'], 0)
        self.assertContains(r, 'Revisar cobertura de todas as equipes')
        r = self.client.get(reverse('gerenciar_equipes'))
        equipe = next(e for e in r.context['page_obj'] if e.pk == self.equipe.pk)
        self.assertTrue(equipe.tem_tecnico_ativo)
        self.assertFalse(equipe.tem_coordenador_ativo)
        self.assertContains(r, 'Sem coordenador ativo · avisos aos administradores')
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
        self.assertFalse(Notificacao.objects.exists())

    def test_cobertura_desconsidera_coordenador_inativo_e_equipe_desativada(self):
        IntegranteEquipe.objects.create(equipe=self.equipe, usuario=self.coordenador, coordenador=True)
        # Somente esta equipe permanece ativa na fixture.
        Equipe.objects.exclude(pk=self.equipe.pk).update(ativa=False)
        self.client.force_login(self.admin)
        url = reverse('central_administracao')
        self.assertEqual(self.client.get(url).context['total_sem_coordenacao'], 0)
        User.objects.filter(pk=self.coordenador.pk).update(is_active=False)
        self.assertEqual(self.client.get(url).context['total_sem_coordenacao'], 1)
        Equipe.objects.filter(pk=self.equipe.pk).update(ativa=False)
        self.assertEqual(self.client.get(url).context['total_sem_coordenacao'], 0)
