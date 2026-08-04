# Sandbells

**Django-based Church Bell Change-Ringing Display and Kiosk**

Sandbells is a web application that computes and displays the step-by-step sequences of change ringing (English-style method ringing) between named patterns such as Rounds, Jokers, Titums, Whittington’s, Queens, and many others.

It is designed to run as a fullscreen kiosk on a Raspberry Pi attached to an HDMI television or monitor. The interface is intended for simple, mouse-only operation by non-technical users.

![Sandbells Kiosk Screenshot](docs/screenshot-20260722-144857.png)

*(Full-screen view on Raspberry Pi – clock, dual-direction change sequences, method selector, and live system status)*

---

## What you see on the screen

- Analogue and digital clock and current date (top-left)
- Two side-by-side columns showing the complete transition (e.g. Rounds to Jokers and the reverse)
- Each row shows the current order of the bells together with the adjacent swaps that produce the next row
- Right-hand sidebar listing available methods for 4–8 bells
- System status overlay under the clock:
  - **Browser** — screen / body / iframe sizes
  - **Network** — WiFi (and SSID), wired, IP addresses, recovery fallback
  - **Server** — hostname (.local), git branch/hash, Nginx / Gunicorn / Kiosk
  - **Hardware** — Pi model, arch, memory, temperature, fan percent
  - **Time** — chrony source / lock (10.42.0.1, sandmon.local, sandgps*, or NO LOCK)

Tower deployment is intended to work with or without Internet: local WiFi (for example the Sandbells AP on sandmon) and/or Ethernet, with GPS-backed time from a local server.

---

## Architecture overview

HDMI display runs Luakit fullscreen against http://localhost (with fallbacks in start-kiosk-solo.sh).

On the Pi (kiosk host such as sandbells or sandbells2):

- **sandbells-kiosk.service** — Luakit after LightDM
- **gunicorn** / **nginx** — Django and static files
- **sandbells-fan.service** — PWM fan; duty file under /run
- **sandbells-time-select** — chrony sources from settings.json time_hosts
- **sandbells-network-select.timer** — local net check and WiFi SSID fallback list
- **sandbells-early-status** — optional console status before LightDM (install step 16)

Config file: **/etc/sandbells/settings.json**

Django project: **changes/** with app **bells/** (models, functions.db_process, views, status_views, templates, static).

Optional tower infrastructure (separate repository):

- **sandmon.local** — WiFi AP (SSID Sandbells) and GPS/PPS chrony stratum 1
- https://github.com/wyleu/Sandmon

### Core logic

The heart of the system is bells/functions.py → db_process(). Given two patterns of equal length, it repeatedly swaps adjacent pairs until the target is reached, recording every intermediate row and the calls. The same process is run in reverse so both directions are shown at once.

---

## Configuration

Path: **/etc/sandbells/settings.json**

Created from install-steps/settings.example.json on first install. Typical content:

    {
      "networks": [
        { "ssid": "Sandbells", "psk": "CHANGE_ME" }
      ],
      "time_hosts": [
        "10.42.0.1",
        "sandmon.local",
        "sandgps.local",
        "sandgps1.local",
        "sandgps2.local",
        "sandgps3.local"
      ],
      "ethernet": {
        "dhcp_timeout_sec": 15,
        "fallback_ip": "192.168.99.2",
        "fallback_prefix": 24
      },
      "status": {
        "poll_hint_sec": 3
      }
    }

- **networks** — SSIDs used by network-select / WiFi setup
- **time_hosts** — ordered list for chrony (first entry is preferred when sources are written)
- **ethernet** — static recovery when DHCP fails on the tower cable

Do not commit real WiFi passwords; keep secrets only on the machine.

---

## Local network and time

