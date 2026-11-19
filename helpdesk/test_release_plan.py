from pathlib import Path
import subprocess
import tempfile
from unittest import TestCase

from scripts.plan_releases import plan_releases


class ReleasePlanTests(TestCase):
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

    def commit(self, version, brand='Portal de TI'):
        (self.repo/'VERSION').write_text(version+'\n')
        notes = self.repo/'docs'/'releases'
        notes.mkdir(parents=True, exist_ok=True)
        (notes/f'v{version}.md').write_text(f'# {brand} v{version}\n\nNotas.\n')
        self.git('add', '.')
        self.git('commit', '-qm', version)
        return self.git('rev-parse', 'HEAD')

    def test_pendentes_usa_ordem_semantica_e_latest_somente_no_head_atual(self):
        self.commit('1.9.0')
        historical = self.commit('1.10.0')
        patch = self.commit('1.10.1')
        head = self.commit('1.15.0', 'Nexaltri')
        plan = plan_releases([{'tag_name': 'v1.9.0', 'draft': False}], repository=self.repo)
        self.assertEqual([(p['tag'], p['sha'], p['latest']) for p in plan],
            [('v1.10.0', historical, 'false'), ('v1.10.1', patch, 'false'), ('v1.15.0', head, 'true')])
        self.assertEqual(self.git('tag', '--list'), '')
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)

    def test_repetir_publicacao_nao_reescreve_versoes_existentes(self):
        self.commit('1.10.0')
        self.commit('1.15.0', 'Nexaltri')
        releases = [{'tag_name': 'v1.10.0'}, {'tag_name': 'v1.15.0'}]
        self.assertEqual(plan_releases(releases, repository=self.repo), [])
        self.assertEqual(plan_releases(releases, 'atual', self.repo), [])

    def test_tag_sem_release_e_reutilizada_sem_ser_movida(self):
        tagged = self.commit('1.10.0')
        self.git('tag', '-a', 'v1.10.0', '-m', 'original')
        (self.repo/'docs'/'ajuste.md').write_text('Ajuste posterior da documentação.')
        self.git('add', '.')
        self.git('commit', '-qm', 'docs')
        self.commit('1.15.0', 'Nexaltri')
        result = plan_releases([], 'v1.10.0', self.repo)
        self.assertEqual(result[0]['sha'], tagged)
        self.assertEqual(result[0]['latest'], 'false')
        self.assertEqual(self.git('rev-parse', 'v1.10.0^{commit}'), tagged)

    def test_recusa_tag_incompativel_rascunho_e_notas_divergentes(self):
        historical = self.commit('1.10.0')
        head = self.commit('1.15.0', 'Nexaltri')
        self.git('tag', 'v1.10.0', head)
        with self.assertRaisesRegex(ValueError, 'histórico principal'):
            plan_releases([], 'v1.10.0', self.repo)
        with self.assertRaisesRegex(ValueError, 'rascunho'):
            plan_releases([{'tag_name': 'v1.15.0', 'draft': True}], 'atual', self.repo)
        self.git('tag', '-d', 'v1.10.0')
        self.git('checkout', '-q', historical)
        (self.repo/'docs'/'releases'/'v1.10.0.md').write_text('# Versão errada\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'notas divergentes')
        with self.assertRaisesRegex(ValueError, 'Notas'):
            plan_releases([], 'atual', self.repo)

    def test_ignora_notas_futuras_e_recusa_entradas_invalidas(self):
        self.commit('1.15.0', 'Nexaltri')
        (self.repo/'docs'/'releases'/'v2.0.0.md').write_text('# Futuro\n')
        plan = plan_releases([], repository=self.repo)
        self.assertEqual([p['tag'] for p in plan], ['v1.15.0'])
        for value in ('../main', '$(id)', 'v01.2.3', 'v2.0.0'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                plan_releases([], value, self.repo)

    def test_notas_em_branch_lateral_nao_tornam_uma_versao_publicavel(self):
        base = self.commit('1.9.0')
        self.git('checkout', '-qb', 'lateral')
        lateral = self.commit('1.10.0')
        self.git('tag', 'v1.10.0', lateral)
        self.git('checkout', '-q', base)
        self.commit('1.15.0', 'Nexaltri')
        with self.assertRaises(ValueError):
            plan_releases([], 'v1.10.0', self.repo)
