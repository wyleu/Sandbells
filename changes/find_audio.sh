#!/bin/bash
echo "===  Audio Search in Sandbells /changes Directory ==="
echo "Current directory: $(pwd)"
echo "Date: $(date)"
echo "--------------------------------------------------"

cd /home/wyleu/Code/Sandbells/changes 2>/dev/null || {
    echo "ERROR: changes directory not found!"
    exit 1
}

echo "1. AUDIO FILES FOUND:"
find . -type f \( -name "*.webm" -o -name "*.mp3" -o -name "*.wav" -o -name "*.ogg" -o -name "*.m4a" -o -name "*.opus" \) | sort

echo -e "\n2. CODE REFERENCES (howler, drums, audio, sound, etc.):"
grep -rE --include="*.js" --include="*.html" --include="*.htm" --include="*.py" \
    "(howler|drums\.webm|webm|audio|sound|drum|bell\.mp3|Audio|Howl)" . 2>/dev/null | head -50

echo -e "\n3. HOWLER.JS LIBRARY FILES:"
find . -name "*howler*" -type f

echo -e "\n4. Directories containing potential static assets:"
find . -name "static" -o -name "bells" -o -name "drums" -o -name "icons" -type d

echo -e "\n=== Search Complete ==="