- No Internet is required in the tower if sandmon (or another GPS time host) is reachable on the LAN or AP.
- **Time:** sandbells-time-select.sh reads time_hosts, writes /etc/chrony/sources.d/sandbells.sources, and restarts chrony with a timeout. The systemd unit is ordered After=chrony (never Before=chrony) so boot cannot deadlock.
- **Network:** sandbells-network-select.sh checks local reachability; if down, tries configured SSIDs. Driven by a timer; also runnable by hand as: sudo sandbells-network-select.sh
- **AP and GPS time:** Sandmon provides SSID Sandbells, AP address 10.42.0.1, hostname sandmon.local, and chrony stratum 1 from GPS/PPS.
- Install pattern: a numbered step installs the helper into /usr/local/sbin and the unit file from the repo **systemd/** directory only.

---

## Quick start (fresh install)

    cd ~/Code
    git clone https://github.com/wyleu/Sandbells.git
    cd Sandbells

    chmod +x master_install.sh install-steps/[0-9][0-9]-*.sh start-kiosk-solo.sh

    ./master_install.sh
    # or: ./master_install.sh --quick

    # Then set real SSIDs/passwords and time_hosts if needed:
    # sudo nano /etc/sandbells/settings.json

    sudo reboot

After reboot the kiosk should appear on the HDMI screen.

### Services after a successful install

- **sandbells-kiosk** — Luakit fullscreen (enabled at install; starts on boot after LightDM)
- **gunicorn** / **nginx** — Django app and static files
- **sandbells-fan** — PWM fan
- **sandbells-time-select** — ensure chrony sources from time_hosts
- **sandbells-network-select.timer** — local net and WiFi fallback
- **sandbells-early-status** — optional pre-LightDM console status (step 16)

### Day-to-day commands

    systemctl status sandbells-kiosk
    sudo systemctl restart sandbells-kiosk
    journalctl -u sandbells-kiosk -f

    sudo systemctl restart gunicorn nginx

    cd ~/Code/Sandbells
    source Bellvirtenv/bin/activate
    cd changes
    python manage.py migrate
    python manage.py collectstatic --noinput
    sudo systemctl reload gunicorn

    curl -s http://localhost/api/system-status/ | python3 -m json.tool

    sudo sandbells-time-select.sh
    chronyc sources -v
    sudo sandbells-network-select.sh

    systemctl status sandbells-fan
    cat /run/sandbells-fan.pct

---

## Systemd layout

- **systemd/** in this repository is the only place unit files are maintained.
- **install-steps** copy those units into /etc/systemd/system and enable them. Prefer install -m 644 from the repo path.
- Do not rely on long-term hand edits under /etc/systemd/system.

Kiosk unit: After=lightdm.service and WantedBy=graphical.target. Do not use After=graphical.target on the kiosk unit (that deadlocks with WantedBy=graphical.target).

Time-select unit: After=chrony.service and TimeoutStartSec=60. Do not use Before=chrony while the script restarts chrony.

Install step 14 installs and enables the kiosk service; it does not start it during the install. The unit starts on the next reboot, or with:

    sudo systemctl start sandbells-kiosk

---

## Project layout

    Sandbells/
    ├── changes/                 # Django project
    │   └── bells/               # models, db_process, views, status API, templates, static
    ├── fan/
    ├── install-steps/           # numbered NN-*.sh steps and runtime helpers
    │   ├── settings.example.json
    │   └── sandbells-common.sh
    ├── systemd/                 # all unit files (source of truth)
    ├── nginx/
    ├── luakit/
    ├── start-kiosk-solo.sh
    ├── master_install.sh
    ├── INSTALL-KIOSK.md
    ├── TODO.md
    └── README.md

master_install.sh runs every install-steps/[0-9][0-9]-*.sh in filename order (including 16-early-status when present).

---

## Recovery Ethernet (no DHCP / tower cable)

When the kiosk has no home LAN and uses the static fallback:

- Kiosk eth0: 192.168.99.2/24
- Admin laptop USB Ethernet: 192.168.99.1/24

On the admin machine:

    ./sandbells-eth-link.sh

Or manually set the USB Ethernet interface to 192.168.99.1/24, then:

    ping -c 2 192.168.99.2
    ssh sandbells@192.168.99.2

Use the USB Ethernet interface, not WiFi. Home WiFi (192.168.0.x) will not reach 192.168.99.2.

---

## Current status (August 2026)

Working:

- Kiosk auto-start after LightDM, blanking defeat, Gunicorn and Nginx
- Dual-direction display, method selector, clock, status panel
- Fan service and duty file
- Network-select timer and helper
- Time-select from settings time_hosts (sandmon, 10.42.0.1, sandgps*)
- Chrony sources.d layout; boot-safe time-select and kiosk unit ordering
- Early-status unit (step 16)
- Recovery Ethernet fallback

Still open:

- Fan curve (quieter ramp)
- UI polish; Luakit/WebKit CPU on smaller Pis
- Log rotation and monitoring

See TODO.md for the live checklist.

---

## Development notes

- Default number of bells is 8.
- Patterns are stored as simple strings such as "12345678".
- Intermediate steps can be stored on the Change model or generated live via db_process().
- MIDI export of patterns is supported.
- REST endpoints under /api/ include system status and some model APIs.

---

## Licence and credits

Church-bell change ringing is a centuries-old English tradition. This software is a practical tool to help ringers visualise and practise the methods.

- Repository: https://github.com/wyleu/Sandbells
- Tower AP and GPS time: https://github.com/wyleu/Sandmon

Last updated: 4 August 2026 (branch main)
