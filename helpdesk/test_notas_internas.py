import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models.query import QuerySet
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .acesso import comentarios_acessiveis
from .forms import NotaInternaForm
from .models import (Chamado, Comentario, Equipe, HistoricoStatus, IntegranteEquipe,
    Notificacao, RegistroAuditoria)
from .notificacoes import gerar, notificar_resposta, notificacoes_visiveis
from .test_helpers import dados_atribuicao, dados_situacao, restaurar_migracoes_atuais


class NotasInternasTests(TestCase):
    def setUp(self):
        self.midia = tempfile.TemporaryDirectory()
        self.addCleanup(self.midia.cleanup)
        configuracao = override_settings(MEDIA_ROOT=self.midia.name)
        configuracao.enable()
        self.addCleanup(configuracao.disable)
        self.cliente = User.objects.create_user('cliente-notas')
        self.alheio = User.objects.create_user('alheio-notas')
        self.tecnico = User.objects.create_user('responsavel-notas', is_staff=True)
        self.colega = User.objects.create_user('colega-notas', is_staff=True)
        self.coordenador = User.objects.create_user('coordenador-notas', is_staff=True)
        self.externo = User.objects.create_user('tecnico-externo-notas', is_staff=True)
        self.admin = User.objects.create_superuser('admin-notas', password=None)
        self.equipe = Equipe.objects.get(triagem_padrao=True)
        for usuario in (self.tecnico, self.colega, self.coordenador):
            IntegranteEquipe.objects.create(usuario=usuario, equipe=self.equipe,
                coordenador=usuario == self.coordenador)
        self.destino = Equipe.objects.create(nome='Equipe de destino das notas')
        IntegranteEquipe.objects.create(usuario=self.externo, equipe=self.destino)
        self.ticket = Chamado.objects.create(titulo='Chamado com colaboração interna', descricao='Conversa pública',
            solicitante=self.cliente, tecnico=self.tecnico, equipe=self.equipe,
            status='Aguardando solicitante', motivo_espera='Aguardando retorno público', espera_desde=timezone.now(),
            data_vencimento=timezone.now()+timedelta(hours=4))
        self.url = reverse('adicionar_nota_interna', args=[self.ticket.pk])
        self.detalhes = reverse('detalhes_chamado', args=[self.ticket.pk])
        self.client.force_login(self.colega)

    def dados(self, **extra):
        return {'nota-texto': 'Diagnóstico interno reservado.', **{
            'nota-'+campo: valor for campo, valor in dados_situacao(self.ticket).items()}, **extra}

    def salvar(self, **extra):
        return self.client.post(self.url, self.dados(**extra))

    def criar_nota(self, **extra):
        self.assertEqual(self.salvar(**extra).status_code, 302)
        return Comentario.objects.filter(chamado=self.ticket, interna=True).latest('pk')

    def pdf(self):
        return SimpleUploadedFile('diagnostico-reservado.pdf', b'%PDF-1.7\nfixture interna')

    def test_membro_coordenador_responsavel_e_admin_podem_colaborar(self):
        for autor in (self.colega, self.coordenador, self.tecnico, self.admin):
            self.client.force_login(autor)
            nota = self.criar_nota()
            self.assertEqual(nota.autor, autor)
            self.assertTrue(nota.interna)
        self.assertEqual(self.ticket.comentarios.count(), 4)

    def test_solicitante_e_tecnico_de_outra_equipe_nao_criam_notas(self):
        for autor, codigo in ((self.cliente, 403), (self.alheio, 404), (self.externo, 404)):
            self.client.force_login(autor)
            self.assertEqual(self.salvar().status_code, codigo)
        self.assertFalse(Comentario.objects.exists())

    def test_staff_solicitante_sem_vinculo_nao_ganha_acesso_interno(self):
        nota = self.criar_nota(**{'nota-anexo': self.pdf()})
        Chamado.objects.filter(pk=self.ticket.pk).update(solicitante=self.externo)
        self.client.force_login(self.externo)
        r = self.client.get(self.detalhes)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, nota.texto)
        self.assertNotContains(r, 'Adicionar nota interna')
        self.assertEqual(self.salvar().status_code, 403)
        self.assertEqual(self.client.get(reverse('baixar_anexo_comentario', args=[self.ticket.pk, nota.pk])).status_code, 404)

    def test_staff_solicitante_com_vinculo_mantem_permissao_tecnica(self):
        Chamado.objects.filter(pk=self.ticket.pk).update(solicitante=self.colega)
        nota = self.criar_nota()
        self.assertContains(self.client.get(self.detalhes), nota.texto)
        self.assertFalse(Notificacao.objects.filter(destinatario=self.colega).exists())

    def test_get_login_e_csrf_sao_obrigatorios(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        seguro = Client(enforce_csrf_checks=True)
        seguro.force_login(self.colega)
        self.assertEqual(seguro.post(self.url, self.dados()).status_code, 403)
        self.client.logout()
        self.assertEqual(self.salvar().status_code, 302)
        self.assertFalse(Comentario.objects.exists())

    def test_solicitante_nao_recebe_texto_marcador_ou_link_do_anexo(self):
        nota = self.criar_nota(**{'nota-anexo': self.pdf()})
        self.client.force_login(self.cliente)
        r = self.client.get(self.detalhes)
        self.assertEqual(list(r.context['comentarios']), [])
        self.assertNotContains(r, nota.texto)
        self.assertNotContains(r, 'Nota interna · TI')
        self.assertNotContains(r, 'Adicionar nota interna')
        self.assertNotContains(r, reverse('baixar_anexo_comentario', args=[self.ticket.pk, nota.pk]))
        self.assertContains(r, 'Nenhum comentário adicionado ainda.')

    def test_membros_e_admin_veem_identificacao_privada_e_texto_escapado(self):
        nota = self.criar_nota(**{'nota-texto': '<script>alert("interno")</script>', 'nota-anexo': self.pdf()})
        for usuario in (self.tecnico, self.colega, self.coordenador, self.admin):
            self.client.force_login(usuario)
            r = self.client.get(self.detalhes)
            self.assertContains(r, '&lt;script&gt;')
            self.assertNotContains(r, '<script>alert(')
            self.assertContains(r, 'Nota interna · TI')
            self.assertContains(r, 'Baixar anexo privado')
            self.assertEqual(list(r.context['comentarios']), [nota])

    def test_anexo_exige_acesso_interno_mesmo_conhecendo_id(self):
        nota = self.criar_nota(**{'nota-anexo': self.pdf()})
        url = reverse('baixar_anexo_comentario', args=[self.ticket.pk, nota.pk])
        for usuario, codigo in ((self.cliente, 404), (self.externo, 404),
                (self.colega, 200), (self.tecnico, 200), (self.admin, 200)):
            self.client.force_login(usuario)
            r = self.client.get(url)
            self.assertEqual(r.status_code, codigo)
            if codigo == 200:
                self.assertEqual(b''.join(r.streaming_content), b'%PDF-1.7\nfixture interna')
                self.assertEqual(r['Cache-Control'], 'private, no-store')
                self.assertEqual(r['X-Content-Type-Options'], 'nosniff')
                self.assertIn('attachment;', r['Content-Disposition'])
        outro = Chamado.objects.create(titulo='Outro chamado', descricao='Fixture', solicitante=self.cliente)
        self.assertEqual(self.client.get(reverse('baixar_anexo_comentario', args=[outro.pk, nota.pk])).status_code, 404)

    def test_nota_nao_altera_dados_prazo_espera_interacao_ou_historico(self):
        antes = Chamado.objects.filter(pk=self.ticket.pk).values().get()
        self.criar_nota()
        self.assertEqual(Chamado.objects.filter(pk=self.ticket.pk).values().get(), antes)
        self.assertFalse(HistoricoStatus.objects.exists())

    def test_nota_do_solicitante_com_papel_tecnico_nao_retoma_espera(self):
        Chamado.objects.filter(pk=self.ticket.pk).update(solicitante=self.colega)
        self.criar_nota()
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'Aguardando solicitante')
        self.assertIsNone(self.ticket.ultima_interacao_em)

    def test_resposta_publica_permanece_publica_e_retoma_normalmente(self):
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.post(self.detalhes, {'texto': 'Retorno público', 'interna': 'true'}).status_code, 302)
        comentario = Comentario.objects.get()
        self.assertFalse(comentario.interna)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'Em Andamento')
        self.assertIsNotNone(self.ticket.ultima_interacao_em)
        self.assertContains(self.client.get(self.detalhes), 'Retorno público')

    def test_servidor_define_autor_chamado_e_classificacao(self):
        self.assertNotIn('interna', NotaInternaForm().fields)
        nota = self.criar_nota(interna='false', autor=self.cliente.pk, chamado=999999)
        self.assertEqual((nota.autor, nota.chamado, nota.interna), (self.colega, self.ticket, True))

    def test_formulario_tem_ids_distintos_e_limites_de_anexo(self):
        self.client.force_login(self.tecnico)
        r = self.client.get(self.detalhes)
        self.assertContains(r, 'id="id_texto"', count=1)
        self.assertContains(r, 'id="id_nota-texto"', count=1)
        self.assertContains(r, f'action="{self.url}"')
        self.assertContains(r, 'PNG, JPEG ou PDF de até 10 MB.')

    def test_texto_vazio_ou_anexo_invalido_nao_gravam_nota(self):
        antes = RegistroAuditoria.objects.count()
        for texto in ('', '  \n '):
            self.assertEqual(self.salvar(**{'nota-texto': texto}).status_code, 400)
        texto = 'Diagnóstico <script>reservado</script>'
        r = self.salvar(**{'nota-texto': texto, 'nota-anexo': SimpleUploadedFile('erro.pdf', b'<html>')})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.context['nota_form']['texto'].value(), texto)
        self.assertIn('anexo', r.context['nota_form'].errors)
        self.assertContains(r, '&lt;script&gt;', status_code=400)
        self.assertContains(r, 'A nota não foi gravada.', status_code=400)
        self.assertContains(r, ' open>', status_code=400)
        self.assertFalse(Comentario.objects.exists())
        self.assertFalse(Notificacao.objects.exists())
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_versoes_obrigatorias_e_telas_antigas_rejeitadas(self):
        self.assertEqual(self.client.post(self.url, {'nota-texto': 'Sem versões'}).status_code, 400)
        for campo in ('nota-versao_status', 'nota-versao_atribuicao'):
            r = self.salvar(**{campo: 999})
            self.assertEqual(r.status_code, 409)
            self.assertContains(r, 'Carregar os dados atuais', status_code=409)
        self.assertFalse(Comentario.objects.exists())

    def test_conflito_condicional_nao_cria_conteudo_ou_aviso(self):
        original = QuerySet.update
        def disputar(qs, **campos):
            return 0 if qs.model is Chamado and set(campos) == {'versao_status'} else original(qs, **campos)
        antes = RegistroAuditoria.objects.count()
        with patch.object(QuerySet, 'update', disputar):
            self.assertEqual(self.salvar().status_code, 409)
        self.assertFalse(Comentario.objects.exists())
        self.assertFalse(Notificacao.objects.exists())
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_falha_no_aviso_reverte_nota_e_auditoria(self):
        antes = RegistroAuditoria.objects.count()
        with patch('helpdesk.views.notificar_resposta', side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError):
                self.salvar()
        self.assertFalse(Comentario.objects.exists())
        self.assertFalse(Notificacao.objects.exists())
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_finalizados_e_equipes_inativas_recusam_novas_notas(self):
        for status in ('Resolvido', 'Fechado'):
            Chamado.objects.filter(pk=self.ticket.pk).update(status=status)
            self.assertEqual(self.salvar().status_code, 403)
            self.assertNotContains(self.client.get(self.detalhes), 'Adicionar nota interna')
        Chamado.objects.filter(pk=self.ticket.pk).update(status='Aberto')
        Equipe.objects.filter(pk=self.equipe.pk).update(ativa=False)
        self.client.force_login(self.admin)
        self.assertEqual(self.salvar().status_code, 403)

    def test_somente_responsavel_recebe_aviso_interno_sem_copia_de_texto(self):
        nota = self.criar_nota()
        aviso = Notificacao.objects.get()
        self.assertEqual((aviso.tipo, aviso.destinatario), ('nota_interna', self.tecnico))
        self.assertNotIn(nota.texto, str(list(Notificacao.objects.values())))
        notificar_resposta(nota)
        self.assertEqual(Notificacao.objects.count(), 1)
        self.assertFalse(Notificacao.objects.filter(destinatario=self.cliente).exists())

    def test_ramo_de_notificacao_usa_classificacao_persistida(self):
        nota = self.criar_nota()
        nota.interna = False
        notificar_resposta(nota)
        self.assertFalse(Notificacao.objects.filter(tipo='resposta').exists())
        self.assertEqual(Notificacao.objects.count(), 1)

    def test_gerador_nao_envia_aviso_interno_ao_solicitante_ou_sem_acesso(self):
        total = gerar(self.ticket, self.colega.pk, 'nota_interna', 'teste-nota-filtro',
            {self.cliente.pk, self.externo.pk, self.tecnico.pk})
        self.assertEqual(total, 1)
        self.assertEqual(Notificacao.objects.get().destinatario, self.tecnico)

    def test_sem_responsavel_avisa_coordenacao_e_sem_coordenacao_avisa_admin(self):
        Chamado.objects.filter(pk=self.ticket.pk).update(tecnico=None)
        self.criar_nota()
        self.assertTrue(Notificacao.objects.filter(destinatario=self.coordenador).exists())
        IntegranteEquipe.objects.filter(usuario=self.coordenador).update(coordenador=False)
        self.criar_nota()
        self.assertTrue(Notificacao.objects.filter(destinatario=self.admin).exists())
        self.assertFalse(Notificacao.objects.filter(destinatario=self.cliente).exists())

    def test_notificacao_persistida_indevida_fica_oculta_ao_solicitante(self):
        self.criar_nota()
        interno = Notificacao.objects.create(destinatario=self.cliente, chamado=self.ticket,
            tipo='nota_interna', evento='fixture-interna-indevida')
        publico = Notificacao.objects.create(destinatario=self.cliente, chamado=self.ticket,
            tipo='resposta', evento='fixture-publica')
        self.client.force_login(self.cliente)
        r = self.client.get(reverse('listar_notificacoes'))
        self.assertEqual(r.context['notificacoes_nao_lidas'], 1)
        self.assertEqual(list(r.context['page_obj']), [publico])
        self.assertNotContains(r, 'Nova nota interna')
        self.assertEqual(self.client.post(reverse('ler_notificacao', args=[interno.pk])).status_code, 404)
        self.client.post(reverse('ler_todas_notificacoes'))
        interno.refresh_from_db()
        publico.refresh_from_db()
        self.assertIsNone(interno.lida_em)
        self.assertIsNotNone(publico.lida_em)

    def test_remocao_de_vinculo_revoga_texto_anexo_e_avisos_mesmo_com_acesso_publico(self):
        Chamado.objects.filter(pk=self.ticket.pk).update(solicitante=self.tecnico)
        nota = self.criar_nota(**{'nota-anexo': self.pdf()})
        aviso = Notificacao.objects.create(destinatario=self.tecnico, chamado=self.ticket,
            tipo='nota_interna', evento='fixture-aviso-revogado')
        IntegranteEquipe.objects.filter(usuario=self.tecnico).delete()
        self.client.force_login(self.tecnico)
        r = self.client.get(self.detalhes)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, nota.texto)
        self.assertEqual(self.client.get(reverse('baixar_anexo_comentario', args=[self.ticket.pk, nota.pk])).status_code, 404)
        self.assertFalse(notificacoes_visiveis(self.tecnico).filter(pk=aviso.pk).exists())

    def test_rebaixamento_revoga_notas_mesmo_quando_usuario_continua_solicitante(self):
        Chamado.objects.filter(pk=self.ticket.pk).update(solicitante=self.colega)
        nota = self.criar_nota()
        User.objects.filter(pk=self.colega.pk).update(is_staff=False)
        self.client.force_login(self.colega)
        r = self.client.get(self.detalhes)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, nota.texto)
        self.assertEqual(self.salvar().status_code, 403)

    def test_equipe_inativa_revoga_notas_da_equipe_mas_admin_pode_consultar(self):
        Chamado.objects.filter(pk=self.ticket.pk).update(solicitante=self.colega)
        nota = self.criar_nota()
        Equipe.objects.filter(pk=self.equipe.pk).update(ativa=False)
        self.client.force_login(self.colega)
        r = self.client.get(self.detalhes)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, nota.texto)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.detalhes), nota.texto)
        self.assertNotContains(self.client.get(self.detalhes), 'Adicionar nota interna')

    def test_transferencia_revoga_antiga_equipe_e_libera_nova_sem_expor_ao_solicitante(self):
        Chamado.objects.filter(pk=self.ticket.pk).update(solicitante=self.colega)
        nota = self.criar_nota(**{'nota-anexo': self.pdf()})
        self.client.force_login(self.admin)
        r = self.client.post(reverse('redistribuir_chamado', args=[self.ticket.pk]), {
            **dados_atribuicao(self.ticket), 'equipe': self.destino.pk, 'tecnico': self.externo.pk,
            'responsavel_anterior': self.tecnico.pk, 'motivo': 'Análise especializada'})
        self.assertEqual(r.status_code, 302)
        self.client.force_login(self.colega)
        r = self.client.get(self.detalhes)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, nota.texto)
        self.client.force_login(self.externo)
        self.assertContains(self.client.get(self.detalhes), nota.texto)
        anexo = self.client.get(reverse('baixar_anexo_comentario', args=[self.ticket.pk, nota.pk]))
        self.assertEqual(anexo.status_code, 200)
        anexo.close()

    def test_admin_queryset_respeita_visibilidade_e_nao_permite_editar(self):
        nota = self.criar_nota()
        Chamado.objects.filter(pk=self.ticket.pk).update(solicitante=self.externo)
        modeladmin = admin.site._registry[Comentario]
        for usuario, visivel in ((self.externo, False), (self.tecnico, True), (self.admin, True)):
            request = RequestFactory().get('/admin/')
            request.user = usuario
            self.assertEqual(modeladmin.get_queryset(request).filter(pk=nota.pk).exists(), visivel)
            self.assertFalse(modeladmin.has_change_permission(request, nota))
            self.assertFalse(modeladmin.has_delete_permission(request, nota))

    def test_busca_nao_revela_texto_de_notas(self):
        self.criar_nota(**{'nota-texto': 'TERMO-INTERNO-EXCLUSIVO'})
        self.client.force_login(self.cliente)
        r = self.client.get(reverse('lista_chamados'), {'q': 'TERMO-INTERNO-EXCLUSIVO'})
        self.assertEqual(r.context['page_obj'].paginator.count, 0)

    def test_auditoria_identifica_classificacao_sem_texto_ou_nome_do_anexo(self):
        nota = self.criar_nota(**{'nota-anexo': self.pdf()})
        evento = RegistroAuditoria.objects.get(objeto='helpdesk.comentario', objeto_id=nota.pk, acao='criado')
        self.assertEqual(evento.alteracoes['interna']['depois'], True)
        self.assertNotIn(nota.texto, str(evento.alteracoes))
        self.assertNotIn('diagnostico-reservado', str(evento.alteracoes))

    def test_detalhe_e_erro_de_nota_nao_sao_armazenados_em_cache(self):
        self.criar_nota()
        for usuario in (self.tecnico, self.cliente):
            self.client.force_login(usuario)
            self.assertIn('no-store', self.client.get(self.detalhes)['Cache-Control'])
        self.client.force_login(self.colega)
        self.assertIn('no-store', self.salvar(**{'nota-texto': ''})['Cache-Control'])

    def test_consultas_nao_gravam_avisos_notas_ou_auditoria(self):
        self.criar_nota()
        antes = (Comentario.objects.count(), Notificacao.objects.count(), RegistroAuditoria.objects.count())
        self.client.get(self.detalhes)
        self.client.get(reverse('listar_notificacoes'))
        self.assertEqual((Comentario.objects.count(), Notificacao.objects.count(), RegistroAuditoria.objects.count()), antes)


