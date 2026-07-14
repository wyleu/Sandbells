#!/bin/bash
echo "Configuring time with local GPS source (sandgps3.local)..."
sudo systemctl stop chrony 2>/dev/null || true
sudo cp /etc/chrony/chrony.conf /etc/chrony/chrony.conf.bak 2>/dev/null || true

cat | sudo tee /etc/chrony/chrony.conf > /dev/null <<EOF
pool ntp.ubuntu.com iburst
server sandgps3.local iburst prefer
makestep 1.0 3
rtcsync
EOF

sudo systemctl start chrony
sleep 8

echo "Current time sources:"
chronyc sources
echo ""
echo "Clock Stratum : $(chronyc tracking | grep Stratum | awk '{print $3}' || echo 'Unknown')"
echo "Reference ID  : $(chronyc tracking | grep 'Reference ID' | awk '{print $4}' | tr -d '()' || echo 'Unknown')"
echo "Time server configured successfully"
