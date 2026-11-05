"""Amplia o catálogo sem modificar regras ou medalhas existentes."""
from django.db import migrations
from django.utils import timezone


CATALOGO = [
    ('missao-cumprida', 'Missão cumprida', 'Conclua 5 resoluções elegíveis.', 'pessoa', 'resolucoes', 5, 'raio'),
    ('resolvedor-elite', 'Resolvedor de elite', 'Conclua 50 resoluções elegíveis.', 'pessoa', 'resolucoes', 50, 'estrela'),
    ('centuriao-suporte', 'Centurião do suporte', 'Conclua 100 resoluções elegíveis.', 'pessoa', 'resolucoes', 100, 'trofeu'),
    ('ritmo-certo', 'No ritmo certo', 'Conclua 5 resoluções elegíveis dentro do SLA.', 'pessoa', 'no_prazo', 5, 'cronometro'),
    ('guardiao-sla', 'Guardião do SLA', 'Conclua 50 resoluções elegíveis dentro do SLA.', 'pessoa', 'no_prazo', 50, 'escudo'),
    ('sintonia-equipe', 'Sintonia de equipe', 'A equipe conclui 10 resoluções elegíveis.', 'equipe', 'resolucoes', 10, 'equipe'),
    ('forca-tarefa', 'Força-tarefa', 'A equipe conclui 50 resoluções elegíveis.', 'equipe', 'resolucoes', 50, 'foguete'),
    ('operacao-centenaria', 'Operação centenária', 'A equipe conclui 100 resoluções elegíveis.', 'equipe', 'resolucoes', 100, 'alvo'),
]


def ampliar_catalogo(apps, schema_editor):
    Regra = apps.get_model('helpdesk', 'RegraConquista')
    inicio = timezone.now()
    for codigo, nome, descricao, alvo, metrica, meta, icone in CATALOGO:
        Regra.objects.using(schema_editor.connection.alias).get_or_create(codigo=codigo, defaults={
            'nome': nome, 'descricao': descricao, 'alvo': alvo, 'metrica': metrica,
            'meta': meta, 'icone': icone, 'inicio_em': inicio, 'ativa': True,
        })


class Migration(migrations.Migration):
    dependencies = [('helpdesk', '0021_construtor_conquistas')]
    # A reversão preserva o catálogo e as medalhas que já tenham sido concedidas.
    operations = [migrations.RunPython(ampliar_catalogo, migrations.RunPython.noop)]
