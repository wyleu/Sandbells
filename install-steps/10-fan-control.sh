#!/bin/bash
# 10-fan-control.sh
# Sandbells Install Step - PWM Fan Control
# Command line arguments:
# $1 = QUICK_MODE (true/false)
# $2 = DEBUG_MODE (true/false)

QUICK_MODE=${1:-false}
DEBUG_MODE=${2:-false}

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
echo "Sandbells PWM Fan Control Setup"
echo "=================================================="

if [ "$DEBUG_MODE" = true ]; then
    set -x
fi

# Check if already running
if systemctl is-active --quiet sandbells-fan.service; then
    echo "Fan control service is already running."
    pause
    exit 0
fi

echo "Installing PWM fan control..."

# Install dependencies
sudo apt-get update -qq
sudo apt-get install -y python3-dev

# Setup directory
mkdir -p /home/sandbells/Code/Sandbells/fan
cd /home/sandbells/Code/Sandbells/fan

# Keep original zynthian script (do not overwrite if it exists)
if [ ! -f zynthian-pwm-fan.py ]; then
    echo "Copying original zynthian PWM fan script..."
    # (Add your original script content here if needed, or assume it's already present)
    echo "Note: Please ensure zynthian-pwm-fan.py exists in this directory."
fi

echo "Creating shell wrapper..."
cat > fan-control.sh << 'EOF'
#!/bin/bash
# Sandbells Fan Control Wrapper
cd /home/sandbells/Code/Sandbells/fan
exec /usr/bin/python3 ./zynthian-pwm-fan.py
EOF

chmod +x fan-control.sh

echo "Creating systemd service..."
sudo tee /etc/systemd/system/sandbells-fan.service > /dev/null << 'EOL'
[Unit]
Description=Sandbells PWM Fan Control
After=multi-user.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/sandbells/Code/Sandbells/fan
ExecStart=/home/sandbells/Code/Sandbells/fan/fan-control.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

echo "Enabling and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable sandbells-fan.service
sudo systemctl start sandbells-fan.service

echo ""
echo "Fan control installed successfully using shell wrapper."
echo "Check status : systemctl status sandbells-fan"

if [ "$DEBUG_MODE" = true ]; then
    systemctl status sandbells-fan --no-pager -l
fi

pause
