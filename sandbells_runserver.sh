#!/bin/sh
echo "############################################################################"
echo "#                                                                          #"
echo "#        Sandbells Virtenv and Runserver                                   #"
echo "#                                                                          #"
echo "############################################################################"

echo $USER
cd /home/$USER/Code/Sandbells
git status
source Bellvirtenv/bin/activate
cd changes
# python manage.py collectstatic --noinput 

python manage.py runserver 0.0.0.0:8000
# sudo systemctl restart nginx.service
# sudo systemctl restart gunicorn.service
# sudo systemctl restart luakit-fullscreen.service
# sudo systemctl restart midori-fullscreen.service
