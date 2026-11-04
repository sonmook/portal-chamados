from io import BytesIO
import warnings

from django import forms
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError


class PerfilForm(forms.Form):
    first_name = forms.CharField(label='Nome', max_length=150, required=False)
    last_name = forms.CharField(label='Sobrenome', max_length=150, required=False)
    cargo = forms.CharField(label='Cargo', max_length=100, required=False)
    departamento = forms.CharField(label='Departamento', max_length=100, required=False)
    ramal = forms.CharField(label='Ramal', max_length=20, required=False)
    foto = forms.FileField(label='Nova foto', required=False,
                           help_text='JPEG ou PNG de até 2 MB, 4096 px por lado e 4 milhões de pixels. A imagem será ajustada para até 512 px.',
                           widget=forms.ClearableFileInput(attrs={'accept': 'image/png,image/jpeg'}))
    foto_x = forms.IntegerField(label='Posição horizontal', min_value=0, max_value=100, required=False,
                                widget=forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 100, 'step': 1}))
    foto_y = forms.IntegerField(label='Posição vertical', min_value=0, max_value=100, required=False,
                                widget=forms.NumberInput(attrs={'type': 'range', 'min': 0, 'max': 100, 'step': 1}))
    foto_zoom = forms.IntegerField(label='Zoom', min_value=100, max_value=300, required=False,
                                   widget=forms.NumberInput(attrs={'type': 'range', 'min': 100, 'max': 300, 'step': 1}))
    remover_foto = forms.BooleanField(label='Remover foto atual', required=False)
    versao = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome, campo in self.fields.items():
            if nome not in ('versao', 'remover_foto'):
                campo.widget.attrs['class'] = 'form-control'
        for nome in ('foto_x', 'foto_y', 'foto_zoom'):
            self.fields[nome].widget.attrs['class'] = 'form-range'
        self.fields['remover_foto'].widget.attrs['class'] = 'form-check-input'
        self.fields['first_name'].widget.attrs['autocomplete'] = 'given-name'
        self.fields['last_name'].widget.attrs['autocomplete'] = 'family-name'

    def clean_foto(self):
        arquivo = self.cleaned_data.get('foto')
        if not arquivo:
            return None
        if arquivo.size > 2 * 1024 * 1024:
            raise forms.ValidationError('A foto deve ter no máximo 2 MB.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(arquivo) as imagem:
                    if imagem.format not in ('JPEG', 'PNG') or getattr(imagem, 'n_frames', 1) != 1:
                        raise ValueError
                    largura, altura = imagem.size
                    if max(largura, altura) > 4096 or largura * altura > 4_000_000:
                        raise ValueError
                    imagem.load()
                    orientada = ImageOps.exif_transpose(imagem)
                    orientada.thumbnail((512, 512))
                    # Nova imagem sem EXIF, comentários ou outros metadados do upload.
                    limpa = Image.new('RGB', orientada.size, 'white')
                    rgba = orientada.convert('RGBA')
                    limpa.paste(rgba.convert('RGB'), mask=rgba.getchannel('A'))
                    saida = BytesIO()
                    limpa.save(saida, format='PNG')
            return ContentFile(saida.getvalue(), name='avatar.png')
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise forms.ValidationError('Envie uma imagem JPEG ou PNG válida, não animada, dentro dos limites informados.')

    def clean(self):
        dados = super().clean()
        for nome, padrao in [('foto_x', 50), ('foto_y', 50), ('foto_zoom', 100)]:
            if nome not in self.errors and dados.get(nome) is None:
                dados[nome] = self.initial.get(nome, padrao)
        if dados.get('foto') and dados.get('remover_foto'):
            self.add_error('remover_foto', 'Escolha uma nova foto ou remova a atual, sem combinar as duas ações.')
        return dados