class MigracaoNotasInternasTests(TransactionTestCase):
    def tearDown(self):
        restaurar_migracoes_atuais()
        super().tearDown()

    def test_migracao_mantem_comentarios_publicos_e_leituras_anteriores(self):
        anterior = ('helpdesk', '0028_reabertura_ciclos')
        alvo = ('helpdesk', '0029_notas_internas')
        executor = MigrationExecutor(connection)
        executor.migrate([anterior])
        apps = executor.loader.project_state([anterior]).apps
        usuario = apps.get_model('auth', 'User').objects.create(username='legado-notas')
        equipe, _ = apps.get_model('helpdesk', 'Equipe').objects.get_or_create(triagem_padrao=True,
            defaults={'nome': 'Triagem das notas', 'ativa': True})
        ticket = apps.get_model('helpdesk', 'Chamado').objects.create(titulo='Legado público', descricao='Preservar',
            solicitante=usuario, equipe=equipe, data_vencimento=timezone.now())
        c = apps.get_model('helpdesk', 'Comentario').objects.create(chamado=ticket, autor=usuario,
            texto='Resposta anterior pública', anexo='anexos_comentarios/legado.pdf')
        antes = apps.get_model('helpdesk', 'Comentario').objects.filter(pk=c.pk).values().get()
        aviso = apps.get_model('helpdesk', 'Notificacao').objects.create(destinatario=usuario, chamado=ticket,
            tipo='resposta', evento='aviso-legado-notas', lida_em=timezone.now())
        leitura = aviso.lida_em
        executor = MigrationExecutor(connection)
        executor.migrate([alvo])
        self.assertEqual(Comentario.objects.filter(pk=c.pk).values(*antes).get(), antes)
        self.assertFalse(Comentario.objects.get(pk=c.pk).interna)
        self.assertEqual(Notificacao.objects.get(pk=aviso.pk).lida_em, leitura)
        self.assertEqual(Notificacao.objects.count(), 1)
        self.assertEqual(list(comentarios_acessiveis(User.objects.get(pk=usuario.pk)).values_list('pk', flat=True)), [c.pk])
