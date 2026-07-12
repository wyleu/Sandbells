#!/bin/bash
# Sandbells System Monitor
# Monitors services and resources, logs to file

LOGFILE="/var/log/sandbells-monitor.log"
INTERVAL=30  # seconds

echo "=== Sandbells Monitor Started at $(date) ===" >> $LOGFILE

while true; do
  TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
  
  echo "[$TIMESTAMP] === Resource Usage ===" >> $LOGFILE
  echo "Memory:" >> $LOGFILE
  free -h >> $LOGFILE
  echo "CPU Load:" >> $LOGFILE
  uptime >> $LOGFILE
  
  echo "Running Services:" >> $LOGFILE
  systemctl list-units --type=service --state=running | grep -E 'gunicorn|nginx|luakit|kiosk' >> $LOGFILE || echo "No matching services" >> $LOGFILE
  
  echo "Top Processes:" >> $LOGFILE
  ps aux --sort=-%mem | head -10 >> $LOGFILE
  
  echo "Luakit Processes:" >> $LOGFILE
  ps aux | grep -E 'luakit' | grep -v grep >> $LOGFILE || echo "No luakit" >> $LOGFILE
  
  echo "----------------------------------------" >> $LOGFILE
  
  sleep $INTERVAL
done
