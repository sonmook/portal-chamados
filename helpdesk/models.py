from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db import transaction
from django.db.models.functions import Coalesce, Greatest, Lower
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from .validators import validar_anexo
from .visual_conquistas import OPCOES_ICONES, visual


def equipe_triagem_id():
    return Equipe.objects.get(triagem_padrao=True, ativa=True).pk

def calcular_prazo_util(data_inicial, horas_prazo):
    """
    Função auxiliar para calcular a data final de um SLA, adicionando horas 
    e pulando finais de semana (sábados e domingos).
    """
    data_final = data_inicial
    horas_contadas = 0

    while horas_contadas < horas_prazo:
        data_final += timedelta(hours=1)
        # weekday(): 0=Seg, 1=Ter, 2=Qua, 3=Qui, 4=Sex, 5=Sáb, 6=Dom
        if data_final.weekday() < 5:
            horas_contadas += 1

    return data_final


class Chamado(models.Model):
    """
    Modelo principal que representa um ticket/chamado de suporte.
    Armazena detalhes do problema, prazos (SLA), status e responsáveis.
    """
    STATUS_CHOICES = (
        ('Aberto', 'Aberto'),
        ('Em Andamento', 'Em Andamento'),
        ('Resolvido', 'Resolvido'),
        ('Fechado', 'Fechado'),
    )

    PRIORIDADE_CHOICES = (
        ('Baixa', 'Baixa'),
        ('Normal', 'Normal'),
        ('Alta', 'Alta'),
        ('Crítica', 'Crítica'),
    )

    CATEGORIA_CHOICES = (
        ('Software', 'Software/Sistemas'),
        ('Hardware', 'Hardware/Periféricos'),
        ('Rede', 'Rede/Internet'),
        ('Acessos', 'Acessos e Senhas'),
        ('Outros', 'Outros'),
    )

    # Informações base do chamado
    titulo = models.CharField(max_length=200, verbose_name="Título do Chamado")
    descricao = models.TextField(verbose_name="Descrição do Problema")
    categoria = models.CharField(max_length=30, choices=CATEGORIA_CHOICES, default='Outros')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Aberto')
    prioridade = models.CharField(max_length=20, choices=PRIORIDADE_CHOICES, default='Normal')
    anexo = models.FileField(validators=[validar_anexo], upload_to='anexos_chamados/', blank=True, null=True, verbose_name="Anexo (Print do Erro)")
    
    # Rastreamento de Datas e SLA
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)
    ultima_interacao_em = models.DateTimeField(null=True, blank=True, editable=False, db_index=True)
    data_vencimento = models.DateTimeField(blank=True, null=True)
    data_fechamento = models.DateTimeField(null=True, blank=True, verbose_name="Data de Fechamento")

    # Relacionamentos com Usuários
    solicitante = models.ForeignKey(User, on_delete=models.PROTECT, related_name='chamados_solicitados')
    tecnico = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='chamados_atendidos', verbose_name='Técnico Responsável')
    fechado_por = models.ForeignKey(User, on_delete=models.PROTECT, blank=True, null=True, related_name='chamados_fechados')
    equipe = models.ForeignKey('Equipe', on_delete=models.PROTECT, related_name='chamados', default=equipe_triagem_id)
    versao_atribuicao = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        indexes = [models.Index(fields=['status', 'data_vencimento'], name='chamado_status_prazo_idx')]

    def save(self, *args, **kwargs):
        """
        Sobrescreve o método de salvamento para calcular o SLA automaticamente 
        no momento da criação do chamado, baseado na prioridade selecionada.
        """
        if not self.data_vencimento:
            regras_sla = {
                'Crítica': 4,
                'Alta': 24,
                'Normal': 48,
                'Baixa': 120
            }
            horas = regras_sla.get(self.prioridade, 48)
            self.data_vencimento = calcular_prazo_util(timezone.now(), horas)

        if not self._state.adding and kwargs.get('update_fields') is None:
            # A interação é mantida pelos comentários, não por cópias antigas do chamado.
            adiados = self.get_deferred_fields()
            kwargs['update_fields'] = {
                campo.name for campo in self._meta.concrete_fields
                if not campo.primary_key and campo.name != 'ultima_interacao_em' and campo.attname not in adiados
            }
        super().save(*args, **kwargs)

    @property
    def data_ultima_interacao(self):
        return self.ultima_interacao_em or self.data_criacao

    @property
    def sla_estourado(self):
        """
        Propriedade computada que retorna True se o chamado não está resolvido
        e a data/hora atual ultrapassou o vencimento do SLA.
        """
        if self.status not in ('Resolvido', 'Fechado') and self.data_vencimento and timezone.now() > self.data_vencimento:
            return True
        return False                                         

    def __str__(self):
        return f"#{self.id} - {self.titulo}"


