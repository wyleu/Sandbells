# Sandbells

**Django-based Church Bell Change-Ringing Display & Kiosk**

Sandbells is a web application that computes and displays the step-by-step sequences of **change ringing** (English-style method ringing) between named patterns such as *Rounds*, *Jokers*, *Titums*, *Whittington’s*, *Queens*, etc.

It is designed to run as a **fullscreen kiosk** on a Raspberry Pi attached to an HDMI television or monitor. The interface is intended for simple, mouse-only operation by non-technical users.

![Sandbells Kiosk Screenshot](docs/screenshot-20260722-144857.png)
*(Full-screen view on Raspberry Pi – clock, dual-direction change sequences, method selector, and live system status)*

---

## What You See on the Screen

- **Analogue + digital clock** and current date (top-left)
- Two side-by-side columns showing the complete transition:
  - Left: e.g. **Rounds → Jokers**
  - Right: the reverse **Jokers → Rounds**
- Each row shows the current order of the bells (e.g. `17654328`) together with the adjacent swaps that produce the next row (e.g. `2 to 4  3 to 2  8 to 3`)
- Right-hand sidebar listing every available method for the selected number of bells (4–8). Clicking a method loads the corresponding change.
- **System status overlay** (under the clock), in sections:
  - **Browser** — screen / body / iframe sizes
  - **Network** — WiFi (+ SSID), wired, IP addresses
  - **Server** — hostname (`.local`), git branch/hash, Nginx / Gunicorn / Kiosk
  - **Hardware** — Pi model, arch, memory, temperature, fan %
  - **Time** — chrony source / lock (`sandgps*` or `NO LOCK`)
The application supports 4–8 bells and many classic methods (Rounds, Titums, Whittington’s, Sew Saw, Back Rounds, Bowbells, Burdette, Hagdyke, Jacks, Jokers, Kings, Princes, Princesses, Priory, Queens, Roller Coaster, St Michael’s, Exp-ing Titums, Total Rev, …).
The tower deployment is intentionally **offline** (no Internet): local WiFi and/or Ethernet, plus a GPS time server on the LAN (`sandgps*.local`). That suits limited technical support and church environments.
---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  HDMI Display (TV / Monitor)                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Luakit (fullscreen kiosk browser)                    │  │
│  │  → http://localhost (fallbacks in start-kiosk-solo.sh)│  │  
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          ▲
                          │
┌─────────────────────────────────────────────────────────────┐
│  Raspberry Pi (typically Pi 3)                              │
│                                                             │
│  systemd services:                                          │
│  • sandbells-kiosk.service  (Luakit on boot)                │
│  • gunicorn / nginx         (Django + static)               │
│  • sandbells-fan.service    (PWM fan → /run/…fan.pct)       │
│  • sandbells-time-select    (prefer sandgps*.local)         │
│  • sandbells-network-select.timer                           │
│      (local net check + WiFi SSID fallback list)            │
│                                                             │
│  Django project: changes/                                   │
│  └── app: bells/                                            │
│      ├── models.py      (Pattern, Change, ChangeItem…)      │
│      ├── functions.py   (db_process – the core engine)      │
│      ├── views.py       (display, menu, clock, …)           │
       ├──  status_views.py (/api/system-status/)             │
│      ├── templates/     (display.html, home.html, …)        │
│      └── static/        (CSS, JS, SVG, audio)               │
└─────────────────────────────────────────────────────────────┘
```

### Core Logic
The heart of the system is `bells/functions.py` → `db_process()`.  
Given two patterns of equal length (e.g. `"12345678"` and `"17654328"`), it repeatedly swaps adjacent pairs until the target is reached, recording every intermediate row and the calls (“7 to 5”, “6 to 7”, …). The same process is run in reverse so both directions are shown simultaneously.

---

### Local network & time

- No Internet required in the tower.
- **Time:** `sandbells-time-select.sh` probes `sandgps*.local` and prefers that server in chrony.
- **Network:** `sandbells-network-select.sh` (NetworkManager) checks local reachability; if down, tries configured SSIDs (e.g. `sandbells`). Driven by a systemd timer; also runnable by hand for debug:
  `sudo sandbells-network-select.sh`
- Install pattern matches time: numbered step installs the `sandbells-*-select` helper + unit/timer.

---

## Quick Start (Fresh Install on Raspberry Pi)

```bash
# Clone / update
cd ~/Code
git clone https://github.com/wyleu/Sandbells.git   # or git pull
cd Sandbells

