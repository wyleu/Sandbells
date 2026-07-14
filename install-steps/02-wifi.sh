#!/bin/bash
echo "Setting WiFi country and attempting tower network..."
sudo raspi-config nonint do_wifi_country GB
sudo raspi-config nonint do_wifi_ssid_passphrase sandbells Sandbells || true
echo "WiFi step completed"

