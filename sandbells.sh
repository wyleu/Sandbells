#!/bin/sh
cd /home/wyleu/Sandbells
source Bellvirtenv/bin/activate
pip install -r requirements.txt
cd changes
chmod 777 /var/www/html/static/bells/*.*
python manage.py --noinput collectstatic
chmod 777 /var/www/html/static/bells/*.*
systemctl restart nginx.service
systemctl restart midori-fullscreen.service
systemctl restart gunicorn.service
