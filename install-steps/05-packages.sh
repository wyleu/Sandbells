#!/bin/bash
# 05-packages.sh
# Sandbells Install Step – core system packages for kiosk + web stack
#
# Args: $1 = QUICK_MODE (true/false)

QUICK_MODE=${1:-false}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/sandbells-common.sh"

echo "=================================================="
echo " 05 – Installing software packages"
echo "=================================================="
echo "This may take several minutes on a Pi 3..."

sudo apt-get update

# Packages we want
PACKAGES=(
    # Display / kiosk
    luakit
    xinit
    xserver-xorg
    x11-xserver-utils
    lightdm
    unclutter

    # Web stack
    nginx

    # Python / build
    python3
    python3-venv
    python3-pip
    python3-dev
    build-essential
    libpq-dev
    libjpeg-dev
    zlib1g-dev
    libffi-dev
    libssl-dev

    # Utilities
    git
    curl
    jq
    chrony
    locales-all
    avahi-daemon
    libnss-mdns
    htop
    rsync
)

# Only install what is missing
TO_INSTALL=()
for pkg in "${PACKAGES[@]}"; do
    if package_installed "$pkg"; then
        echo "  already installed: $pkg"
    else
        TO_INSTALL+=("$pkg")
    fi
done

if [ ${#TO_INSTALL[@]} -eq 0 ]; then
    echo "All required packages are already installed."
else
    echo "Installing: ${TO_INSTALL[*]}"
    sudo apt-get install --no-install-recommends -y "${TO_INSTALL[@]}"
fi

echo ""
echo "Packages step completed."
pause
