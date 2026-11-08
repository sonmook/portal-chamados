from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
import signal
import subprocess
import tempfile
from unittest import TestCase
from unittest.mock import Mock, patch
from scripts import iniciar_local as local


class InicializacaoLocalTests(TestCase):
    def setUp(self):
        local.os.environ.setdefault('DJANGO_SETTINGS_MODULE','core.settings')
        from django.conf import settings
        debug=patch.object(settings,'DEBUG',True)
        debug.start();self.addCleanup(debug.stop)
        self.output=StringIO()
        self.addCleanup(self.output.close)
        self.stdout=redirect_stdout(self.output);self.stdout.__enter__()
        self.addCleanup(self.stdout.__exit__,None,None,None)

    def test_trava_impede_duplicacao_e_libera_apos_erro_sem_apagar_arquivo(self):
        with tempfile.TemporaryDirectory(prefix='portal com espacos ') as tmp:
            path=Path(tmp)/'.portal-local.lock'
            with local.execucao_exclusiva(path):
                with self.assertRaises(local.ErroInicializacao):
                    with local.execucao_exclusiva(path):pass
            with self.assertRaises(RuntimeError):
                with local.execucao_exclusiva(path):raise RuntimeError('fixture')
            with local.execucao_exclusiva(path):self.assertTrue(path.exists())

    def test_porta_ocupada_tem_mensagem_e_nao_encerra_outros_processos(self):
        with patch.object(local.socket,'socket',side_effect=OSError('ocupada')), patch.object(local,'encerrar') as parar:
            with self.assertRaisesRegex(local.ErroInicializacao,'8000'):
                local.verificar_porta(8000)
            parar.assert_not_called()

    def test_python_ou_ambiente_incorreto_falha_antes_de_executar_servicos(self):
        with patch.object(local.sys,'version_info',(99,0,0)):
            with self.assertRaisesRegex(local.ErroInicializacao,'Python 3.12'):local.verificar_ambiente()
        with patch.object(local.sys,'prefix',str(local.ROOT/'fora-da-venv')):
            with self.assertRaisesRegex(local.ErroInicializacao,'.venv'):local.verificar_ambiente()

    def test_falta_django_mostra_comando_de_instalacao(self):
        with patch.object(local.importlib.util,'find_spec',return_value=None):
            with self.assertRaisesRegex(local.ErroInicializacao,'pip install'):local.verificar_ambiente()

    def test_configuracao_producao_e_bloqueada(self):
        with patch.dict(local.os.environ,{'DJANGO_SETTINGS_MODULE':'core.settings_production'}):
            with self.assertRaisesRegex(local.ErroInicializacao,'desenvolvimento local'):local.verificar_ambiente()

    def test_debug_desativado_impede_inicializacao_local(self):
        from django.conf import settings
        with patch.object(settings,'DEBUG',False):
            with self.assertRaisesRegex(local.ErroInicializacao,'DEBUG ativo'):local.verificar_ambiente()

    def test_migracoes_pendentes_impedem_inicio_sem_migrar_automaticamente(self):
        with patch.object(local.subprocess,'run',side_effect=[Mock(returncode=0),Mock(returncode=0),Mock(returncode=1)]) as run:
            with self.assertRaisesRegex(local.ErroInicializacao,'Faça backup'):local.verificar_ambiente()
            for call in run.call_args_list:
                cmd=call.args[0]
                if 'migrate' in cmd:self.assertIn('--check',cmd)

    def test_dependencias_inconsistentes_bloqueiam_checks_seguintes(self):
        with patch.object(local.subprocess,'run',return_value=Mock(returncode=1)) as run:
            with self.assertRaisesRegex(local.ErroInicializacao,'Dependências'):local.verificar_ambiente()
            self.assertEqual(run.call_count,1)

    def test_aguarda_portal_antes_de_iniciar_alertas_e_ctrl_c_para_os_dois(self):
        web=Mock(pid=101);alertas=Mock(pid=102)
        web.poll.return_value=None;alertas.poll.return_value=None
        eventos=[]
        def aguardar(*args):eventos.append('pronto')
        def criar(args):
            eventos.append(args[0]);return web if args[0]=='runserver' else alertas
        with patch.object(local,'iniciar_processo',side_effect=criar), patch.object(local,'aguardar_portal',side_effect=aguardar), patch.object(local.time,'sleep',side_effect=KeyboardInterrupt), patch.object(local,'encerrar') as parar:
            self.assertEqual(local.supervisionar(8000),0)
        self.assertEqual(eventos,['runserver','pronto','processar_alertas_sla'])
        self.assertEqual([c.args[0] for c in parar.call_args_list],[alertas,web])

    def test_portal_sem_saude_nao_inicia_alertas_e_e_encerrado(self):
        web=Mock(pid=101)
        with patch.object(local,'iniciar_processo',return_value=web) as criar, patch.object(local,'aguardar_portal',side_effect=local.ErroInicializacao('sem saude')), patch.object(local,'encerrar') as parar:
            with self.assertRaises(local.ErroInicializacao):local.supervisionar(8000)
        self.assertEqual(criar.call_count,1);parar.assert_called_once_with(web)

    def test_falha_ao_criar_segundo_processo_limpa_o_primeiro(self):
        web=Mock(pid=101)
        with patch.object(local,'iniciar_processo',side_effect=[web,OSError('fixture')]), patch.object(local,'aguardar_portal'), patch.object(local,'encerrar') as parar:
            with self.assertRaises(OSError):local.supervisionar(8000)
        parar.assert_called_once_with(web)

    def test_encerramento_inesperado_de_qualquer_servico_para_ambos(self):
        for falha in ('web','alertas'):
            web=Mock(pid=101);alertas=Mock(pid=102)
            web.poll.return_value=1 if falha=='web' else None
            alertas.poll.return_value=0 if falha=='alertas' else None
            with patch.object(local,'iniciar_processo',side_effect=[web,alertas]), patch.object(local,'aguardar_portal'), patch.object(local,'encerrar') as parar:
                with self.assertRaises(local.ErroInicializacao):local.supervisionar(8000)
            self.assertEqual(parar.call_count,2)

    def test_falha_na_limpeza_de_um_servico_nao_abandona_o_outro(self):
        web=Mock(pid=101);alertas=Mock(pid=102)
        web.poll.return_value=1
        with patch.object(local,'iniciar_processo',side_effect=[web,alertas]), patch.object(local,'aguardar_portal'), patch.object(local,'encerrar',side_effect=[OSError('fixture'),None]) as parar:
            with self.assertRaisesRegex(local.ErroInicializacao,'Alertas'):local.supervisionar(8000)
        self.assertEqual(parar.call_count,2)

    def test_encerramento_esgotado_forca_apenas_grupo_do_filho(self):
        processo=Mock(pid=123456);processo.poll.return_value=None
        processo.wait.side_effect=[subprocess.TimeoutExpired('fixture',8),0]
        kill=getattr(signal,'SIGKILL',9)
        with patch.object(local,'WINDOWS',False), patch.object(local.os,'killpg',create=True) as matar, patch.object(local.signal,'SIGKILL',kill,create=True):
            local.encerrar(processo)
        self.assertEqual([c.args for c in matar.call_args_list],[(123456,signal.SIGINT),(123456,kill)])

    def test_encerramento_windows_usa_break_e_fallback_somente_no_filho(self):
        processo=Mock(pid=123456);processo.poll.return_value=None
        processo.wait.side_effect=[subprocess.TimeoutExpired('fixture',8),0]
        with patch.object(local,'WINDOWS',True), patch.object(local.signal,'CTRL_BREAK_EVENT',1,create=True):
            local.encerrar(processo)
        processo.send_signal.assert_called_once_with(1);processo.kill.assert_called_once()

    def test_modo_verificar_nao_inicia_processos(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(local,'ROOT',Path(tmp)), patch.object(local,'verificar_porta'), patch.object(local,'verificar_ambiente'), patch.object(local,'supervisionar') as iniciar:
            self.assertEqual(local.main(['--verificar']),0)
        iniciar.assert_not_called()

    def test_portas_invalidas_sao_recusadas(self):
        for porta in ('0','65536','invalida'):
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):local.main(['--porta',porta])
