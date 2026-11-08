import json
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from .colunas import COLUNAS
from .models import PreferenciaListaChamados, RegistroAuditoria, Notificacao


class ColunasTests(TestCase):
    def setUp(self):
        self.usuario=User.objects.create_user('colunas-cliente')
        self.outro=User.objects.create_user('colunas-tecnico',is_staff=True)
        self.client.force_login(self.usuario)
        self.url=reverse('salvar_ordem_colunas')
        self.ordem=list(reversed(COLUNAS))

    def post(self,dados=None,**extra):
        return self.client.post(self.url,json.dumps(dados if dados is not None else {'ordem':self.ordem}),content_type='application/json',**extra)

    def test_consulta_padrao_sem_criar_preferencia(self):
        r=self.client.get(reverse('lista_chamados'))
        self.assertEqual(r.context['ordem_colunas'],list(COLUNAS))
        self.assertFalse(PreferenciaListaChamados.objects.exists())
        self.assertContains(r,'data-coluna="ticket"')
        self.assertContains(r,'Restaurar ordem padrão')

    def test_salva_todas_colunas_e_recarrega_por_usuario_sem_notificar_ou_auditar(self):
        antes=(RegistroAuditoria.objects.count(),Notificacao.objects.count())
        r=self.post();self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()['ordem'],self.ordem)
        self.assertIn('no-store',r.headers['Cache-Control'])
        self.assertEqual(self.client.get(reverse('lista_chamados')).context['ordem_colunas'],self.ordem)
        segunda=Client();segunda.force_login(self.usuario)
        self.assertEqual(segunda.get(reverse('lista_chamados')).context['ordem_colunas'],self.ordem)
        self.assertEqual((RegistroAuditoria.objects.count(),Notificacao.objects.count()),antes)
        self.client.force_login(self.outro)
        self.assertEqual(self.client.get(reverse('lista_chamados')).context['ordem_colunas'],list(COLUNAS))

    def test_sobrescreve_apenas_a_propria_preferencia_e_restaura_padrao(self):
        PreferenciaListaChamados.objects.create(usuario=self.outro,ordem=list(COLUNAS))
        self.assertEqual(self.post().status_code,200)
        self.assertEqual(self.post({'ordem':list(COLUNAS)}).status_code,200)
        self.assertEqual(PreferenciaListaChamados.objects.filter(usuario=self.usuario).count(),1)
        self.assertEqual(PreferenciaListaChamados.objects.get(usuario=self.outro).ordem,list(COLUNAS))
        self.assertEqual(self.client.get(reverse('lista_chamados')).context['ordem_colunas'],list(COLUNAS))

    def test_payload_invalido_nao_altera_preferencia(self):
        self.post()
        invalidos=[{},None,[],{'ordem':None},{'ordem':list(COLUNAS)[:-1]},
            {'ordem':[COLUNAS[0]]*len(COLUNAS)}, {'ordem':[*COLUNAS[:-1],'inventada']},
            {'ordem':[*COLUNAS[:-1],{}]}, {'ordem':list(COLUNAS),'usuario':self.outro.pk},
            {'ordem':'ticket'}, {'ordem':list(COLUNAS)*100}]
        for dados in invalidos:
            r=self.client.post(self.url,json.dumps(dados),content_type='application/json')
            self.assertEqual(r.status_code,400)
        self.assertEqual(PreferenciaListaChamados.objects.get(usuario=self.usuario).ordem,self.ordem)
        self.assertEqual(self.client.post(self.url,'{',content_type='application/json').status_code,400)
        self.assertEqual(self.client.post(self.url,b'\xff',content_type='application/json').status_code,400)
        self.assertEqual(self.client.post(self.url,{'ordem':self.ordem}).status_code,400)

    def test_requer_login_post_e_csrf(self):
        self.assertEqual(Client().post(self.url,{},content_type='application/json').status_code,302)
        self.assertEqual(self.client.get(self.url).status_code,405)
        estrito=Client(enforce_csrf_checks=True);estrito.force_login(self.usuario)
        self.assertEqual(estrito.post(self.url,json.dumps({'ordem':self.ordem}),content_type='application/json').status_code,403)
        estrito.get(reverse('lista_chamados'))
        r=estrito.post(self.url,json.dumps({'ordem':self.ordem}),content_type='application/json',HTTP_X_CSRFTOKEN=estrito.cookies['csrftoken'].value)
        self.assertEqual(r.status_code,200)
        User.objects.filter(pk=self.usuario.pk).update(is_active=False)
        self.assertEqual(self.post().status_code,302)

    def test_querystring_nao_escolhe_destinatario_e_filtros_nao_resetam_ordem(self):
        self.url+='?usuario='+str(self.outro.pk)
        self.post()
        self.assertFalse(PreferenciaListaChamados.objects.filter(usuario=self.outro).exists())
        r=self.client.get(reverse('lista_chamados'),{'fila':'minha','sla':'vencidos','q':'Sem resultado','page':2})
        self.assertEqual(r.context['ordem_colunas'],self.ordem)

    def test_dado_antigo_invalido_usa_padrao_sem_expor_html(self):
        PreferenciaListaChamados.objects.create(usuario=self.usuario,ordem=['<script>alert(1)</script>'])
        r=self.client.get(reverse('lista_chamados'))
        self.assertEqual(r.context['ordem_colunas'],list(COLUNAS))
        self.assertNotContains(r,'<script>alert(1)</script>')
