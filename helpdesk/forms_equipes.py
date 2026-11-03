from django import forms
from django.contrib.auth.models import User
from django.db.models import Q

from .models import Equipe
from .acesso import FINALIZADOS


class UsuarioEquipeChoice(forms.ModelMultipleChoiceField):
    def label_from_instance(self, usuario):
        nome = usuario.get_full_name() or usuario.username
        situacao = '' if usuario.is_active and usuario.is_staff else ' — sem acesso de técnico ativo'
        return f'{nome} ({usuario.username}){situacao}'


class EquipeForm(forms.ModelForm):
    integrantes = UsuarioEquipeChoice(queryset=User.objects.none(), required=False,
                                      widget=forms.CheckboxSelectMultiple)
    coordenadores = UsuarioEquipeChoice(queryset=User.objects.none(), required=False,
                                        widget=forms.CheckboxSelectMultiple)
    versao_atual = forms.IntegerField(min_value=0, widget=forms.HiddenInput, initial=0)

    class Meta:
        model = Equipe
        fields = ['nome', 'descricao', 'ativa']
        labels = {'nome': 'Nome da equipe', 'descricao': 'Responsabilidades', 'ativa': 'Equipe ativa'}
        widgets = {'nome': forms.TextInput(attrs={'class': 'form-control'}),
                   'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        permitidos = Q(is_active=True, is_staff=True)
        if self.instance.pk:
            permitidos |= Q(vinculos_equipes__equipe_id=self.instance.pk)
        usuarios = User.objects.filter(permitidos).distinct().order_by('username')
        self.fields['integrantes'].queryset = usuarios
        self.fields['coordenadores'].queryset = usuarios
        self.fields['versao_atual'].initial = self.instance.versao
        if self.instance.pk:
            self.fields['integrantes'].initial = list(self.instance.vinculos.values_list('usuario_id', flat=True))
            self.fields['coordenadores'].initial = list(self.instance.vinculos.filter(coordenador=True).values_list('usuario_id', flat=True))

    def clean(self):
        dados = super().clean()
        integrantes = dados.get('integrantes')
        coordenadores = dados.get('coordenadores')
        if integrantes is not None and coordenadores is not None:
            ids = {u.pk for u in integrantes}
            if any(u.pk not in ids for u in coordenadores):
                self.add_error('coordenadores', 'Coordenadores devem fazer parte dos integrantes selecionados.')
            if any(not u.is_active or not u.is_staff for u in integrantes):
                self.add_error('integrantes', 'Remova da seleção as contas sem acesso de técnico ativo antes de salvar.')
            if self.instance.pk and self.instance.chamados.exclude(status__in=FINALIZADOS).exclude(tecnico_id=None).exclude(tecnico_id__in=ids).exists():
                self.add_error('integrantes', 'Redistribua os chamados ativos antes de remover seus responsáveis da equipe.')
        if self.instance.pk and not dados.get('ativa', False):
            if self.instance.triagem_padrao:
                self.add_error('ativa', 'A equipe de triagem deve permanecer ativa para receber novos chamados.')
            elif self.instance.chamados.exclude(status__in=FINALIZADOS).exists():
                self.add_error('ativa', 'Transfira os chamados pendentes antes de desativar a equipe.')
        return dados
