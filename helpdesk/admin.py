from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied

from .models import Chamado, Comentario, RegistroAuditoria
from .user_security import bloquear_administradores, validar_administrador, validar_pendencias


class UsuarioProtegidoForm(UserChangeForm):
    def clean(self):
        dados = super().clean()
        bloquear_administradores()
        if self.instance.pk:
            User.objects.select_for_update().get(pk=self.instance.pk)
        validar_administrador(
            self.instance.pk, dados.get('is_active', False),
            dados.get('is_staff', False), dados.get('is_superuser', False),
        )
        validar_pendencias(self.instance.pk, dados.get('is_active', False), dados.get('is_staff', False))
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





@admin.register(Chamado)
class ChamadoAdmin(admin.ModelAdmin):
    readonly_fields = ('status', 'tecnico', 'data_criacao', 'data_atualizacao', 'data_fechamento', 'fechado_por')

    def has_change_permission(self, request, obj=None):
        if obj and obj.status in ('Resolvido', 'Fechado'):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if change and Chamado.objects.select_for_update().get(pk=obj.pk).status in ('Resolvido', 'Fechado'):
            raise PermissionDenied
        super().save_model(request, obj, form, change)

    def delete_queryset(self, request, queryset):
        raise PermissionDenied


@admin.register(Comentario)
class ComentarioAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def delete_queryset(self, request, queryset):
        raise PermissionDenied


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ('criado_em', 'ator', 'origem', 'objeto', 'objeto_id', 'acao')
    list_filter = ('origem', 'objeto', 'acao')
    search_fields = ('=objeto_id',)

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def delete_queryset(self, request, queryset):
        raise PermissionDenied


admin.site.unregister(User)
admin.site.register(User, UsuarioProtegidoAdmin)
