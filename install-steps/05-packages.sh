#!/bin/bash
echo "Installing software packages (this may take several minutes)..."
sudo apt update
sudo apt install --no-install-recommends -y luakit matchbox-window-manager xinit xserver-xorg git curl chrony lightdm locales-all
echo "Packages installed successfully"
