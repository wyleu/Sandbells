#!/bin/bash
echo "Enabling SSH access..."
sudo raspi-config nonint do_ssh 0
echo "SSH enabled"
