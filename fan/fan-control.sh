#!/bin/bash
# Sandbells Fan Control Wrapper
# Calls the original zynthian PWM fan script

cd /home/sandbells/Code/Sandbells/fan

# Optional debug
# export DEBUG=true

exec /usr/bin/python3 ./zynthian-pwm-fan.py
