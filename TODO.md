# Sandbells TODO List

## Current Priorities (Kiosk Recovery)

- [x] Restore working luakit kiosk on Pi
- [x] Self-starting on boot (systemd)          ← step 14 + sandbells-kiosk.service
- [x] Gunicorn / runserver working             ← step 13
- [x] Django venv + collectstatic + migrate    ← step 12
- [ ] Make kiosk run cleanly as user `sandbells` (not root)
- [ ] Reduce luakit/WebKit memory usage (multiple processes)
- [ ] Full kiosk mode (no tabs/edge clutter via Lua)
- [ ] Get a better AI

## Nice to Have

- [ ] Dynamic SVG system info (Pi model, arch, git branch, DEBUG, memory)
- [ ] Log rotation for monitor + better logging
- [ ] Production-ready gunicorn + nginx setup   ← largely done in step 13
- [ ] Better cursor / UI polish
- [ ] sandbells2.local test machine setup
- [ ] Automated installer improvements
- [ ] Screen blanking fully eliminated under all conditions

## Done Recently

- [x] Monitor script + systemd service
- [x] Git branch `kiosk-recovery` / `luakit-kiosk-dev` with working state
- [x] Basic fullscreen Lua config
- [x] Cursor visibility
- [x] Backend server running
- [x] start-kiosk-solo.sh with robust blanking disable + URL fallback
- [x] sandbells-kiosk.service (graphical.target)
- [x] install-steps 12 / 13 / 14

## How to finish a fresh install

```bash
cd ~/Code/Sandbells
git pull
chmod +x install-steps/*.sh master_install.sh start-kiosk-solo.sh
./master_install.sh          # # or ./master_install.sh --quick
sudo reboot
```

After reboot the kiosk should appear automatically on the HDMI screen.

### Manual one-shot (if you only need the new bits)

```bash
./install-steps/12-django-venv.sh
./install-steps/13-gunicorn-nginx.sh
./install-steps/14-kiosk-systemd.sh
sudo reboot
```

### Useful commands for the little-old-lady operators (or remote helpers)

| Action                    | Command                                      |
|---------------------------|----------------------------------------------|
| Status of kiosk           | `systemctl status sandbells-kiosk`           |
| Restart kiosk             | `sudo systemctl restart sandbells-kiosk`     |
| Restart web stack         | `sudo systemctl restart gunicorn nginx`      |
| Watch kiosk log           | `journalctl -u sandbells-kiosk -f`           |
| Disable blanking now      | `DISPLAY=:0 xset s off; xset -dpms`          |

Last updated: 2026-07-21