class Comentario(models.Model):
    """
    Modelo para armazenar as interações (chat/respostas) dentro de um chamado.
    """
    chamado = models.ForeignKey(Chamado, on_delete=models.PROTECT, related_name='comentarios')
    autor = models.ForeignKey(User, on_delete=models.PROTECT)
    texto = models.TextField(verbose_name="Mensagem")
    data_criacao = models.DateTimeField(auto_now_add=True)
    anexo = models.FileField(validators=[validar_anexo], upload_to='anexos_comentarios/', blank=True, null=True, verbose_name="Anexo")

    def save(self, *args, **kwargs):
        novo = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if novo:
                # Inclui a solução registrada como comentário e não recua em gravações concorrentes.
                Chamado.objects.filter(pk=self.chamado_id).update(ultima_interacao_em=Greatest(
                    Coalesce('ultima_interacao_em', 'data_criacao'), models.Value(self.data_criacao)
                ))

    def __str__(self):
        return f"Comentário de {self.autor.username} no chamado #{self.chamado.id}"

# Função alternativa de cálculo de horas (Mantida para fins de compatibilidade)
def somar_horas_uteis(data_inicio, horas_a_somar):
    data_final = data_inicio
    while horas_a_somar > 0:
        data_final += timedelta(hours=1)
        if data_final.weekday() < 5:
            horas_a_somar -= 1
    return data_final

class JanelaLogin(models.Model):
    chave = models.CharField(max_length=64, unique=True)
    tentativas = models.PositiveIntegerField(default=0)
    expira_em = models.DateTimeField(db_index=True)


class RegistroAuditoria(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    ator = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    origem = models.CharField(max_length=12, default='sistema')
    objeto = models.CharField(max_length=40)
    objeto_id = models.PositiveBigIntegerField()
    acao = models.CharField(max_length=16)
    alteracoes = models.JSONField(default=dict)

    class Meta:
        ordering = ['-criado_em', '-pk']
        indexes = [models.Index(fields=['objeto', 'objeto_id'])]

    def __str__(self):
        return f'{self.objeto} #{self.objeto_id}: {self.acao}'


class Equipe(models.Model):
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True, max_length=1000)
    ativa = models.BooleanField(default=True)
    versao = models.PositiveIntegerField(default=0, editable=False)
    triagem_padrao = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ['nome', 'pk']
        constraints = [models.UniqueConstraint(Lower('nome'), name='equipe_nome_unico',
                                              violation_error_message='Já existe uma equipe com esse nome.'),
                       models.UniqueConstraint(fields=['triagem_padrao'], condition=models.Q(triagem_padrao=True),
                                               name='uma_equipe_triagem')]

    def __str__(self):
        return self.nome


class IntegranteEquipe(models.Model):
    equipe = models.ForeignKey(Equipe, on_delete=models.PROTECT, related_name='vinculos')
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, related_name='vinculos_equipes')
    coordenador = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['equipe', 'usuario'], name='integrante_equipe_unico')]

    def __str__(self):
        return f'{self.equipe}: {self.usuario}'


class RegraEncaminhamento(models.Model):
    categoria = models.CharField(max_length=30, choices=Chamado.CATEGORIA_CHOICES, unique=True)
    equipe = models.ForeignKey(Equipe, on_delete=models.PROTECT, related_name='regras_encaminhamento')
    ativa = models.BooleanField(default=True)
    versao = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ['categoria']

    def __str__(self):
        return f'{self.get_categoria_display()} → {self.equipe}'


