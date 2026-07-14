#!/bin/bash
echo "Setting up automatic login..."
sudo tee /etc/lightdm/lightdm.conf > /dev/null <<EOF
[Seat:*]
autologin-user=sandbells
autologin-user-timeout=0
autologin-session=lightdm-xsession
EOF
echo "Auto-login configured"
