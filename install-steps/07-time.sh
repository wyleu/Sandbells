#!/bin/bash
# Time configuration step - smart check

TIME_SERVER="sandgps3.local"
DEBUG=${1:-false}

if [ "$DEBUG" = true ]; then
    echo "DEBUG MODE"
    set -x
fi

echo "Checking current time configuration..."

# Check if our desired server is already the preferred one
if grep -q "server $TIME_SERVER" /etc/chrony/chrony.conf 2>/dev/null; then
    echo "Good news! The local GPS time server ($TIME_SERVER) is already configured."
else
    echo "Updating chrony config to prefer local GPS ($TIME_SERVER)..."
    sudo systemctl stop chrony 2>/dev/null || true
    
    sudo cp /etc/chrony/chrony.conf /etc/chrony/chrony.conf.bak 2>/dev/null || true

    cat | sudo tee /etc/chrony/chrony.conf > /dev/null <<EOF
pool ntp.ubuntu.com iburst
server $TIME_SERVER iburst prefer
makestep 1.0 3
rtcsync
EOF
    echo "New config written."
fi

echo "Starting / restarting chrony..."
sudo systemctl restart chrony
sleep 6

echo "Current time sources:"
chronyc sources
echo ""
echo "Clock Stratum : $(chronyc tracking | grep Stratum | awk '{print $3}' || echo 'Unknown')"
echo "Reference ID  : $(chronyc tracking | grep 'Reference ID' | awk '{print $4}' | tr -d '()' || echo 'Unknown')"

echo "Time configuration step completed"