def caminho_foto_perfil(instance, filename):
    from uuid import uuid4
    return f'perfis/{uuid4().hex}.png'


class Perfil(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    foto = models.FileField(upload_to=caminho_foto_perfil, blank=True)
    foto_x = models.PositiveSmallIntegerField(default=50, validators=[MaxValueValidator(100)])
    foto_y = models.PositiveSmallIntegerField(default=50, validators=[MaxValueValidator(100)])
    foto_zoom = models.PositiveSmallIntegerField(default=100, validators=[MinValueValidator(100), MaxValueValidator(300)])
    cargo = models.CharField(max_length=100, blank=True)
    departamento = models.CharField(max_length=100, blank=True)
    ramal = models.CharField(max_length=20, blank=True)
    versao = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(foto_x__range=(0, 100), foto_y__range=(0, 100), foto_zoom__range=(100, 300)), name='perfil_enquadramento_valido')]

    def __str__(self):
        return f'Perfil de {self.usuario.username}'


class PlanoConquista(models.Model):
    nome = models.CharField(max_length=80)
    descricao = models.CharField(max_length=240)
    icone = models.CharField(max_length=20, choices=OPCOES_ICONES, default='trofeu')
    alvo = models.CharField(max_length=10, choices=[('pessoa', 'Técnico'), ('equipe', 'Equipe')])
    metrica = models.CharField(max_length=12, choices=[('resolucoes', 'Chamados resolvidos'), ('no_prazo', 'Chamados resolvidos dentro do SLA')])
    bronze = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(100000)])
    prata = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(100000)])
    ouro = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(100000)])
    contagem = models.CharField(max_length=12, choices=[('publicacao', 'Começar na publicação'), ('historico', 'Usar eventos já registrados desde o início do sistema')], default='publicacao')
    estado = models.CharField(max_length=12, choices=[('rascunho', 'Rascunho'), ('publicada', 'Publicada')], default='rascunho')
    ativa = models.BooleanField(default=True)
    versao = models.PositiveIntegerField(default=0, editable=False)
    regra_origem = models.ForeignKey('RegraConquista', on_delete=models.PROTECT, null=True, blank=True, related_name='revisoes')
    base_versao = models.PositiveIntegerField(null=True, blank=True)
    publicada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(bronze__range=(1, 100000)), name='plano_bronze_valido'),
            models.CheckConstraint(condition=(models.Q(regra_origem__isnull=False, prata__isnull=True, ouro__isnull=True) | models.Q(regra_origem__isnull=True, prata__gt=models.F('bronze'), ouro__gt=models.F('prata'), ouro__lte=100000, prata__isnull=False, ouro__isnull=False)), name='plano_metas_crescentes'),
            models.UniqueConstraint(fields=['regra_origem'], condition=models.Q(estado='rascunho', regra_origem__isnull=False), name='um_rascunho_por_regra'),
        ]

    @property
    def visual(self):
        return visual(self.icone)


class RegraConquista(models.Model):
    plano = models.ForeignKey(PlanoConquista, on_delete=models.PROTECT, null=True, blank=True, related_name='niveis')
    nivel = models.CharField(max_length=6, choices=[('bronze', 'Bronze'), ('prata', 'Prata'), ('ouro', 'Ouro')], blank=True)
    codigo = models.SlugField(max_length=40, unique=True)
    icone = models.CharField(max_length=20, choices=OPCOES_ICONES, default='trofeu')
    nome = models.CharField(max_length=80)
    descricao = models.CharField(max_length=240)
    alvo = models.CharField(max_length=10, choices=[('pessoa', 'Individual'), ('equipe', 'Equipe')])
    metrica = models.CharField(max_length=12, choices=[('resolucoes', 'Resoluções'), ('no_prazo', 'Resoluções no prazo')])
    meta = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(100000)])
    ativa = models.BooleanField(default=True)
    inicio_em = models.DateTimeField(default=timezone.now, editable=False)
    versao = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ['pk']
        constraints = [
            models.CheckConstraint(condition=models.Q(meta__range=(1, 100000)), name='conquista_meta_valida'),
            models.UniqueConstraint(fields=['plano', 'nivel'], condition=models.Q(plano__isnull=False), name='nivel_unico_por_plano'),
            models.CheckConstraint(condition=(models.Q(plano__isnull=True, nivel='') | models.Q(plano__isnull=False, nivel__in=['bronze','prata','ouro'])), name='nivel_associado_ao_plano'),
        ]

    def __str__(self):
        return self.nome

    @property
    def visual(self):
        return visual(self.icone)