# Make scripts executable
chmod +x master_install.sh install-steps/*.sh start-kiosk-solo.sh

# Run the full installer (or --quick)
./master_install.sh

# Reboot – the kiosk should appear automatically on the HDMI screen
sudo reboot
```

After reboot the following services should be active:

| Service               | Purpose                                   |
|-----------------------|-------------------------------------------|
| `sandbells-kiosk`     | Launches Luakit fullscreen                |
| `gunicorn`            | Runs the Django application               |
| `nginx`               | Serves static files + proxies to Gunicorn |
| sandbells-fan         | PWM fan; writes /run/sandbells-fan.pct    |
| sandbells-time-select | Prefer GPS NTP on LAN                     |
| sandbells-network-select.timer | Local net + WiFi fallback        |


### Useful day-to-day commands

```bash
# Kiosk
systemctl status sandbells-kiosk
sudo systemctl restart sandbells-kiosk
journalctl -u sandbells-kiosk -f

# Web stack
sudo systemctl restart gunicorn nginx
sudo systemctl reload nginx          # after nginx.conf changes

# After code changes
cd ~/Code/Sandbells
source Bellvirtenv/bin/activate
cd changes
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl reload gunicorn
# Status API
curl -s http://localhost/api/system-status/ | python3 -m json.tool

# Network helper
sudo sandbells-network-select.sh
journalctl -t sandbells-net -f

# Fan
systemctl status sandbells-fan
cat /run/sandbells-fan.pct

# Venv (must be sourced)
source ~/Code/Sandbells/sandbells_env.sh

```

---

## Project Layout (high level)

```
Sandbells/
├── changes/                     # Django project root
│   ├── bells/
│   │   ├── models.py
│   │   ├── functions.py         # db_process()
│   │   ├── status_views.py      # /api/system-status/
│   │   ├── views.py             # display, menu, clock, …
│   │   ├── templates/bells/
│   │   └── static/
│   ├── manage.py
│   └── requirements.txt
├── fan/
│   ├── sandbells-fan.py         # PWM fan (Zynthian-inspired; adapted)
│   └── fan-control.sh
├── install-steps/               # 01–15… + sandbells-*-select helpers
├── systemd/                     # kiosk, fan, time-select, network-select, …
├── nginx/
├── luakit/
├── start-kiosk-solo.sh
├── master_install.sh
├── INSTALL-KIOSK.md
├── TODO.md
└── README.md
```

---

## Current Status (July 2026)

Working

Kiosk auto-start, blanking defeat, Gunicorn + Nginx
Dual-direction display, method selector, clock, 1920 layout
Sectioned status panel (network, temp, fan %, .local, NTP)
Fan service + duty file (curve still to quieten)
Kiosk URL fallbacks (curl -f)
Network-select timer + helper
Time-select for sandgps*.local

Still open

Fan curve (quieter ramp; service loud at ~65 °C)
Non-root kiosk polish
UI polish; Luakit/WebKit CPU on Pi 3
Log rotation & monitoring
Ensure 15-network-select on every fresh install

See `TODO.md` for the live checklist.

---

## Development Notes

- Default number of bells is 8.
- Patterns are stored as simple strings (`"12345678"`, `"17654328"`, …).
- The `Change` model can pre-compute and store intermediate steps; the live display can also generate them on the fly via `db_process()`.
- MIDI export of any pattern is supported.
- The application includes REST endpoints (`/api/`) for some models.

---

## Recovery Ethernet (no DHCP / tower cable)

When sandbells2 has no home LAN and uses the static fallback:

| Host        | Interface     | Address            |
|-------------|---------------|--------------------|
| sandbells2  | eth0          | `192.168.99.2/24`  |
| Admin laptop| USB Ethernet  | `192.168.99.1/24`  |

**On the admin machine** (not automatic):

```bash
# Sandbells_connect (or equivalent)
./sandbells-eth-link.sh          # sets dongle to 192.168.99.1, pings .2
# or manually:
sudo ip link set eth1 up
sudo ip addr flush dev eth1
sudo ip addr add 192.168.99.1/24 dev eth1
ping -c 2 192.168.99.2
ssh sandbells@192.168.99.2

Use the USB Ethernet iface (eth1 etc.), not WiFi.
Home WiFi (192.168.0.x) will not reach 192.168.99.2.
Status panel: using_fallback: true, wired_method: static.
API on-box: curl -sS http://127.0.0.1/api/system-status/ | python3 -m json.tool
From laptop, prefer Host: sandbells2.local if nginx returns 444 for raw IP.


## Licence & Credits

Church-bell change ringing is a centuries-old English tradition.  
This software is a practical tool to help ringers visualise and practise the methods.

Repository: https://github.com/wyleu/Sandbells

---

*Last updated: 24 July 2026*
*Branch / date — main, July 2026
