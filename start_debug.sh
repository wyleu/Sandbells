#!/bin/bash
# ===============================================================
# Sandbells Debug Server Starter
# File: start_debug.sh
# Purpose: Starts Django development server on port 8000
# ===============================================================

PROJECT_DIR="/opt/sandbells"
VENV_DIR="$PROJECT_DIR/Bellvirtenv"
USER="sandbells"

echo "=================================================="
echo "     Sandbells Debug Server"
echo "     Starting on http://0.0.0.0:8000"
echo "=================================================="

if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: Project not found at $PROJECT_DIR"
    echo "Please run install_debug.sh first."
    exit 1
fi

cd $PROJECT_DIR

# Activate virtual environment and start server
echo "Starting Django development server..."
sudo -u $USER $VENV_DIR/bin/python changes/manage.py runserver 0.0.0.0:8000
