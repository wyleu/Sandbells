# Reboot and Shut down (farm status page)

The farm status page of **this machine** (the entry in the farm registry that
is the Sandbells running Django: a `sandbells` entry polling `127.0.0.1` /
`localhost` or its own host name) has a **Reboot** and a **Shut down** button in
its top line.  They act on this machine only.  They never reach another
Sandbells, a Pico or any other device, and they are not shown on those pages.

## Using it

1. Press **Reboot** or **Shut down**.  The buttons are replaced by a confirm
   button that names the machine (*Yes, reboot sandbells now*) and a note saying
   what will happen, plus **Cancel**.  It cancels itself after 5 s.
2. Press the confirm button.  Sandbells answers at once and does it about 2 s
   later, so the browser gets its reply.
3. Reboot: the page says *Rebooting sandbells… reconnect shortly* and polls
   `/control/ping/` until Sandbells answers on a **new boot** (it compares the
   kernel's boot id), then reloads itself.  Shut down: the page says to wait for
   the green light to stop before unplugging; it stays off until power is cycled.
4. If something is wrong the page says so (*Not done: …*) and nothing happens.

## Enabling it on a Pi (one-off, on each Pi that should have the buttons)

The web user (the `User=` of `systemd/gunicorn.service`, `sandbells`) needs a
narrow sudo rule.  After the code is on the Pi run, as a normal user:

```
bash ~/Code/Sandbells/install-steps/19-power.sh true
```

It asks for your sudo password, writes `/etc/sudoers.d/sandbells-power`
(mode 0440, checked with `visudo -cf` first and `visudo -c` after; only
replaced if it changed, so it can be run again), and then checks the rule
without rebooting.  The whole file is:

```
sandbells ALL=(root) NOPASSWD: /usr/bin/systemctl reboot, /usr/bin/systemctl poweroff
```

Exactly those two commands, with those exact arguments: nothing else.
`master_install.sh` runs this step too (it runs every `install-steps/NN-*.sh`).
`sandbells_reset.sh` does not run it.  The static files (power.css/js) come
with the usual `sandbells_reset.sh`.

**If the rule is missing** the button answers *reboot is not enabled on
sandbells: the sudoers rule is missing. Run install step 19 on it* and does
nothing (the server asks `sudo -n -l` first, which only lists permissions).

## How it works / safety

* `POST /control/reboot/` and `POST /control/poweroff/` (`bells/controls.py`):
  POST only (405), Django CSRF token (403), and refused (403) unless the
  browser is on the Pi or the LAN: loopback, private or link-local addresses
  (the last `X-Forwarded-For` hop behind nginx).
* One action at a time: a second request while one is pending answers 409
  (the memory of it lapses after 3 minutes, or at once if the command could
  not be started).
* The command runs 2 s after the reply, detached, as
  `sudo -n /usr/bin/systemctl reboot` (or `poweroff`).
* Every request is logged with the client address:
  `journalctl -u gunicorn | grep "control "`.
* `GET /control/ping/` (LAN only) returns the machine name and boot id.
* Colours: neutral buttons, gold for the confirm and messages.  No red (kept
  for "not coming").

## Tests

`python manage.py test bells.tests_power`: the views with the sudo check and
the command mocked (nothing is ever rebooted), method / CSRF / address /
rate-limit / missing-rule checks, page partial shown only for the local
machine, the install step's rule text (and `visudo -cf` when available), and
the page's JS helpers with `node --test changes/bells/js_tests/`.
