from pathlib import Path
import subprocess
import tempfile
from unittest import TestCase
from scripts.resolve_release import resolve_release


class ResolveReleaseTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Release Test')
        self.git('config', 'user.email', 'test@example.invalid')

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, version, name):
        (self.repo / 'VERSION').write_text(version + '\n')
        (self.repo / 'history.txt').write_text(name)
        self.git('add', '.')
        self.git('commit', '-qm', name)
        return self.git('rev-parse', 'HEAD')

    def test_atual_resolve_head_sem_criar_tags(self):
        head = self.commit('1.4.0', 'atual')
        self.assertEqual(resolve_release('atual', self.repo),
            {'sha': head, 'version': '1.4.0', 'tag': 'v1.4.0', 'latest': 'true'})
        self.assertEqual(self.git('tag', '--list'), '')

    def test_historica_escolhe_ultimo_commit_130_e_preserva_main_e_tags(self):
        original = self.commit('1.2.0', 'perfil')
        self.git('tag', 'v1.2.0')
        self.commit('1.3.0', 'conquistas')
        historical = self.commit('1.3.0', 'icones')
        head = self.commit('1.4.0', 'catalogo')
        result = resolve_release('v1.3.0', self.repo)
        self.assertEqual(result, {'sha': historical, 'version': '1.3.0', 'tag': 'v1.3.0', 'latest': 'false'})
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(self.git('rev-parse', 'v1.2.0'), original)
        self.assertEqual(self.git('tag', '--list'), 'v1.2.0')

    def test_nao_escolhe_versao_de_branch_lateral(self):
        base = self.commit('1.2.0', 'base')
        self.git('checkout', '-qb', 'lateral')
        self.commit('1.3.0', 'apenas lateral')
        self.git('checkout', '-q', base)
        self.commit('1.4.0', 'main')
        with self.assertRaises(ValueError):
            resolve_release('v1.3.0', self.repo)

    def test_entrada_desconhecida_versao_invalida_e_historica_igual_sao_recusadas(self):
        self.commit('1.3.0', 'atual')
        for selection in ['v1.3.0', 'v1.2.0', '$(id)', '../main']:
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                resolve_release(selection, self.repo)
        self.commit('versao-invalida', 'invalida')
        with self.assertRaises(ValueError):
            resolve_release('atual', self.repo)
