#!/bin/bash
# Sandbells Kiosk Monitor - Resource Guard

LOGFILE="/var/log/sandbells-monitor.log"
echo "$(date) - Monitor started" >> $LOGFILE

while true; do
    # Check if Luakit is running
    if ! pgrep -f "luakit" > /dev/null; then
        echo "$(date) - Luakit not running. Restarting kiosk..." >> $LOGFILE
        /home/wyleu/Code/Sandbells/sandbells_startLuakit.sh &
    fi

    # Check memory usage (kill if too high)
    MEM_USAGE=$(ps -p $(pgrep -f luakit || echo 0) -o %mem= 2>/dev/null | tr -d ' ')
    if (( $(echo "$MEM_USAGE > 70" | bc -l 2>/dev/null || echo 0) )); then
        echo "$(date) - High memory usage ($MEM_USAGE%). Killing Luakit." >> $LOGFILE
        pkill -9 luakit
        sleep 2
    fi

    # Restart Gunicorn if workers are dead
    if ! pgrep -f gunicorn > /dev/null; then
        echo "$(date) - Gunicorn dead. Restarting..." >> $LOGFILE
        cd /home/wyleu/Code/Sandbells && /opt/sandbells/Bellvirtenv/bin/gunicorn --workers 2 --bind 0.0.0.0:8000 changes.wsgi:application &
    fi

    sleep 10
done
