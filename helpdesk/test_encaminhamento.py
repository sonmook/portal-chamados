from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from .models import Chamado, Equipe, IntegranteEquipe, RegraEncaminhamento, RegistroAuditoria
from .test_helpers import dados_atribuicao
from .encaminhamento import criar_chamado_encaminhado


class EncaminhamentoTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin-regras', is_staff=True, is_superuser=True)
        self.cliente = User.objects.create_user('cliente-regras')
        self.tecnico = User.objects.create_user('tecnico-rede', is_staff=True)
        self.triagem = Equipe.objects.get(triagem_padrao=True)
        self.rede = Equipe.objects.get(nome='Infraestrutura e Redes')
        self.n2 = Equipe.objects.get(nome='Suporte Especializado — N2')
        IntegranteEquipe.objects.create(equipe=self.rede, usuario=self.tecnico, coordenador=True)
        self.regra = RegraEncaminhamento.objects.get(categoria='Rede')
        self.lista = reverse('listar_regras_encaminhamento')
        self.editar = reverse('editar_regra_encaminhamento', args=[self.regra.pk])

    def abrir(self, categoria='Rede', **extras):
        self.client.force_login(self.cliente)
        dados = {'titulo': f'Novo {Chamado.objects.count()}', 'descricao': 'Fixture',
                 'categoria': categoria, 'prioridade': 'Normal'}
        dados.update(extras)
        return self.client.post(reverse('novo_chamado'), dados)

    def dados(self, **extras):
        dados = {'categoria': 'Rede', 'equipe': self.rede.pk, 'ativa': 'on', 'versao_atual': self.regra.versao}
        dados.update(extras)
        return dados

    def decisao(self, chamado):
        return RegistroAuditoria.objects.get(objeto='helpdesk.chamado', objeto_id=chamado.pk, acao='encaminhado')

    def test_regra_ativa_define_destino_e_registra_decisao(self):
        self.assertEqual(self.abrir(equipe=self.n2.pk).status_code, 302)
        chamado = Chamado.objects.latest('pk')
        self.assertEqual(chamado.equipe, self.rede)
        self.assertIsNone(chamado.tecnico)
        self.assertEqual(chamado.status, 'Aberto')
        self.assertIsNotNone(chamado.data_vencimento)
        evento = self.decisao(chamado)
        self.assertEqual(evento.ator, self.cliente)
        self.assertEqual(evento.origem, 'portal')
        self.assertEqual(evento.alteracoes, {'categoria': 'Rede', 'equipe_id': self.rede.pk,
            'regra_id': self.regra.pk, 'versao_regra': 0, 'modo': 'categoria', 'motivo_triagem': None})
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.get(reverse('detalhes_chamado', args=[chamado.pk])).status_code, 200)

    def test_servico_de_criacao_deixa_na_fila_e_recusa_objeto_existente(self):
        chamado = Chamado(titulo='Integração', descricao='Fixture', categoria='Rede',
                          solicitante=self.cliente, tecnico=self.tecnico)
        criar_chamado_encaminhado(chamado)
        chamado.refresh_from_db()
        self.assertEqual(chamado.equipe, self.rede)
        self.assertIsNone(chamado.tecnico)
        with self.assertRaises(ValueError):
            criar_chamado_encaminhado(chamado)

    def test_cinco_mapeamentos_iniciais(self):
        destinos = {'Rede': 'Infraestrutura e Redes', 'Acessos': 'Identidades e Acessos',
                    'Hardware': 'Suporte Especializado — N2', 'Software': 'Sistemas e Aplicações',
                    'Outros': self.triagem.nome}
        for categoria, nome in destinos.items():
            with self.subTest(categoria=categoria):
                equipe = Equipe.objects.get(nome=nome)
                if not equipe.triagem_padrao:
                    IntegranteEquipe.objects.get_or_create(equipe=equipe, usuario=self.tecnico)
                self.assertEqual(self.abrir(categoria).status_code, 302)
                self.assertEqual(Chamado.objects.latest('pk').equipe_id, equipe.pk)

    def test_sem_regra_usa_triagem(self):
        self.regra.delete()
        self.abrir()
        chamado = Chamado.objects.latest('pk')
        self.assertEqual(chamado.equipe, self.triagem)
        self.assertEqual(self.decisao(chamado).alteracoes['motivo_triagem'], 'sem_regra')

    def test_regra_inativa_usa_triagem(self):
        self.regra.ativa = False
        self.regra.save()
        self.abrir()
        chamado = Chamado.objects.latest('pk')
        self.assertEqual(chamado.equipe, self.triagem)
        self.assertEqual(self.decisao(chamado).alteracoes['motivo_triagem'], 'regra_inativa')

    def test_destino_inativo_usa_triagem(self):
        self.rede.ativa = False
        self.rede.save()
        self.abrir()
        chamado = Chamado.objects.latest('pk')
        self.assertEqual(chamado.equipe, self.triagem)
        self.assertEqual(self.decisao(chamado).alteracoes['motivo_triagem'], 'equipe_inativa')

    def test_sem_vinculo_ativo_usa_triagem_inclusive_contas_inativas_ou_rebaixadas(self):
        for ativo, staff in ((False, True), (True, False)):
            with self.subTest(ativo=ativo, staff=staff):
                self.tecnico.is_active = ativo
                self.tecnico.is_staff = staff
                self.tecnico.save()
                self.abrir()
                chamado = Chamado.objects.latest('pk')
                self.assertEqual(chamado.equipe, self.triagem)
                self.assertEqual(self.decisao(chamado).alteracoes['motivo_triagem'], 'sem_tecnico_ativo')

    def test_destino_sem_integrantes_usa_triagem(self):
        IntegranteEquipe.objects.filter(equipe=self.rede).delete()
        self.abrir()
        self.assertEqual(Chamado.objects.latest('pk').equipe, self.triagem)

    def test_triagem_recebe_mesmo_sem_integrantes(self):
        self.assertFalse(self.triagem.vinculos.exists())
        self.abrir('Outros')
        chamado = Chamado.objects.latest('pk')
        self.assertEqual(chamado.equipe, self.triagem)
        self.assertEqual(self.decisao(chamado).alteracoes['modo'], 'categoria')

    def test_alteracao_auditada_afeta_so_novos_chamados(self):
        self.abrir()
        antigo = Chamado.objects.latest('pk')
        IntegranteEquipe.objects.create(equipe=self.n2, usuario=self.tecnico)
        self.client.force_login(self.admin)
        resposta = self.client.post(self.editar, self.dados(equipe=self.n2.pk, categoria='Acessos'))
        self.assertRedirects(resposta, self.lista)
        self.regra.refresh_from_db()
        self.assertEqual(self.regra.categoria, 'Rede')
        self.assertEqual(self.regra.versao, 1)
        evento = RegistroAuditoria.objects.get(objeto='helpdesk.regraencaminhamento', objeto_id=self.regra.pk)
        self.assertEqual(evento.ator, self.admin)
        self.assertEqual(evento.alteracoes['equipe_id'], {'antes': self.rede.pk, 'depois': self.n2.pk})
        self.abrir()
        novo = Chamado.objects.latest('pk')
        self.assertEqual(novo.equipe, self.n2)
        antigo.refresh_from_db()
        self.assertEqual(antigo.equipe, self.rede)
        self.assertEqual(self.decisao(novo).alteracoes['versao_regra'], 1)

    def test_coordenador_e_cliente_nao_gerenciam_regras(self):
        for usuario in (self.tecnico, self.cliente):
            self.client.force_login(usuario)
            for url in (self.lista, self.editar, reverse('criar_regra_encaminhamento')):
                self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(self.editar, self.dados()).status_code, 403)
        self.assertEqual(Client().get(self.lista).status_code, 302)

    def test_csrf_e_get_sem_alteracao(self):
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.admin)
        self.assertEqual(protegido.post(self.editar, self.dados()).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.editar).status_code, 200)
        self.assertEqual(self.client.delete(self.editar).status_code, 405)
        self.regra.refresh_from_db()
        self.assertEqual(self.regra.versao, 0)

    def test_edicao_antiga_rejeitada(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.editar, self.dados(equipe=self.n2.pk)).status_code, 302)
        self.assertEqual(self.client.post(self.editar, self.dados()).status_code, 409)
        self.regra.refresh_from_db()
        self.assertEqual(self.regra.equipe, self.n2)
        self.assertEqual(RegistroAuditoria.objects.filter(objeto='helpdesk.regraencaminhamento').count(), 1)

    def test_regra_alterada_durante_abertura_usa_triagem(self):
        original = Equipe.objects.select_for_update

        def alterar_antes_do_bloqueio():
            RegraEncaminhamento.objects.filter(pk=self.regra.pk).update(versao=1, equipe=self.n2)
            return original()

        with patch('helpdesk.encaminhamento.Equipe.objects.select_for_update', side_effect=alterar_antes_do_bloqueio):
            self.abrir()
        chamado = Chamado.objects.latest('pk')
        self.assertEqual(chamado.equipe, self.triagem)
        self.assertEqual(self.decisao(chamado).alteracoes['motivo_triagem'], 'regra_alterada')

    def test_destino_desativado_apos_validacao_do_formulario_nao_e_salvo(self):
        original = Equipe.objects.select_for_update

        def desativar_antes_do_bloqueio():
            Equipe.objects.filter(pk=self.rede.pk).update(ativa=False)
            return original()

        self.client.force_login(self.admin)
        with patch('helpdesk.regras_encaminhamento.Equipe.objects.select_for_update', side_effect=desativar_antes_do_bloqueio):
            resposta = self.client.post(self.editar, self.dados())
        self.assertTrue(resposta.context['form'].errors)
        self.regra.refresh_from_db()
        self.assertEqual(self.regra.versao, 0)

    def test_categoria_unica_e_valida(self):
        self.client.force_login(self.admin)
        for categoria in ('Rede', 'Inexistente'):
            resposta = self.client.post(reverse('criar_regra_encaminhamento'), self.dados(categoria=categoria))
            self.assertTrue(resposta.context['form'].errors)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RegraEncaminhamento.objects.create(categoria='Rede', equipe=self.rede)

    def test_cria_regra_ausente_com_auditoria(self):
        self.regra.delete()
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.lista), 'Nova regra')
        self.assertEqual(self.client.post(reverse('criar_regra_encaminhamento'), self.dados()).status_code, 302)
        regra = RegraEncaminhamento.objects.get(categoria='Rede')
        self.assertEqual(regra.versao, 1)
        self.assertTrue(RegistroAuditoria.objects.filter(objeto='helpdesk.regraencaminhamento', objeto_id=regra.pk, acao='criado').exists())

    def test_regra_ativa_nao_pode_ser_salva_com_destino_inativo(self):
        self.rede.ativa = False
        self.rede.save()
        self.client.force_login(self.admin)
        resposta = self.client.post(self.editar, self.dados())
        self.assertTrue(resposta.context['form'].errors)
        self.assertEqual(self.client.post(self.editar, self.dados(ativa='')).status_code, 302)
        self.regra.refresh_from_db()
        self.assertFalse(self.regra.ativa)

    def test_lista_mostra_quando_destino_vai_usar_triagem(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(self.lista)
        regra_n2 = next(r for r in resposta.context['regras'] if r.categoria == 'Hardware')
        self.assertFalse(regra_n2.tem_tecnico)
        self.assertContains(resposta, 'Sem técnico ativo — usará triagem')

    def test_falha_auditoria_reverte_criacao_do_chamado(self):
        total = RegistroAuditoria.objects.count()
        with patch('helpdesk.encaminhamento.registrar', side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):
                self.abrir()
        self.assertFalse(Chamado.objects.exists())
        self.assertEqual(RegistroAuditoria.objects.count(), total)

    def test_falha_auditoria_reverte_configuracao(self):
        self.client.force_login(self.admin)
        with patch('helpdesk.regras_encaminhamento.registrar', side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):
                self.client.post(self.editar, self.dados(equipe=self.n2.pk))
        self.regra.refresh_from_db()
        self.assertEqual(self.regra.equipe, self.rede)
        self.assertEqual(self.regra.versao, 0)

    def test_django_admin_cria_com_rota_e_nao_reencaminha_edicao_existente(self):
        self.client.force_login(self.admin)
        dados = {'titulo': 'Criado pelo admin', 'descricao': 'Fixture', 'categoria': 'Rede',
                 'prioridade': 'Normal', 'solicitante': self.cliente.pk, '_save': 'Salvar'}
        resposta = self.client.post(reverse('admin:helpdesk_chamado_add'), dados)
        self.assertEqual(resposta.status_code, 302)
        chamado = Chamado.objects.get(titulo=dados['titulo'])
        self.assertEqual(chamado.equipe, self.rede)
        self.assertEqual(self.decisao(chamado).origem, 'admin')
        self.assertEqual(self.decisao(chamado).ator, self.admin)
        dados['categoria'] = 'Outros'
        self.assertEqual(self.client.post(reverse('admin:helpdesk_chamado_change', args=[chamado.pk]), dados).status_code, 302)
        chamado.refresh_from_db()
        self.assertEqual(chamado.equipe, self.rede)
        self.assertEqual(RegistroAuditoria.objects.filter(objeto_id=chamado.pk, objeto='helpdesk.chamado', acao='encaminhado').count(), 1)

    def test_transferencia_manual_nao_e_desfeita_pela_regra(self):
        self.abrir()
        chamado = Chamado.objects.latest('pk')
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('redistribuir_chamado', args=[chamado.pk]), {
            **dados_atribuicao(chamado), 'equipe': self.n2.pk, 'tecnico': '', 'responsavel_anterior': '',
            'motivo': 'Encaminhamento manual',
        }).status_code, 302)
        chamado.refresh_from_db()
        self.assertEqual(chamado.equipe, self.n2)

    def test_admin_das_regras_e_somente_consulta(self):
        registro = admin.site._registry[RegraEncaminhamento]
        self.assertFalse(registro.has_add_permission(None))
        self.assertFalse(registro.has_change_permission(None))
        self.assertFalse(registro.has_delete_permission(None))
