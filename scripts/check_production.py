"""Verifica produção sem exigir HSTS nos subdomínios ou adesão ao preload."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings_production')

import django
from django.core import checks

django.setup()
observacoes = checks.run_checks(include_deployment_checks=True)
# Não aplicar HSTS a outros subdomínios nem preload sem validar sua infraestrutura.
permitidos = {'security.W005', 'security.W021'}
for observacao in observacoes:
    print(observacao)
falhas = [item for item in observacoes if item.id not in permitidos]
raise SystemExit(1 if falhas else 0)
