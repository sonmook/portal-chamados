from datetime import datetime, timedelta, timezone as utc
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.core.checks import run_checks
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from .calendario_sla import calcular_vencimento
from .models import Chamado, calcular_prazo_util, somar_horas_uteis


PADRAO = {'inicio': '00:00', 'fim': '24:00', 'dias': [0, 1, 2, 3, 4], 'feriados': []}
COMERCIAL = {**PADRAO, 'inicio': '08:00', 'fim': '18:00'}


@override_settings(TIME_ZONE='America/Sao_Paulo', SLA_CALENDARIO=PADRAO)
class CalendarioSLATests(SimpleTestCase):
    def local(self, ano, mes, dia, hora=0, minuto=0, segundo=0):
        return datetime(ano, mes, dia, hora, minuto, segundo, tzinfo=ZoneInfo('America/Sao_Paulo'))

    def test_sexta_a_noite_nao_vence_no_domingo_por_usar_utc(self):
        inicio = self.local(2026, 11, 13, 18)
        esperado = self.local(2026, 11, 13, 22)
        self.assertEqual(calcular_vencimento(inicio.astimezone(utc.utc), 4), esperado)

    def test_mesmo_instante_em_fusos_diferentes_produz_mesmo_prazo(self):
        inicio = self.local(2026, 11, 13, 23, 30)
        esperado = self.local(2026, 11, 16, 3, 30)
        for fuso in (utc.utc, ZoneInfo('America/Sao_Paulo'), ZoneInfo('Asia/Tokyo')):
            self.assertEqual(calcular_vencimento(inicio.astimezone(fuso), 4), esperado)

    def test_abertura_no_fim_de_semana_inicia_na_segunda(self):
        for dia in (14, 15):
            self.assertEqual(calcular_vencimento(self.local(2026, 11, dia, 12), 4),
                self.local(2026, 11, 16, 4))

    @override_settings(SLA_CALENDARIO=COMERCIAL)
    def test_soma_somente_o_expediente_preservando_minutos_e_segundos(self):
        inicio = self.local(2026, 11, 13, 17, 30, 20)
        self.assertEqual(calcular_vencimento(inicio, 4), self.local(2026, 11, 16, 11, 30, 20))

    @override_settings(SLA_CALENDARIO=COMERCIAL)
    def test_abertura_antes_ou_depois_do_expediente(self):
        self.assertEqual(calcular_vencimento(self.local(2026, 11, 16, 6), 4), self.local(2026, 11, 16, 12))
        self.assertEqual(calcular_vencimento(self.local(2026, 11, 16, 20), 4), self.local(2026, 11, 17, 12))

    @override_settings(SLA_CALENDARIO=COMERCIAL)
    def test_fechamento_exato_e_fim_inclusivo_sem_adicionar_outro_dia(self):
        self.assertEqual(calcular_vencimento(self.local(2026, 11, 13, 14), 4), self.local(2026, 11, 13, 18))
        self.assertEqual(calcular_vencimento(self.local(2026, 11, 13, 18), 4), self.local(2026, 11, 16, 12))

    @override_settings(SLA_CALENDARIO={**COMERCIAL, 'feriados': ['2026-11-16', '2026-11-17']})
    def test_feriados_configurados_sao_pulados(self):
        self.assertEqual(calcular_vencimento(self.local(2026, 11, 13, 17), 4), self.local(2026, 11, 18, 11))

    @override_settings(SLA_CALENDARIO={**PADRAO, 'dias': [0, 1, 2, 3, 4, 5, 6]})
    def test_calendario_24_por_7_e_configuravel(self):
        self.assertEqual(calcular_vencimento(self.local(2026, 11, 13, 23), 4), self.local(2026, 11, 14, 3))

    @override_settings(SLA_CALENDARIO=COMERCIAL)
    def test_prazo_longo_atravessa_varios_fins_de_semana(self):
        # Doze expedientes de 10 horas: segunda 16 até terça 01/12 às 18h.
        self.assertEqual(calcular_vencimento(self.local(2026, 11, 16, 8), 120), self.local(2026, 12, 1, 18))

    @override_settings(TIME_ZONE='America/New_York', SLA_CALENDARIO={**PADRAO, 'dias': [6]})
    def test_horas_reais_em_transicao_de_horario_de_verao(self):
        fuso = ZoneInfo('America/New_York')
        inicio = datetime(2026, 3, 8, 0, tzinfo=fuso)
        resultado = calcular_vencimento(inicio, 4)
        self.assertEqual(resultado.astimezone(fuso).hour, 5)
        self.assertEqual(resultado - inicio.astimezone(utc.utc), timedelta(hours=4))

    def test_zero_horas_nao_desloca_abertura_e_horas_fracionadas_sao_exatas(self):
        inicio = self.local(2026, 11, 14, 12)
        self.assertEqual(calcular_vencimento(inicio, 0), inicio)
        self.assertEqual(calcular_vencimento(self.local(2026, 11, 16, 9), 0.5), self.local(2026, 11, 16, 9, 30))

    def test_datas_sem_fuso_e_horas_invalidas_sao_rejeitadas(self):
        with self.assertRaises(ValueError):
            calcular_vencimento(datetime(2026, 11, 16), 4)
        for horas in (-1, float('inf'), float('nan'), 'quatro'):
            with self.subTest(horas=horas), self.assertRaises(ValueError):
                calcular_vencimento(self.local(2026, 11, 16), horas)

    def test_funcoes_publicas_usam_o_mesmo_calendario(self):
        inicio = self.local(2026, 11, 13, 23)
        esperado = self.local(2026, 11, 16, 3)
        self.assertEqual(calcular_prazo_util(inicio, 4), esperado)
        self.assertEqual(somar_horas_uteis(inicio, 4), esperado)

    def test_calendarios_invalidos_falham_no_check_sem_calcular_prazo(self):
        for campo, valor in (('inicio', '24:00'), ('inicio', '8:00'), ('fim', '25:00'),
                ('fim', '00:00'), ('dias', []), ('dias', [7]), ('dias', [0, 0]),
                ('feriados', ['2026-02-30']), ('feriados', ['20261120']), ('feriados', '2026-11-20')):
            with self.subTest(campo=campo, valor=valor), override_settings(SLA_CALENDARIO={**PADRAO, campo: valor}):
                self.assertIn('helpdesk.E001', {erro.id for erro in run_checks(tags=['compatibility'])})
                with self.assertRaises(ImproperlyConfigured):
                    calcular_vencimento(self.local(2026, 11, 16), 4)


