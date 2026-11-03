from django.db.models import Q

from .models import Chamado, Equipe, IntegranteEquipe


FINALIZADOS = ('Resolvido', 'Fechado')


def filtrar_equipe(chamados, valor):
    if not valor:
        return chamados
    try:
        pk = int(valor)
    except (ValueError, TypeError):
        return chamados.none()
    return chamados.filter(equipe_id=pk) if 0 < pk <= 9223372036854775807 else chamados.none()


def equipes_acessiveis(usuario):
    if not usuario.is_active:
        return Equipe.objects.none()
    if usuario.is_superuser:
        return Equipe.objects.all()
    if usuario.is_staff:
        return Equipe.objects.filter(ativa=True, vinculos__usuario_id=usuario.pk)
    return Equipe.objects.none()


def chamados_acessiveis(usuario):
    if not usuario.is_active:
        return Chamado.objects.none()
    if usuario.is_superuser:
        return Chamado.objects.all()
    visiveis = Q(solicitante_id=usuario.pk)
    if usuario.is_staff:
        visiveis |= Q(equipe_id__in=equipes_acessiveis(usuario).values('pk'))
    return Chamado.objects.filter(visiveis)


def integrante_ativo(usuario, equipe_id):
    return usuario.is_active and usuario.is_staff and IntegranteEquipe.objects.filter(
        usuario_id=usuario.pk, equipe_id=equipe_id, equipe__ativa=True,
    ).exists()


def pode_distribuir(usuario, chamado):
    if not usuario.is_active or chamado.status in FINALIZADOS:
        return False
    if usuario.is_superuser:
        return True
    return usuario.is_staff and IntegranteEquipe.objects.filter(
        usuario_id=usuario.pk, equipe_id=chamado.equipe_id, equipe__ativa=True, coordenador=True,
    ).exists()
