from django.contrib import admin
from .models import Chamado, Comentario

# Registra os modelos no painel administrativo padrão do Django (/admin)
# Isso permite gerenciar os dados cruamente pelo backend, se necessário.
admin.site.register(Chamado)
admin.site.register(Comentario)

from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied

from .models import Chamado, Comentario
from .user_security import bloquear_administradores, validar_administrador

admin.site.register(Chamado)
admin.site.register(Comentario)


class UsuarioProtegidoForm(UserChangeForm):
    def clean(self):
        dados = super().clean()
        bloquear_administradores()
        validar_administrador(
            self.instance.pk, dados.get('is_active', False),
            dados.get('is_staff', False), dados.get('is_superuser', False),
        )
        return dados


class UsuarioProtegidoAdmin(UserAdmin):
    form = UsuarioProtegidoForm

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_active and obj.is_staff and obj.is_superuser:
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        if queryset.filter(is_active=True, is_staff=True, is_superuser=True).exists():
            raise PermissionDenied('Rebaixe o administrador antes de excluir sua conta.')
        super().delete_queryset(request, queryset)


admin.site.unregister(User)
admin.site.register(User, UsuarioProtegidoAdmin)
