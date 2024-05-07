#!/bin/sh
cd /home/wyleu/Sandbells
source Bellvirtenv/bin/activate
cd changes
python manage.py --noinput 
collectstatic
systemctl restart nginx.service
systemctl restart midori-fullscreen.service
systemctl restart gunicorn.service
