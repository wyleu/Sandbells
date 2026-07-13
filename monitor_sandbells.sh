#!/bin/bash
LOGFILE="/var/log/sandbells-monitor.log"
echo "$(date) - Monitor started" >> $LOGFILE

while true; do
    TIMESTAMP=$(date)

    if ! pgrep -f "luakit" > /dev/null; then
        echo "$TIMESTAMP - Luakit not running. Restarting..." >> $LOGFILE
        systemctl restart luakit-kiosk.service
    fi

    if ! pgrep -f "gunicorn" > /dev/null; then
        echo "$TIMESTAMP - Gunicorn not running. Restarting..." >> $LOGFILE
        systemctl restart sandbells
    fi

    HIGH_CPU=$(ps -eo pid,%cpu,comm | grep -i WebKitWebProcess | awk '{print $2}' | sort -nr | head -1 | awk '{print int($1)}' || echo 0)
    if [ "$HIGH_CPU" -gt 70 ]; then
        echo "$TIMESTAMP - High CPU ($HIGH_CPU%). Restarting Luakit..." >> $LOGFILE
        systemctl restart luakit-kiosk.service
        sleep 10
    fi

    MEM_USED=$(free -m | awk 'NR==2 {print $3}')
    if [ "$MEM_USED" -gt 650 ]; then
        echo "$TIMESTAMP - High memory ($MEM_USED MiB). Restarting Luakit..." >> $LOGFILE
        systemctl restart luakit-kiosk.service
        sleep 10
    fi

    sleep 15
done
