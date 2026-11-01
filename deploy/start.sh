#!/bin/sh
set -eu
python scripts/check_production.py
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 1 --threads 1 --timeout 60 --no-control-socket --error-logfile -
