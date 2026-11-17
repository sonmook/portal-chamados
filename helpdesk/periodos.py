"""Intervalos de datas compartilhados pelos painéis, no fuso ativo do portal."""
from datetime import datetime, time, timedelta

from django.utils import timezone


def datas_periodo(periodo, *, hoje, inicio=None, fim=None):
    if periodo == 'hoje':
        return hoje, hoje
    if periodo == '7dias':
        return hoje - timedelta(days=6), hoje
    if periodo == 'mes':
        return hoje.replace(day=1), hoje
    if periodo == 'personalizado':
        return inicio, fim
    return None, None


def limites_datas(inicio, fim):
    """Inclui os dois dias sem incluir a meia-noite do dia seguinte."""
    return (
        timezone.make_aware(datetime.combine(inicio, time.min)),
        timezone.make_aware(datetime.combine(fim + timedelta(days=1), time.min)),
    )
