#!/usr/bin/env bash
# Render ejecuta este script durante el build.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
