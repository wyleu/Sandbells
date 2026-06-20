#!/bin/sh
cd /home/wyleu/Code/Sandbells
source Bellvirtenv/bin/activate
cd changes
python manage.py --noinput collectstatic

sudo systemctl restart nginx.service
sudo systemctl restart midori-fullscreen.service
sudo systemctl restart gunicorn.service