@override_settings(TIME_ZONE='America/Sao_Paulo', SLA_CALENDARIO=COMERCIAL)
class PersistenciaSLATests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user('cliente-calendario')

    def test_novo_chamado_usa_prioridade_e_calendario_configurado(self):
        inicio = datetime(2026, 11, 13, 17, tzinfo=ZoneInfo('America/Sao_Paulo'))
        with patch('django.utils.timezone.now', return_value=inicio.astimezone(utc.utc)):
            chamado = Chamado.objects.create(titulo='Incidente crítico', descricao='Fixture',
                prioridade='Crítica', solicitante=self.usuario)
        chamado.refresh_from_db()
        self.assertEqual(chamado.data_vencimento,
            datetime(2026, 11, 16, 11, tzinfo=ZoneInfo('America/Sao_Paulo')))

    def test_editar_chamado_existente_nao_recalcula_prazo_ao_alterar_calendario(self):
        prazo = timezone.now() + timedelta(hours=2)
        chamado = Chamado.objects.create(titulo='Prazo já combinado', descricao='Fixture',
            data_vencimento=prazo, solicitante=self.usuario)
        with override_settings(SLA_CALENDARIO={**COMERCIAL, 'feriados': ['2026-11-16']}):
            chamado.prioridade = 'Crítica'
            chamado.titulo = 'Título atualizado'
            chamado.save()
        chamado.refresh_from_db()
        self.assertEqual(chamado.data_vencimento, prazo)
