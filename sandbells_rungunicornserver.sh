#!/bin/bash
cd ~/Code/Sandbells/changes
source ../Bellvirtenv/bin/activate
gunicorn --bind 0.0.0.0:8000 changes.wsgi:application
