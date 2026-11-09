from io import StringIO
from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from .models import Chamado, Comentario, Equipe


@override_settings(DEBUG=True)
class DadosDemoTests(TestCase):
    def executar(self):
        saida = StringIO()
        call_command('criar_dados_demo', stdout=saida)
        return saida.getvalue()

    def test_cenarios_senhas_e_repeticao_preservam_edicoes(self):
        saida = self.executar()
        self.assertEqual(User.objects.filter(username__startswith='demo.').count(), 6)
        self.assertEqual(Chamado.objects.filter(titulo__startswith='[DEMO]').count(), 12)
        self.assertEqual(Comentario.objects.count(), 9)
        self.assertEqual(Equipe.objects.filter(nome__startswith='[DEMO]').count(), 3)
        for linha in saida.splitlines():
            if linha.startswith('Usuário:'):
                login, senha = linha.removeprefix('Usuário: ').split(' | Senha: ')
                self.assertTrue(User.objects.get(username=login).check_password(senha))
        usuario = User.objects.get(username='demo.lucas')
        senha_original = usuario.password
        usuario.first_name = 'Nome editado'
        usuario.save()
        chamado = Chamado.objects.filter(titulo__startswith='[DEMO]').first()
        chamado.status = 'Fechado'
        chamado.save()
        self.assertIn('0 novos usuários e 0 novos chamados', self.executar())
        usuario.refresh_from_db()
        chamado.refresh_from_db()
        self.assertEqual(usuario.password, senha_original)
        self.assertEqual(usuario.first_name, 'Nome editado')
        self.assertEqual(chamado.status, 'Fechado')
        self.assertFalse(User.objects.filter(username__startswith='demo.', is_superuser=True).exists())
        self.assertEqual(Comentario.objects.count(), 9)

    @override_settings(DEBUG=False)
    def test_producao_bloqueada(self):
        with self.assertRaises(CommandError):
            self.executar()
        self.assertFalse(User.objects.filter(username__startswith='demo.').exists())

    def test_colisao_nao_altera_cadastro_nem_cria_outros(self):
        usuario = User.objects.create_user('demo.julia', email='existente@example.com', password='original')
        with self.assertRaises(CommandError):
            self.executar()
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password('original'))
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(Chamado.objects.exists())
