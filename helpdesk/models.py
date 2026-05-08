from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

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
    anexo = models.FileField(upload_to='anexos_chamados/', blank=True, null=True, verbose_name="Anexo (Print do Erro)")
    
    # Rastreamento de Datas e SLA
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)
    data_vencimento = models.DateTimeField(blank=True, null=True)
    data_fechamento = models.DateTimeField(null=True, blank=True, verbose_name="Data de Fechamento")

    # Relacionamentos com Usuários
    solicitante = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chamados_solicitados')
    tecnico = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='chamados_atendidos', verbose_name='Técnico Responsável')
    fechado_por = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='chamados_fechados')

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
            
        super().save(*args, **kwargs)

    @property
    def sla_estourado(self):
        """
        Propriedade computada que retorna True se o chamado não está resolvido
        e a data/hora atual ultrapassou o vencimento do SLA.
        """
        if self.status != 'Resolvido' and self.data_vencimento and timezone.now() > self.data_vencimento:
            return True
        return False                                         

    def __str__(self):
        return f"#{self.id} - {self.titulo}"


class Comentario(models.Model):
    """
    Modelo para armazenar as interações (chat/respostas) dentro de um chamado.
    """
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name='comentarios')
    autor = models.ForeignKey(User, on_delete=models.CASCADE)
    texto = models.TextField(verbose_name="Mensagem")
    data_criacao = models.DateTimeField(auto_now_add=True)
    anexo = models.FileField(upload_to='anexos_comentarios/', blank=True, null=True, verbose_name="Anexo")

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