#!/bin/sh
cd /home/wyleu/Code/Sandbells
source Bellvirtenv/bin/activate
cd changes
pwd
python manage.py collectstatic --noinput

sudo systemctl restart nginx.service
sudo systemctl restart midori-fullscreen.service
sudo systemctl restart gunicorn.service
