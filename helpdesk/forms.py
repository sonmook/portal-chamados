from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from .user_security import validar_administrador, validar_pendencias
from .models import Chamado, Comentario, Equipe
from .validators import validar_anexo


class ResolucaoForm(forms.Form):
    resolucao = forms.CharField(strip=True)
    anexo_resolucao = forms.FileField(required=False, validators=[validar_anexo])


class RedistribuirChamadoForm(forms.Form):
    equipe = forms.ModelChoiceField(queryset=Equipe.objects.filter(ativa=True), label='Equipe de destino',
                                   widget=forms.HiddenInput)
    tecnico = forms.ModelChoiceField(queryset=User.objects.none(), required=False, label='Responsável no destino',
                                    empty_label='Sem responsável — deixar na fila',
                                    widget=forms.Select(attrs={'class': 'form-select'}))
    motivo = forms.CharField(max_length=500, strip=True, widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
                            help_text='Informe o motivo, sem senhas ou dados sensíveis.')
    responsavel_anterior = forms.IntegerField(required=False, widget=forms.HiddenInput)
    equipe_anterior = forms.IntegerField(widget=forms.HiddenInput)
    versao_atribuicao = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    def __init__(self, *args, chamado, **kwargs):
        super().__init__(*args, **kwargs)
        self.chamado = chamado
        destino = self.data.get('equipe') if self.is_bound else self.initial.get('equipe', chamado.equipe_id)
        try:
            destino = int(destino)
        except (TypeError, ValueError):
            destino = None
        self.fields['tecnico'].queryset = User.objects.filter(
            is_active=True, is_staff=True, vinculos_equipes__equipe_id=destino, vinculos_equipes__equipe__ativa=True,
        ).order_by('username') if destino else User.objects.none()
        for campo, valor in {'equipe': chamado.equipe_id, 'equipe_anterior': chamado.equipe_id,
                             'responsavel_anterior': chamado.tecnico_id,
                             'versao_atribuicao': chamado.versao_atribuicao}.items():
            self.fields[campo].initial = valor

    def clean(self):
        dados = super().clean()
        if dados.get('equipe') and dados['equipe'].pk == self.chamado.equipe_id:
            tecnico = dados.get('tecnico')
            if 'tecnico' in dados and (tecnico.pk if tecnico else None) == self.chamado.tecnico_id:
                self.add_error(None, 'Selecione outra equipe ou altere o responsável.')
        return dados


class ChamadoForm(forms.ModelForm):
    """
    Formulário para abertura de novos chamados.
    Utiliza as classes do Bootstrap ('form-control', 'form-select') para estilização nativa.
    """
    class Meta:
        model = Chamado
        fields = ['titulo', 'descricao', 'categoria', 'prioridade', 'anexo']
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-control'}),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'prioridade': forms.Select(attrs={'class': 'form-select'}),
            'anexo': forms.FileInput(attrs={'class': 'form-control'}),
        }

class ComentarioForm(forms.ModelForm):
    """
    Formulário para adicionar respostas/interações na linha do tempo do chamado.
    """
    class Meta:
        model = Comentario
        fields = ['texto', 'anexo']
        widgets = {
            'texto': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Escreva seu comentário...'}),
            'anexo': forms.FileInput(attrs={'class': 'form-control'}),
        }


class NovoUsuarioForm(forms.ModelForm):
    """
    Formulário para criação manual de usuários pelo painel do Administrador.
    Inclui lógica para definir os níveis de acesso (Staff/Superuser) automaticamente.
    """
    password1 = forms.CharField(widget=forms.PasswordInput, label='Senha')
    password2 = forms.CharField(widget=forms.PasswordInput, label='Confirme a Senha')

    OPCOES_NIVEL = (
        ('cliente', '👤 Cliente (Apenas abre chamados)'),
        ('ti', '🛠️ Técnico de TI (Resolve chamados)'),
        ('admin', '👑 Administrador (Gerencia o sistema)'),
    )
    nivel_acesso = forms.ChoiceField(choices=OPCOES_NIVEL, widget=forms.Select, initial='cliente')

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']

    def clean_password2(self):
        # Valida se as senhas digitadas coincidem
        pass1 = self.cleaned_data.get('password1')
        pass2 = self.cleaned_data.get('password2')
        if pass1 and pass2 and pass1 != pass2:
            raise forms.ValidationError("As senhas não coincidem.")
        return pass2

    def _post_clean(self):
        super()._post_clean()
        senha = self.cleaned_data.get('password2')
        if senha:
            try:
                validate_password(senha, self.instance)
            except forms.ValidationError as erro:
                self.add_error('password2', erro)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        
        # Aplica a hierarquia de permissões do Django baseada na escolha do dropdown
        nivel = self.cleaned_data['nivel_acesso']
        if nivel == 'cliente':
            user.is_staff = False
            user.is_superuser = False
        elif nivel == 'ti':
            user.is_staff = True
            user.is_superuser = False
        elif nivel == 'admin':
            user.is_staff = True
            user.is_superuser = True
            
        if commit:
            user.save()
        return user
    

class EditarUsuarioForm(forms.ModelForm):
    """
    Formulário para edição de usuários existentes.
    Permite alterar dados básicos, nível de acesso e bloquear/desbloquear contas.
    """
    OPCOES_NIVEL = (
        ('cliente', '👤 Cliente (Apenas abre chamados)'),
        ('ti', '🛠️ Técnico de TI (Resolve chamados)'),
        ('admin', '👑 Administrador (Gerencia o sistema)'),
    )
    nivel_acesso = forms.ChoiceField(choices=OPCOES_NIVEL, widget=forms.Select)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'is_active']
        labels = {
            'is_active': 'Usuário Ativo no Sistema (Desmarque para bloquear acesso)'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Preenche o dropdown de nível de acesso com base no status atual do usuário no banco
        if self.instance.pk:
            if self.instance.is_superuser:
                self.fields['nivel_acesso'].initial = 'admin'
            elif self.instance.is_staff:
                self.fields['nivel_acesso'].initial = 'ti'
            else:
                self.fields['nivel_acesso'].initial = 'cliente'

    def clean(self):
        dados = super().clean()
        if self.instance.pk and 'nivel_acesso' in dados:
            validar_administrador(
                self.instance.pk, dados.get('is_active', False),
                dados['nivel_acesso'] == 'admin', dados['nivel_acesso'] == 'admin',
            )
            validar_pendencias(self.instance.pk, dados.get('is_active', False), dados['nivel_acesso'] != 'cliente')
        return dados

    def save(self, commit=True):
        user = super().save(commit=False)
        nivel = self.cleaned_data['nivel_acesso']
        
        # Atualiza a hierarquia de permissões
        if nivel == 'cliente':
            user.is_staff = False
            user.is_superuser = False
        elif nivel == 'ti':
            user.is_staff = True
            user.is_superuser = False
        elif nivel == 'admin':
            user.is_staff = True
            user.is_superuser = True
            
        if commit:
            user.save()
        return user
