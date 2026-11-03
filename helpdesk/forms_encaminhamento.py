from django import forms
from django.db.models import Q

from .models import Equipe, RegraEncaminhamento


class RegraEncaminhamentoForm(forms.ModelForm):
    versao_atual = forms.IntegerField(min_value=0, initial=0, widget=forms.HiddenInput)

    class Meta:
        model = RegraEncaminhamento
        fields = ['categoria', 'equipe', 'ativa']
        labels = {'categoria': 'Categoria', 'equipe': 'Equipe de destino', 'ativa': 'Regra ativa'}
        widgets = {'categoria': forms.Select(attrs={'class': 'form-select'}),
                   'equipe': forms.Select(attrs={'class': 'form-select'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        permitidas = Q(ativa=True)
        if self.instance.pk:
            permitidas |= Q(pk=self.instance.equipe_id)
            self.fields['categoria'].disabled = True
        self.fields['equipe'].queryset = Equipe.objects.filter(permitidas).order_by('nome')
        self.fields['versao_atual'].initial = self.instance.versao

    def clean(self):
        dados = super().clean()
        equipe = dados.get('equipe')
        if dados.get('ativa') and equipe and not equipe.ativa:
            self.add_error('equipe', 'Escolha uma equipe ativa ou desative a regra.')
        return dados
