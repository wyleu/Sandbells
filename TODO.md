# Sandbells TODO List

## Current Priorities (Kiosk Recovery)
- [x] Restore working luakit kiosk on Pi
- [x] Self-starting on boot (systemd)
- [x] Gunicorn / runserver working
- [ ] Make kiosk run cleanly as user `wyleu` (not root)
- [ ] Reduce luakit/WebKit memory usage (multiple processes)
- [ ] Full kiosk mode (no tabs/edge clutter via Lua)
- [ ] Get a better AI
## Nice to Have
- [ ] Dynamic SVG system info (Pi model, arch, git branch, DEBUG, memory)
- [ ] Log rotation for monitor + better logging
- [ ] Production-ready gunicorn + nginx setup
- [ ] Better cursor / UI polish
- [ ] sandbells2.local test machine setup
- [ ] Automated installer improvements

## Done Recently
- [x] Monitor script + systemd service
- [x] Git branch `kiosk-recovery` with working state + tag
- [x] Basic fullscreen Lua config
- [x] Cursor visibility
- [x] Backend server running

Last updated: $(date)
