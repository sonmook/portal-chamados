from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Chamado


def validar_pendencias(pk, ativo, staff):
    if pk and not (ativo and staff) and Chamado.objects.filter(tecnico_id=pk).exclude(
        status__in=('Resolvido', 'Fechado')
    ).exists():
        raise ValidationError('Redistribua os chamados pendentes antes de desativar ou retirar o acesso de técnico.')


def bloquear_administradores():
    # Chamado dentro de uma transação antes de alterações administrativas.
    list(User.objects.select_for_update().filter(
        is_active=True, is_staff=True, is_superuser=True,
    ).order_by('pk'))


def validar_administrador(pk, ativo, staff, superuser):
    era_admin = User.objects.filter(pk=pk, is_active=True, is_staff=True, is_superuser=True).exists()
    if era_admin and not (ativo and staff and superuser):
        if not User.objects.filter(is_active=True, is_staff=True, is_superuser=True).exclude(pk=pk).exists():
            raise ValidationError("É necessário manter pelo menos um administrador ativo.")
