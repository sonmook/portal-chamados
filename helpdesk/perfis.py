from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F
from io import BytesIO
from PIL import Image

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_GET

from .audit import registrar
from .forms_perfil import PerfilForm
from .models import Perfil, IntegranteEquipe, Conquista


@login_required
@require_http_methods(['GET', 'POST'])
def meu_perfil(request):
    perfil = Perfil.objects.filter(usuario=request.user).first()
    inicial = {nome: getattr(perfil, nome, '') for nome in ('cargo', 'departamento', 'ramal')}
    inicial.update({nome: getattr(perfil, nome, padrao) for nome, padrao in [('foto_x', 50), ('foto_y', 50), ('foto_zoom', 100)]})
    inicial.update(first_name=request.user.first_name, last_name=request.user.last_name,
                   versao=perfil.versao if perfil else 0)
    form = PerfilForm(request.POST if request.method == 'POST' else None,
                      request.FILES if request.method == 'POST' else None, initial=inicial)
    status = 200
    if request.method == 'POST' and form.is_valid():
        novo_arquivo = None
        storage = Perfil._meta.get_field('foto').storage
        try:
            with transaction.atomic():
                usuario = User.objects.select_for_update().get(pk=request.user.pk)
                atual, _ = Perfil.objects.get_or_create(usuario=usuario)
                atual = Perfil.objects.select_for_update().get(pk=atual.pk)
                if atual.versao != form.cleaned_data['versao']:
                    form.add_error(None, 'Seu perfil foi alterado em outra página. Reabra Meu Perfil antes de salvar.')
                    status = 409
                    transaction.set_rollback(True)
                else:
                    antigo = atual.foto.name
                    foto = form.cleaned_data['foto']
                    nome_foto = antigo
                    if foto:
                        nome_foto = storage.save(atual._meta.get_field('foto').generate_filename(atual, foto.name), foto)
                        novo_arquivo = nome_foto
                    elif form.cleaned_data['remover_foto']:
                        nome_foto = ''
                    campos = {nome: form.cleaned_data[nome] for nome in ('cargo', 'departamento', 'ramal', 'foto_x', 'foto_y', 'foto_zoom')}
                    if form.cleaned_data['remover_foto']:
                        campos.update(foto_x=50, foto_y=50, foto_zoom=100)
                    mudancas = {nome: {'alterado': True} for nome, valor in campos.items() if getattr(atual, nome) != valor}
                    for nome in ('first_name', 'last_name'):
                        if getattr(usuario, nome) != form.cleaned_data[nome]:
                            mudancas[nome] = {'alterado': True}
                    if nome_foto != antigo:
                        mudancas['foto'] = {'alterado': True}
                    atualizado = Perfil.objects.filter(pk=atual.pk, versao=form.cleaned_data['versao']).update(
                        **campos, foto=nome_foto, versao=F('versao') + 1)
                    if not atualizado:
                        raise ConflitoPerfil
                    # Só os nomes são gravados: papéis, login, e-mail e senha nunca vêm do formulário.
                    usuario.first_name = form.cleaned_data['first_name']
                    usuario.last_name = form.cleaned_data['last_name']
                    usuario.save(update_fields=['first_name', 'last_name'])
                    if mudancas:
                        registrar('helpdesk.perfil', atual.pk, 'alterado', mudancas)
                    if antigo and antigo != nome_foto:
                        transaction.on_commit(lambda: storage.delete(antigo), robust=True)
            if status != 409:
                messages.success(request, 'Perfil atualizado com sucesso.')
                return redirect('meu_perfil')
        except ConflitoPerfil:
            if novo_arquivo:
                storage.delete(novo_arquivo)
            form.add_error(None, 'Seu perfil foi alterado em outra página. Reabra Meu Perfil antes de salvar.')
            status = 409
        except Exception:
            if novo_arquivo:
                storage.delete(novo_arquivo)
            raise
    return render(request, 'helpdesk/perfil.html', {
        'form': form, 'perfil': perfil, 'conquistas': Conquista.objects.filter(usuario=request.user)[:3],
        'vinculos': IntegranteEquipe.objects.filter(usuario=request.user).select_related('equipe').order_by('equipe__nome'),
    }, status=status)


class ConflitoPerfil(Exception):
    pass


def resposta_foto(arquivo):
    resposta = FileResponse(arquivo, content_type='image/png')
    resposta['Cache-Control'] = 'private, no-store'
    resposta['X-Content-Type-Options'] = 'nosniff'
    resposta['Content-Disposition'] = 'inline; filename="foto-perfil.png"'
    return resposta


@login_required
@require_GET
def foto_perfil(request, usuario_id):
    perfil = get_object_or_404(Perfil, usuario_id=usuario_id, usuario__is_active=True)
    if not perfil.foto:
        raise Http404
    try:
        with perfil.foto.open('rb') as arquivo, Image.open(arquivo) as imagem:
            largura, altura = imagem.size
            lado = min(largura, altura) * 100 / perfil.foto_zoom
            esquerda = (largura - lado) * perfil.foto_x / 100
            topo = (altura - lado) * perfil.foto_y / 100
            avatar = imagem.resize((512, 512), Image.Resampling.LANCZOS,
                                   box=(esquerda, topo, esquerda + lado, topo + lado))
            saida = BytesIO()
            avatar.save(saida, 'PNG')
            saida.seek(0)
    except (OSError, ValueError):
        raise Http404
    return resposta_foto(saida)


@login_required
@require_GET
def foto_base_perfil(request):
    """Fonte normalizada sem recorte, disponível apenas ao próprio usuário."""
    perfil = get_object_or_404(Perfil, usuario=request.user)
    if not perfil.foto:
        raise Http404
    try:
        arquivo = perfil.foto.open('rb')
    except (OSError, ValueError):
        raise Http404
    return resposta_foto(arquivo)
