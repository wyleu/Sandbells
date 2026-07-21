# Sandbells Kiosk Install Guide (Pi 3 + Luakit + HDMI)

Designed for **simple operation by non-technical users** (mouse only, no keyboard required).

## What you get after install

1. On every boot the HDMI screen automatically shows the Sandbells web app in **fullscreen Luakit**.
2. Screen **never blanks**.
3. Django runs under **Gunicorn** behind **Nginx**.
4. Static files are collected and served efficiently by Nginx.
5. Everything is supervised by systemd and restarts automatically if it crashes.

## Prerequisites

- Raspberry Pi 3 (or similar) running Raspberry Pi OS (Bookworm/Bullseye)
- User `sandbells` already exists (created by earlier install-steps)
- Project cloned to `/home/sandbells/Code/Sandbells`
- You are on branch `luakit-kiosk-dev` (or have merged these files)

## Quick install (recommended)

```bash
cd ~/Code/Sandbells
git pull origin luakit-kiosk-dev   # if you have network

# Make everything executable
chmod +x master_install.sh install-steps/*.sh start-kiosk-solo.sh

# Run the full installer (or --quick to skip pauses)
./master_install.sh
#  – or just the new steps:
# ./install-steps/12-django-venv.sh
# ./install-steps/13-gunicorn-nginx.sh
# ./install-steps/14-kiosk-systemd.sh

sudo reboot
```

After reboot you should see the Sandbells interface full-screen on the HDMI monitor.

## What the new install steps do

| Step | File                      | Purpose                                                                 |
|------|---------------------------|-------------------------------------------------------------------------|
| 12   | `12-django-venv.sh`       | Create `Bellvirtenv`, `pip install -r requirements.txt`, migrate, `collectstatic` → `/var/www/sandbells/static` |
| 13   | `13-gunicorn-nginx.sh`    | Install Nginx + Gunicorn socket/service, drop production nginx.conf     |
| 14   | `14-kiosk-systemd.sh`     | Install `sandbells-kiosk.service`, disable blanking (xset + lightdm + boot config), enable on `graphical.target` |

`master_install.sh` automatically runs every `install-steps/NN-*.sh` in order, so the new steps are picked up with no further changes.

## Key files added / updated

```
start-kiosk-solo.sh                 ← robust launcher (blanking off, URL fallback, lightdm wait)
systemd/sandbells-kiosk.service     ← the boot service
systemd/gunicorn.service            ← updated for user sandbells
systemd/gunicorn.socket
nginx/nginx.conf                    ← production config (static + proxy)
luakit/rc.lua                       ← fullscreen + lighter module load
install-steps/05-packages.sh        ← now includes nginx + build deps
install-steps/12-django-venv.sh
install-steps/13-gunicorn-nginx.sh
install-steps/14-kiosk-systemd.sh
TODO.md                             ← updated
```

## Screen blanking – how it is defeated

Multiple layers (belt-and-braces):

1. `start-kiosk-solo.sh` runs `xset s off / -dpms / s noblank / dpms 0 0 0` every start.
2. `~/.xprofile` does the same when the graphical session begins.
3. `/etc/X11/Xsession.d/99-sandbells-noblank` system-wide.
4. lightdm seat: `xserver-command=X -s 0 -dpms`
5. `/boot/config.txt` (or firmware): `hdmi_blanking=1`

If blanking ever returns, run:

```bash
DISPLAY=:0 xset q
```

and check that Screen Saver and DPMS timeouts are 0.

## Day-to-day commands

```bash
# Kiosk
sudo systemctl status sandbells-kiosk
sudo systemctl restart sandbells-kiosk
journalctl -u sandbells-kiosk -f

# Web stack
sudo systemctl status gunicorn nginx
sudo systemctl restart gunicorn
sudo systemctl reload nginx          # after editing nginx.conf

# After Django code change
cd ~/Code/Sandbells
source Bellvirtenv/bin/activate
cd changes
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl reload gunicorn
```

## Troubleshooting

| Symptom                        | Fix |
|--------------------------------|-----|
| Black screen / blanking        | `DISPLAY=:0 xset s off; xset -dpms` then restart kiosk service |
| Luakit shows “Offline”         | Check `systemctl status gunicorn nginx`; look at `journalctl -u gunicorn` |
| Permission errors on socket    | `ls -l /run/gunicorn.socket` should be owned by sandbells |
| Static files 404               | Re-run step 12; confirm files in `/var/www/sandbells/static` |
| Service fails because X not up | The start script waits up to 30 s for X; check lightdm is enabled |

## Reverting / stopping the kiosk

```bash
sudo systemctl disable --now sandbells-kiosk
# Then you can start manually with:
# ~/Code/Sandbells/start-kiosk-solo.sh
```

---

*Little-old-lady friendly: once installed, just power the Pi on. The bells appear on the TV.*
