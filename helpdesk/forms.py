from django import forms
from django.contrib.auth.models import User
from .models import Chamado, Comentario

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