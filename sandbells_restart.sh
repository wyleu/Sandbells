#!/bin/sh
cd /home/wyleu/Code/Sandbells
source Bellvirtenv/bin/activate
cd changes
python manage.py collectstatic --noinput 

sudo systemctl restart nginx.service
sudo systenctl gunicorn.service
sudo systemctl restart midori-fullscreen.service
