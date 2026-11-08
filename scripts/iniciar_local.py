"""Inicialização local supervisionada; sem instalação ou migração automática."""
import argparse
from contextlib import contextmanager
import errno
import importlib.util
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = sys.platform == 'win32'
WINDOWS_BOOTSTRAP = (
    'import runpy,signal; '
    'signal.signal(signal.SIGBREAK,signal.default_int_handler); '
    'runpy.run_path("manage.py",run_name="__main__")'
)


class ErroInicializacao(Exception):
    pass


@contextmanager
def execucao_exclusiva(path):
    # O lock é liberado pelo sistema se o processo morrer. O arquivo permanece:
    # removê-lo permitiria que outros processos bloqueassem arquivos diferentes.
    arquivo = path.open('a+b')
    bloqueado = False
    try:
        arquivo.seek(0, os.SEEK_END)
        if arquivo.tell() == 0:
            arquivo.write(b'0'); arquivo.flush()
        arquivo.seek(0)
        try:
            if WINDOWS:
                import msvcrt
                msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            bloqueado = True
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise ErroInicializacao('Já existe um inicializador nesta pasta. Encerre-o com Ctrl+C.') from error
            raise
        yield
    finally:
        if bloqueado:
            arquivo.seek(0)
            if WINDOWS:
                import msvcrt
                msvcrt.locking(arquivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(arquivo.fileno(), fcntl.LOCK_UN)
        arquivo.close()


def verificar_porta(porta):
    mensagem = f'A porta {porta} está ocupada ou indisponível. Encerre o portal antigo ou use --porta 8001.'
    if WINDOWS:
        # SO_REUSEADDR permite reiniciar após conexões em TIME_WAIT no Windows;
        # confira antes se já existe um serviço escutando nessa porta.
        try:
            conexao = socket.create_connection(('127.0.0.1', porta), timeout=.3)
        except OSError:
            pass
        else:
            conexao.close()
            raise ErroInicializacao(mensagem)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', porta))
    except OSError as error:
        raise ErroInicializacao(mensagem) from error


def verificar_ambiente():
    esperado = tuple(map(int, (ROOT / '.python-version').read_text().strip().split('.')))
    if sys.version_info[:len(esperado)] != esperado:
        raise ErroInicializacao('Use o Python 3.12 no ambiente .venv. Consulte docs/inicializacao-windows.md.')
    if Path(sys.prefix).resolve() != (ROOT / '.venv').resolve():
        raise ErroInicializacao('Execute pelo iniciar-portal.cmd, usando o Python da .venv deste projeto.')
    if importlib.util.find_spec('django') is None:
        raise ErroInicializacao('Django não instalado. Execute: .venv\\Scripts\\python.exe -m pip install -r requirements.txt')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    if os.environ['DJANGO_SETTINGS_MODULE'] == 'core.settings_production':
        raise ErroInicializacao('Este inicializador é de desenvolvimento local. Use a implantação Docker em produção.')
    sys.path.insert(0, str(ROOT))
    from django.conf import settings
    if not settings.DEBUG:
        raise ErroInicializacao('Este inicializador exige a configuração local com DEBUG ativo.')
    verificacoes = [
        ([sys.executable, '-m', 'pip', 'check'], 'Dependências inconsistentes. Reinstale requirements.txt na .venv.'),
        ([sys.executable, 'manage.py', 'check', '--fail-level', 'WARNING'],
         'A configuração do portal precisa de correção. Confira o erro acima.'),
        ([sys.executable, 'manage.py', 'migrate', '--check', '--noinput'],
         'Há migrações pendentes. Faça backup e execute: .venv\\Scripts\\python.exe manage.py migrate'),
    ]
    for comando, mensagem in verificacoes:
        if subprocess.run(comando, cwd=ROOT).returncode:
            raise ErroInicializacao(mensagem)


def iniciar_processo(argumentos):
    if WINDOWS:
        comando = [sys.executable, '-u', '-c', WINDOWS_BOOTSTRAP, *argumentos]
        opcoes = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        comando = [sys.executable, '-u', 'manage.py', *argumentos]
        opcoes = {'start_new_session': True}
    return subprocess.Popen(comando, cwd=ROOT, **opcoes)


def aguardar_portal(processo, porta, timeout=30):
    # A verificação é exclusivamente no loopback local, sem proxy de saída.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if processo.poll() is not None:
            raise ErroInicializacao('O portal encerrou durante a inicialização. Confira o erro acima.')
        try:
            with opener.open(f'http://127.0.0.1:{porta}/contas/login/', timeout=1) as resposta:
                if resposta.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(.2)
    raise ErroInicializacao('O portal não ficou pronto em 30 segundos. Confira o erro acima.')


def encerrar(processo):
    if processo.poll() is not None:
        return
    try:
        if WINDOWS:
            processo.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(processo.pid, signal.SIGINT)
    except OSError:
        try:
            processo.terminate()
        except OSError:
            pass
    try:
        processo.wait(timeout=8)
    except subprocess.TimeoutExpired:
        if WINDOWS:
            processo.kill()
        else:
            try:
                os.killpg(processo.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        processo.wait(timeout=5)


def supervisionar(porta):
    processos = []
    try:
        portal = iniciar_processo(['runserver', f'127.0.0.1:{porta}', '--noreload'])
        processos.append(('Portal', portal))
        aguardar_portal(portal, porta)
        alertas = iniciar_processo(['processar_alertas_sla', '--continuo'])
        processos.append(('Alertas', alertas))
        print(f'Serviços iniciados: portal PID={portal.pid}; alertas PID={alertas.pid}.', flush=True)
        print(f'Abra http://127.0.0.1:{porta}/ — Ctrl+C encerra os dois serviços.', flush=True)
        while True:
            for nome, processo in processos:
                codigo = processo.poll()
                if codigo is not None:
                    raise ErroInicializacao(f'{nome} encerrou (código {codigo}). Os dois serviços serão parados.')
            time.sleep(.25)
    except KeyboardInterrupt:
        print('\nEncerrando portal e alertas...', flush=True)
        return 0
    finally:
        # Para somente os filhos iniciados nesta execução, em ordem inversa.
        # Um segundo Ctrl+C não deve interromper a limpeza do outro serviço.
        sinais = [signal.SIGINT] + ([signal.SIGBREAK] if WINDOWS else [])
        anteriores = {sinal: signal.signal(sinal, signal.SIG_IGN) for sinal in sinais}
        falhas = []
        try:
            for nome, processo in reversed(processos):
                try:
                    encerrar(processo)
                except (OSError, subprocess.TimeoutExpired):
                    falhas.append(nome)
        finally:
            for sinal, handler in anteriores.items():
                signal.signal(sinal, handler)
        if falhas:
            raise ErroInicializacao('Não foi possível encerrar: '+', '.join(falhas)+'. Confira os processos locais.')
        print('Portal e alertas encerrados.', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Inicia o portal e os alertas em um único terminal local.')
    parser.add_argument('--porta', type=int, default=8000, help='Porta local do portal (padrão 8000).')
    parser.add_argument('--verificar', action='store_true', help='Verifica o ambiente sem iniciar serviços.')
    args = parser.parse_args(argv)
    if not 1 <= args.porta <= 65535:
        parser.error('A porta deve estar entre 1 e 65535.')
    if WINDOWS:
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    try:
        with execucao_exclusiva(ROOT / '.portal-local.lock'):
            verificar_porta(args.porta)
            print('Verificando o ambiente local...', flush=True)
            verificar_ambiente()
            if args.verificar:
                print('Ambiente pronto. Nenhum serviço foi iniciado.', flush=True)
                return 0
            return supervisionar(args.porta)
    except KeyboardInterrupt:
        print('\nInicialização cancelada.', flush=True)
        return 0
    except (ErroInicializacao, OSError) as error:
        print(f'Não foi possível iniciar: {error}', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
