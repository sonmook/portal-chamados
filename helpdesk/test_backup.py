import json
from pathlib import Path
import sqlite3
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase
from .backups import criar_backup, restaurar_backup, verificar_backup


class BackupTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root/'origem.sqlite3'
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE registros (id INTEGER PRIMARY KEY, texto TEXT)')
            db.execute("INSERT INTO registros(texto) VALUES ('histórico preservado')")
            db.execute('CREATE TABLE helpdesk_chamado (id INTEGER PRIMARY KEY, anexo TEXT)')
            db.execute('CREATE TABLE helpdesk_comentario (id INTEGER PRIMARY KEY, anexo TEXT)')
            db.execute("INSERT INTO helpdesk_chamado(anexo) VALUES ('evidencia.pdf')")
        self.media=self.root/'uploads'
        self.media.mkdir()
        (self.media/'evidencia.pdf').write_bytes(b'%PDF-1.7 evidencia')
        self.backup=self.root/'backup'

    def criar(self):
        criar_backup(self.db,self.media,self.backup)

    def test_backup_restauracao_dados_e_upload(self):
        self.criar()
        destino=self.root/'restaurado'
        restaurar_backup(self.backup,destino)
        with sqlite3.connect(destino/'db.sqlite3') as db:
            self.assertEqual(db.execute('SELECT texto FROM registros').fetchone()[0], 'histórico preservado')
        self.assertEqual((destino/'media/evidencia.pdf').read_bytes(), (self.media/'evidencia.pdf').read_bytes())
        self.assertTrue(self.db.exists())

    def test_nao_sobrescreve_destino(self):
        self.criar()
        with self.assertRaises(ValueError):self.criar()
        with self.assertRaises(ValueError):restaurar_backup(self.backup,self.media)
        self.assertTrue((self.media/'evidencia.pdf').exists())

    def test_corrupcao_impede_restauracao(self):
        self.criar()
        (self.backup/'media/evidencia.pdf').write_bytes(b'corrompido')
        with self.assertRaises(ValueError):restaurar_backup(self.backup,self.root/'restaurado')
        self.assertFalse((self.root/'restaurado').exists())

    def test_symlink_rejeitado(self):
        (self.media/'link').symlink_to(self.db)
        with self.assertRaises(ValueError):self.criar()

    def test_backup_dentro_dos_uploads_rejeitado(self):
        with self.assertRaises(ValueError):criar_backup(self.db,self.media,self.media/'backup')

    def test_nao_cria_banco_ausente(self):
        ausente=self.root/'ausente.sqlite3'
        with self.assertRaises(ValueError):criar_backup(ausente,self.media,self.backup)
        self.assertFalse(ausente.exists())

    def test_manifesto_malicioso_rejeitado(self):
        self.criar()
        path=self.backup/'manifest.json'
        manifest=json.loads(path.read_text())
        manifest['arquivos']['../fora']='falso'
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):verificar_backup(self.backup)

    def test_comando_exige_parada_dos_escritores(self):
        with self.assertRaises(CommandError):call_command('backup_homologacao', str(self.backup))

    def test_anexo_ausente_impede_criacao_e_remove_copia_parcial(self):
        for tabela in ('helpdesk_chamado', 'helpdesk_comentario'):
            with self.subTest(tabela=tabela):
                with sqlite3.connect(self.db) as db:
                    db.execute(f"INSERT INTO {tabela}(anexo) VALUES ('ausente.pdf')")
                with self.assertRaisesMessage(ValueError, 'anexo referenciado no banco ausente'):
                    self.criar()
                self.assertFalse(self.backup.exists())
                self.assertTrue((self.media/'evidencia.pdf').exists())
                with sqlite3.connect(self.db) as db:
                    db.execute(f"DELETE FROM {tabela} WHERE anexo = 'ausente.pdf'")

    def test_raiz_midia_ausente_com_referencias_impede_backup(self):
        with self.assertRaisesMessage(ValueError, 'anexo referenciado no banco ausente'):
            criar_backup(self.db, self.root/'uploads-ausentes', self.backup)
        self.assertFalse(self.backup.exists())

    def test_sem_anexos_aceita_raiz_ausente_e_restaura(self):
        with sqlite3.connect(self.db) as db:
            db.execute('DELETE FROM helpdesk_chamado')
            db.executemany('INSERT INTO helpdesk_chamado(anexo) VALUES (?)', [(None,), ('',)])
            db.executemany('INSERT INTO helpdesk_comentario(anexo) VALUES (?)', [(None,), ('',)])
        criar_backup(self.db, self.root/'uploads-ausentes', self.backup)
        restaurar_backup(self.backup, self.root/'restaurado')
        self.assertTrue((self.root/'restaurado/media').is_dir())

    def test_anexo_de_comentario_preservado(self):
        (self.media/'comentario.pdf').write_bytes(b'%PDF-1.7 comentario')
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO helpdesk_comentario(anexo) VALUES ('comentario.pdf')")
        self.criar()
        restaurar_backup(self.backup, self.root/'restaurado')
        self.assertEqual((self.root/'restaurado/media/comentario.pdf').read_bytes(), b'%PDF-1.7 comentario')

    def test_manifesto_coerente_nao_oculta_anexo_ausente(self):
        self.criar()
        (self.backup/'media/evidencia.pdf').unlink()
        path = self.backup/'manifest.json'
        manifest = json.loads(path.read_text())
        del manifest['arquivos']['media/evidencia.pdf']
        path.write_text(json.dumps(manifest))
        with self.assertRaisesMessage(ValueError, 'anexo referenciado no banco ausente'):
            verificar_backup(self.backup)
        with self.assertRaisesMessage(ValueError, 'anexo referenciado no banco ausente'):
            restaurar_backup(self.backup, self.root/'restaurado')
        self.assertFalse((self.root/'restaurado').exists())

    def test_esquema_sem_tabela_de_anexos_nao_passa_silenciosamente(self):
        with sqlite3.connect(self.db) as db:
            db.execute('DROP TABLE helpdesk_comentario')
        with self.assertRaisesMessage(ValueError, 'Não foi possível verificar as referências'):
            self.criar()
        self.assertFalse(self.backup.exists())

    def test_referencia_fora_da_midia_rejeitada(self):
        for nome in ('../evidencia.pdf', '/evidencia.pdf', 'media\\evidencia.pdf'):
            with self.subTest(nome=nome):
                with sqlite3.connect(self.db) as db:
                    db.execute('UPDATE helpdesk_chamado SET anexo = ?', (nome,))
                with self.assertRaisesMessage(ValueError, 'Referência de anexo inválida'):
                    self.criar()
                self.assertFalse(self.backup.exists())

    def test_midia_arquivo_rejeitada(self):
        with self.assertRaisesMessage(ValueError, 'deve ser um diretório'):
            criar_backup(self.db, self.media/'evidencia.pdf', self.backup)
        self.assertFalse(self.backup.exists())
