#!/bin/sh
echo  "Relocating to /home/"$USER"/Code/Sandbells
cd /home/$USER/Code/Sandbells
source Bellvirtenv/bin/activate
cd changes
python manage.py collectstatic --noinput 

sudo systemctl restart nginx.service
sudo systemctl restart gunicorn.service
sudo systemctl restart luakit-fullscreen.service
#sudo systemctl restart midori-fullscreen.service
