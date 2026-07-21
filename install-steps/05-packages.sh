#!/bin/bash
# 05-packages.sh
# Sandbells Install Step – core system packages for kiosk + web stack
#
# Command line arguments:
#   $1 = QUICK_MODE (true/false)

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

echo "=================================================="
echo " 05 – Installing software packages"
echo "=================================================="
echo "This may take several minutes on a Pi 3..."

sudo apt-get update

sudo apt-get install --no-install-recommends -y \
    # Display / kiosk
    luakit \
    matchbox-window-manager \
    xinit \
    xserver-xorg \
    x11-xserver-utils \
    lightdm \
    unclutter \
    # Web stack
    nginx \
    # Python / build (also pulled by step 12, but good to have early)
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    build-essential \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    libffi-dev \
    libssl-dev \
    # Utilities
    git \
    curl \
    chrony \
    locales-all \
    avahi-daemon \
    libnss-mdns \
    # Optional but useful
    htop \
    rsync

echo ""
echo "Packages installed successfully."
pause
