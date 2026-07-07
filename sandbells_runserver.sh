#!/bin/bash
# Sandbells Development Server with status info
echo "=================================================="
echo " Sandbells Development Server"
echo "=================================================="

echo "User: $(whoami)"
echo "Directory: $(pwd)"
echo "Git branch: $(git branch --show-current 2>/dev/null || echo 'No git repo')"
echo "Git status: $(git status --porcelain 2>/dev/null | wc -l) changes"
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

echo "Starting development server..."
python changes/manage.py runserver 0.0.0.0:8000
