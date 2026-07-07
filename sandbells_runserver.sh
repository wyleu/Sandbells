#!/bin/bash
# Sandbells Development Server
echo "=================================================="
echo " Sandbells Development Server"
echo "=================================================="

echo "User       : $(whoami)"
echo "Directory  : $(pwd)"
if git rev-parse --is-inside-work-tree &>/dev/null; then
    echo "Git branch : $(git branch --show-current)"
    echo "Git status : $(git status --porcelain | wc -l) uncommitted changes"
else
    echo "Git        : Not a git repository"
fi
echo "=================================================="

cd ~/Code/Sandbells

source Bellvirtenv/bin/activate

echo "Applying migrations..."
python changes/manage.py migrate

echo "Loading initial data..."
python changes/manage.py loaddata fixtures/initial_data.json || true

echo "Ensuring superuser..."
python changes/manage.py shell -c '
from django.contrib.auth.models import User
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser("admin", "admin@example.com", "admin123")
    print("Default superuser created")
else:
    print("Superuser exists")
' || true

echo "Starting development server on http://0.0.0.0:8000"
python changes/manage.py runserver 0.0.0.0:8000
