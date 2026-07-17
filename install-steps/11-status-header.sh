#!/bin/bash
# 11-status-header.sh
# Installs systemd service to show status header on boot

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
echo "Installing Sandbells Status Header Service"
echo "=================================================="

sudo tee /etc/systemd/system/sandbells-status.service > /dev/null <<EOF
[Unit]
Description=Sandbells Status Header on Boot
After=multi-user.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=sandbells
WorkingDirectory=/home/sandbells/Code/Sandbells
ExecStart=/bin/bash -c 'START_TIME=\$(date +%s) source show_header.sh && show_header'

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable sandbells-status.service

echo "Status header service installed and enabled."
echo "It will show on boot."
pause
