from django.contrib.auth.models import User
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from .audit import registrar
from .models import Chamado, Comentario

# Conteúdo pessoal, texto e senhas são registrados apenas como "alterado".
CAMPOS = {
    User: ('username', 'email', 'first_name', 'last_name', 'password', 'is_active', 'is_staff', 'is_superuser'),
    Chamado: ('titulo', 'descricao', 'categoria', 'prioridade', 'status', 'solicitante_id', 'tecnico_id', 'equipe_id', 'fechado_por_id', 'data_vencimento', 'data_fechamento', 'anexo'),
    Comentario: ('chamado_id', 'autor_id', 'texto', 'anexo'),
}
VALORES = {'is_active', 'is_staff', 'is_superuser', 'categoria', 'prioridade', 'status',
           'solicitante_id', 'tecnico_id', 'equipe_id', 'fechado_por_id', 'chamado_id', 'autor_id',
           'data_vencimento', 'data_fechamento'}


def snapshot(instancia):
    dados = {}
    for campo in CAMPOS[type(instancia)]:
        valor = getattr(instancia, campo)
        if hasattr(valor, 'isoformat'):
            valor = valor.isoformat()
        elif campo == 'anexo':
            valor = valor.name
        dados[campo] = valor
    return dados


@receiver(pre_save)
def antes(sender, instance, raw=False, **kwargs):
    if sender not in CAMPOS or raw:
        return
    anterior = sender.objects.filter(pk=instance.pk).first() if instance.pk else None
    instance._audit_anterior = snapshot(anterior) if anterior else None


@receiver(post_save)
def depois(sender, instance, created, raw=False, **kwargs):
    if sender not in CAMPOS or raw:
        return
    # Lê o banco para respeitar update_fields e ignorar atributos não persistidos.
    atual = snapshot(sender.objects.get(pk=instance.pk))
    anterior = getattr(instance, '_audit_anterior', None)
    mudancas = {}
    for campo, valor in atual.items():
        if anterior is None or anterior[campo] != valor:
            mudancas[campo] = {'antes': anterior[campo] if anterior else None, 'depois': valor} if campo in VALORES else {'alterado': True}
    if mudancas:
        registrar(sender._meta.label_lower, instance.pk, 'criado' if created else 'alterado', mudancas)


@receiver(post_delete)
def removido(sender, instance, **kwargs):
    if sender in CAMPOS:
        registrar(sender._meta.label_lower, instance.pk, 'excluido', {})


from django.db.models.signals import m2m_changed


@receiver(m2m_changed, sender=User.groups.through)
@receiver(m2m_changed, sender=User.user_permissions.through)
def permissoes(sender, instance, action, reverse, model, pk_set, **kwargs):
    if action not in ('post_add', 'post_remove', 'pre_clear'):
        return
    campo = 'groups' if sender == User.groups.through else 'user_permissions'
    if reverse:
        usuarios = pk_set if pk_set is not None else getattr(instance, 'user_set').values_list('pk', flat=True)
        for pk in usuarios:
            registrar('auth.user', pk, 'permissoes', {campo: {'acao': action, 'ids': [instance.pk]}})
    else:
        ids = sorted(pk_set) if pk_set is not None else list(getattr(instance, campo).values_list('pk', flat=True))
        if ids:
            registrar('auth.user', instance.pk, 'permissoes', {campo: {'acao': action, 'ids': ids}})
