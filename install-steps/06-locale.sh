#!/bin/bash
echo "Setting UK English locale..."
sudo dpkg-reconfigure -f noninteractive locales
echo "en_US.UTF-8 UTF-8" | sudo tee -a /etc/locale.gen > /dev/null
sudo locale-gen en_US.UTF-8
sudo update-locale LANG=en_US.UTF-8
echo "Locale updated to UK English"
