import django.db.models.deletion
import helpdesk.models
from django.db import migrations, models


def migrar_chamados(apps, schema_editor):
    Equipe = apps.get_model('helpdesk', 'Equipe')
    Chamado = apps.get_model('helpdesk', 'Chamado')
    Integrante = apps.get_model('helpdesk', 'IntegranteEquipe')
    Usuario = apps.get_model('auth', 'User')
    alias = schema_editor.connection.alias
    equipe, _ = Equipe.objects.using(alias).get_or_create(nome='Central de Serviços — N1')
    Equipe.objects.using(alias).filter(pk=equipe.pk).update(triagem_padrao=True, ativa=True)
    Chamado.objects.using(alias).update(equipe_id=equipe.pk)
    responsaveis = set(Chamado.objects.using(alias).exclude(tecnico_id=None).values_list('tecnico_id', flat=True))
    responsaveis.update(Chamado.objects.using(alias).exclude(fechado_por_id=None).values_list('fechado_por_id', flat=True))
    for pk in Usuario.objects.using(alias).filter(pk__in=responsaveis, is_active=True, is_staff=True).values_list('pk', flat=True):
        Integrante.objects.using(alias).get_or_create(equipe_id=equipe.pk, usuario_id=pk)


class Migration(migrations.Migration):
    dependencies = [('helpdesk', '0014_merge_0012_ultima_interacao_0013_equipes_cadastro')]
    operations = [
        migrations.AddField(model_name='equipe', name='triagem_padrao', field=models.BooleanField(default=False, editable=False)),
        migrations.AddConstraint(model_name='equipe', constraint=models.UniqueConstraint(
            fields=('triagem_padrao',), condition=models.Q(triagem_padrao=True), name='uma_equipe_triagem')),
        migrations.AddField(model_name='chamado', name='equipe', field=models.ForeignKey(
            null=True, to='helpdesk.equipe', on_delete=django.db.models.deletion.PROTECT, related_name='chamados')),
        migrations.AddField(model_name='chamado', name='versao_atribuicao', field=models.PositiveIntegerField(default=0, editable=False)),
        migrations.RunPython(migrar_chamados, migrations.RunPython.noop),
        migrations.AlterField(model_name='chamado', name='equipe', field=models.ForeignKey(
            default=helpdesk.models.equipe_triagem_id, to='helpdesk.equipe',
            on_delete=django.db.models.deletion.PROTECT, related_name='chamados')),
    ]
