#!/bin/bash
export DISPLAY=:0
xset s off -dpms s noblank 2>/dev/null || true
matchbox-window-manager -use_titlebar no -use_cursor yes &
luakit "http://sandbells.local"
