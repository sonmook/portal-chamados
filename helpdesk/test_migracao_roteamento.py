from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigracaoRoteamentoTests(TransactionTestCase):
    def tearDown(self):
        MigrationExecutor(connection).migrate([('helpdesk', '0018_enquadramento_foto')])
        super().tearDown()

    def test_regras_iniciais_nao_reclassificam_chamados_nem_recriam_equipes_renomeadas(self):
        anterior = ('helpdesk', '0015_chamados_por_equipe')
        executor = MigrationExecutor(connection)
        executor.migrate([anterior])
        apps = executor.loader.project_state([anterior]).apps
        Equipe = apps.get_model('helpdesk', 'Equipe')
        Chamado = apps.get_model('helpdesk', 'Chamado')
        Usuario = apps.get_model('auth', 'User')
        triagem = Equipe.objects.filter(triagem_padrao=True).first()
        if triagem is None:
            triagem = Equipe.objects.create(nome='Triagem personalizada', triagem_padrao=True)
        rede, _ = Equipe.objects.get_or_create(nome='Infraestrutura e Redes')
        rede.nome = 'Conectividade personalizada'
        rede.save()
        n2, _ = Equipe.objects.get_or_create(nome='Suporte Especializado — N2')
        n2.ativa = False
        n2.save()
        usuario = Usuario.objects.create(username='cliente-migracao-roteamento')
        chamado = Chamado.objects.create(titulo='Histórico', descricao='Preservar', categoria='Rede',
                                         solicitante=usuario, equipe_id=n2.pk)
        campos = ('id', 'equipe_id', 'status', 'solicitante_id', 'tecnico_id', 'data_criacao',
                  'data_atualizacao', 'data_vencimento', 'ultima_interacao_em', 'versao_atribuicao')
        antes = Chamado.objects.filter(pk=chamado.pk).values(*campos).get()
        total_equipes = Equipe.objects.count()
        executor = MigrationExecutor(connection)
        executor.migrate([('helpdesk', '0016_regras_encaminhamento')])
        apps = executor.loader.project_state([('helpdesk', '0016_regras_encaminhamento')]).apps
        Equipe = apps.get_model('helpdesk', 'Equipe')
        Chamado = apps.get_model('helpdesk', 'Chamado')
        Regra = apps.get_model('helpdesk', 'RegraEncaminhamento')
        self.assertEqual(Chamado.objects.filter(pk=chamado.pk).values(*campos).get(), antes)
        self.assertEqual(Equipe.objects.count(), total_equipes)
        self.assertFalse(Equipe.objects.filter(nome='Infraestrutura e Redes').exists())
        self.assertFalse(Equipe.objects.get(pk=n2.pk).ativa)
        self.assertEqual(Regra.objects.count(), 5)
        regra_rede = Regra.objects.get(categoria='Rede')
        self.assertFalse(regra_rede.ativa)
        self.assertEqual(regra_rede.equipe_id, triagem.pk)
        self.assertEqual(Regra.objects.get(categoria='Hardware').equipe_id, n2.pk)