class ResolucaoConquista(models.Model):
    chamado = models.OneToOneField(Chamado, on_delete=models.PROTECT, related_name='evento_conquista')
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, related_name='resolucoes_conquistas')
    equipe = models.ForeignKey(Equipe, on_delete=models.PROTECT, related_name='resolucoes_conquistas')
    concluido_em = models.DateTimeField()
    no_prazo = models.BooleanField()

    class Meta:
        indexes = [models.Index(fields=['usuario', 'concluido_em']), models.Index(fields=['equipe', 'concluido_em'])]


class Conquista(models.Model):
    nivel = models.CharField(max_length=6, choices=[('bronze', 'Bronze'), ('prata', 'Prata'), ('ouro', 'Ouro')], blank=True)
    regra = models.ForeignKey(RegraConquista, on_delete=models.PROTECT)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='conquistas')
    equipe = models.ForeignKey(Equipe, on_delete=models.PROTECT, null=True, blank=True, related_name='conquistas')
    icone = models.CharField(max_length=20, choices=OPCOES_ICONES, default='trofeu')
    nome = models.CharField(max_length=80)
    descricao = models.CharField(max_length=240)
    meta = models.PositiveIntegerField()
    versao_regra = models.PositiveIntegerField()
    alcancada_em = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-alcancada_em', '-pk']
        constraints = [
            models.CheckConstraint(condition=(models.Q(usuario__isnull=False, equipe__isnull=True) | models.Q(usuario__isnull=True, equipe__isnull=False)), name='conquista_um_destinatario'),
            models.UniqueConstraint(fields=['regra', 'usuario'], condition=models.Q(usuario__isnull=False), name='conquista_unica_pessoa'),
            models.UniqueConstraint(fields=['regra', 'equipe'], condition=models.Q(equipe__isnull=False), name='conquista_unica_equipe'),
        ]

    @property
    def visual(self):
        return visual(self.icone)


class Notificacao(models.Model):
    TIPOS = [('atribuicao', 'Atribuição atualizada'), ('resposta', 'Nova resposta'),
             ('transferencia', 'Equipe alterada'), ('resolucao', 'Chamado resolvido'),
             ('sla_proximo', 'SLA próximo do vencimento'), ('sla_vencido', 'SLA vencido'),
             ('sem_responsavel', 'Chamado sem responsável')]
    destinatario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notificacoes')
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name='notificacoes')
    tipo = models.CharField(max_length=15, choices=TIPOS)
    evento = models.CharField(max_length=100)
    criada_em = models.DateTimeField(auto_now_add=True)
    lida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-criada_em', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['destinatario', 'evento'], name='notificacao_dest_evento_unico'),
            models.CheckConstraint(condition=models.Q(tipo__in=['atribuicao', 'resposta', 'transferencia', 'resolucao', 'sla_proximo', 'sla_vencido', 'sem_responsavel']), name='notificacao_tipo_valido'),
        ]
        indexes = [models.Index(fields=['destinatario', 'lida_em', '-criada_em'], name='notificacao_dest_lida_data')]

    @property
    def icone(self):
        return {'atribuicao': 'person-check', 'resposta': 'chat-left-text',
                'transferencia': 'arrow-left-right', 'resolucao': 'check-circle',
                'sla_proximo': 'hourglass-split', 'sla_vencido': 'alarm',
                'sem_responsavel': 'person-exclamation'}.get(self.tipo, 'bell')


class PreferenciaListaChamados(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferencia_lista_chamados')
    ordem = models.JSONField(default=list)
