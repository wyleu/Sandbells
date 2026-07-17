#!/bin/bash
# 05-packages.sh
# Sandbells Install Step
# Command line arguments:
#   $1 = QUICK_MODE (true/false)

#!/bin/bash
QUICK_MODE=${1:-false}
pause() {
    if [ "$QUICK_MODE" = true ]; then
        sleep 1.5
        return
    fi
    echo ""
    read -p "Press Enter to continue (or Q to stop) > " choice
    if [[ "$choice" =~ ^[Qq]$ ]]; then
        echo "Setup stopped safely."
        exit 1
    fi
}


echo "Installing software packages (this may take several minutes)..."
sudo apt update
sudo apt install --no-install-recommends -y luakit matchbox-window-manager xinit xserver-xorg git curl chrony lightdm locales-all
echo "Packages installed successfully"
pause
