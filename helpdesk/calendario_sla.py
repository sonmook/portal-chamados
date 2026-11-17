"""Contagem de horas de atendimento no calendário e fuso da instalação."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone as utc, tzinfo
import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone


@dataclass(frozen=True)
class CalendarioSLA:
    inicio: int
    fim: int
    dias: frozenset[int]
    feriados: frozenset[date]
    fuso: tzinfo


def _minutos(valor, *, permitir_24=False):
    if permitir_24 and valor == '24:00':
        return 1440
    if not isinstance(valor, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', valor):
        raise ValueError('horários devem usar HH:MM; 24:00 é permitido somente no fim')
    hora, minuto = map(int, valor.split(':'))
    return hora * 60 + minuto


def obter_calendario():
    try:
        configuracao = settings.SLA_CALENDARIO
        inicio = _minutos(configuracao['inicio'])
        fim = _minutos(configuracao['fim'], permitir_24=True)
        if inicio >= fim:
            raise ValueError('o início deve ser anterior ao fim do expediente')
        valores = configuracao['dias']
        if not isinstance(valores, (list, tuple)) or not valores:
            raise ValueError('informe ao menos um dia da semana entre 0 e 6')
        if any(str(d) not in tuple('0123456') for d in valores):
            raise ValueError('dias da semana devem estar entre 0 (segunda) e 6 (domingo)')
        dias = frozenset(int(d) for d in valores)
        if len(dias) != len(valores):
            raise ValueError('dias da semana não podem se repetir')
        valores = configuracao['feriados']
        if not isinstance(valores, (list, tuple)):
            raise ValueError('feriados devem ser uma lista de datas YYYY-MM-DD')
        feriados = set()
        for valor in valores:
            dia = date.fromisoformat(valor)
            if dia.isoformat() != valor:
                raise ValueError('feriados devem usar YYYY-MM-DD')
            feriados.add(dia)
        fuso = timezone.get_default_timezone()
    except (KeyError, TypeError, ValueError) as erro:
        raise ImproperlyConfigured(f'Calendário de SLA inválido: {erro}.') from erro
    return CalendarioSLA(inicio, fim, dias, frozenset(feriados), fuso)


def _instante(dia, minutos, fuso):
    local = datetime.combine(dia, time.min) + timedelta(minutes=minutos)
    return timezone.make_aware(local, fuso).astimezone(utc.utc)


def calcular_vencimento(data_inicial, horas_prazo):
    if timezone.is_naive(data_inicial):
        raise ValueError('O cálculo de SLA exige uma data com fuso horário.')
    try:
        restante = timedelta(hours=horas_prazo)
    except (TypeError, ValueError, OverflowError) as erro:
        raise ValueError('Informe uma quantidade válida de horas para o SLA.') from erro
    if restante < timedelta(0):
        raise ValueError('As horas de SLA não podem ser negativas.')
    calendario = obter_calendario()
    cursor = data_inicial.astimezone(utc.utc)
    while restante > timedelta(0):
        dia = cursor.astimezone(calendario.fuso).date()
        if dia.weekday() in calendario.dias and dia not in calendario.feriados:
            abertura = _instante(dia, calendario.inicio, calendario.fuso)
            fechamento = _instante(dia, calendario.fim, calendario.fuso)
            cursor = max(cursor, abertura)
            if cursor < fechamento:
                disponivel = fechamento - cursor
                if restante <= disponivel:
                    return cursor + restante
                restante -= disponivel
        cursor = _instante(dia + timedelta(days=1), 0, calendario.fuso)
    return cursor
