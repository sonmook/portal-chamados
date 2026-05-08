from django.contrib import admin
from .models import Chamado, Comentario

# Registra os modelos no painel administrativo padrão do Django (/admin)
# Isso permite gerenciar os dados cruamente pelo backend, se necessário.
admin.site.register(Chamado)
admin.site.register(Comentario)