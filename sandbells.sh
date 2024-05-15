#!/bin/sh
echo "############################################################################"
echo "#                                                                          #"
echo "#                          updating Sandbells                              #"
echo "#                                                                          #"
echo "############################################################################"

git status
cd /home/wyleu/Sandbells
echo $pwd
source Bellvirtenv/bin/activate
echo "started virtual env"
pip install -r requirements.txt
cd changes
echo "permissions"
chmod 777 /var/www/html/static/bells/*.*
echo "collect static"
python manage.py --noinput collectstatic
echo "permissions again..."
chmod 777 /var/www/html/static/bells/*.*
systemctl restart nginx.service
systemctl restart midori-fullscreen.service
systemctl restart gunicorn.service
