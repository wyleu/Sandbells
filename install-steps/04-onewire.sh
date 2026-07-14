#!/bin/bash
echo "Enabling 1-Wire support..."
sudo raspi-config nonint do_onewire 0
echo "1-Wire enabled (active after reboot)"
