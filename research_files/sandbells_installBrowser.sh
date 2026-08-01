#!/bin/bash

############################################################################
#                                                                          #
#                   Sandbells Browser Installation Script                  #
#                                                                          #
############################################################################

echo "############################################################################"
echo "#                                                                          #"
echo "#               Installing Browser + WM for Sandbells                      #"
echo "#                                                                          #"
echo "############################################################################"

echo "Updating package lists..."
sudo apt update

echo "Installing Luakit, Matchbox WM, and dependencies..."
sudo apt install -y \
    x11-xserver-utils \
    matchbox-window-manager \
    luakit \
    libwebkit2gtk-4.1-0 \
    libgtk-3-0 \
    lua5.1 \
    liblua5.1-0 \
    libstartup-notification0

echo ""
echo "Verification:"
for tool in luakit matchbox-window-manager xset; do
    if command -v "$tool" > /dev/null 2>&1; then
        echo "✅ $tool is installed: $(which $tool)"
    else
        echo "❌ $tool NOT found"
    fi
done

echo ""
echo "Browser installation complete."
echo "You can now run:"
echo "   . sandbells_startLuakit.sh"
echo ""
echo "Next step suggestion: Add this to your rebuild process if needed."