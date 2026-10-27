"""Hardware controls: CSRF-protected POST actions that return JSON.

Same shape as the Shut down control that was first built on the old front
page: one view, POST /control/<name>/, dispatching on a small registry.

    @control("reboot")
    def reboot(request):
        ...
        return {"message": "..."}          # 200, {"ok": true, ...}

An action raises ControlError("why", status) to answer {"ok": false, ...}.

Rules every action keeps:
  * POST only (405 otherwise) and Django's CSRF token (403 without it);
  * refused (403) unless the browser is on this Pi or the LAN (loopback /
    private / link-local; the last X-Forwarded-For hop behind nginx);
  * the reply goes out first: the real work starts a couple of seconds later;
  * every request is logged with the client address.

The power controls (reboot, poweroff) act on THIS machine only: the one
running this Django.  They never reach another Pi or a Pico.  The gunicorn
user may run exactly `systemctl reboot` and `systemctl poweroff` through sudo
(install-steps/19-power.sh); without that rule the button answers "not
enabled" instead of failing silently.
"""

import ipaddress
import logging
import socket
import subprocess
import threading
import time
from urllib.parse import urlparse

from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

log = logging.getLogger(__name__)

CONTROLS = {}

SYSTEMCTL = "/usr/bin/systemctl"
POWER_DELAY_S = 2.0         # let the JSON reply reach the browser first
CHECK_TIMEOUT_S = 5
PENDING_TTL_S = 180         # one power action at a time; forgotten after this
BOOT_ID_FILE = "/proc/sys/kernel/random/boot_id"

POWER = {
    # name: (sudo command, what the page calls it)
    "reboot": (["sudo", "-n", SYSTEMCTL, "reboot"], "Rebooting"),
    "poweroff": (["sudo", "-n", SYSTEMCTL, "poweroff"], "Shutting down"),
}


class ControlError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


def control(name):
    """Register ``fn(request) -> dict`` as the control ``name``."""
    def register(fn):
        CONTROLS[name] = fn
        return fn
    return register


# ---- who is asking -------------------------------------------------------

def client_ip(request):
    """Browser address.  Behind nginx (gunicorn on a unix socket) REMOTE_ADDR
    is empty, so use the last X-Forwarded-For hop: the one nginx added."""
    addr = request.META.get("REMOTE_ADDR") or ""
    if not addr:
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        addr = xff.split(",")[-1].strip() if xff else ""
    return addr


def is_local(addr):
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_private or ip.is_link_local


def machine_name():
    return socket.gethostname().split(".")[0]


def is_this_machine(inst):
    """True for the farm registry entry that is this Sandbells machine: a
    sandbells-family entry polling loopback, or this machine's own host name.
    Remote Sandbells, Picos and everything else are False: no buttons there."""
    if (inst.get("family") or "sandbells") != "sandbells":
        return False
    host = (urlparse(inst.get("status_url") or "").hostname or "").lower()
    me = machine_name().lower()
    return host in ("", "127.0.0.1", "localhost", "::1", me, me + ".local")


def boot_id():
    try:
        with open(BOOT_ID_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


# ---- the view --------------------------------------------------------------

@require_POST
def control_action(request, name):
    fn = CONTROLS.get(name)
    if fn is None:
        return JsonResponse({"ok": False, "control": name,
                             "error": "unknown control"}, status=404)
    addr = client_ip(request)
    if not is_local(addr):
        log.warning("control %s refused from %r (not a local address)", name, addr)
        return JsonResponse({"ok": False, "control": name,
                             "error": "not allowed from this address"}, status=403)
    try:
        result = fn(request) or {}
    except ControlError as e:
        log.warning("control %s from %s not done: %s", name, addr, e)
        return JsonResponse({"ok": False, "control": name, "error": str(e)},
                            status=e.status)
    log.warning("control %s accepted from %s on %s", name, addr, machine_name())
    return JsonResponse({"ok": True, "control": name, **result})


@require_GET
@never_cache
def control_ping(request):
    """The page polls this after a reboot: it answers as soon as Django is up,
    and boot_id (changes on every boot) says whether it is the NEW boot."""
    if not is_local(client_ip(request)):
        return JsonResponse({"ok": False, "error": "not allowed from this address"}, status=403)
    return JsonResponse({"ok": True, "machine": machine_name(), "boot_id": boot_id()})


# ---- power controls --------------------------------------------------------

_lock = threading.Lock()
_pending = {"name": None, "at": 0.0}


def _permitted(cmd):
    """sudo -n -l <command> asks whether the sudoers rule exists (install step
    19) without running anything."""
    check = cmd[:2] + ["-l"] + cmd[2:]
    try:
        return subprocess.run(check, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL,
                              timeout=CHECK_TIMEOUT_S).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _run_power(name):
    """Runs POWER_DELAY_S after the reply: the detached sudo command."""
    try:
        subprocess.Popen(POWER[name][0], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        log.exception("%s failed to start", name)
        with _lock:
            _pending["name"] = None


def _power(name, request):
    cmd, verb = POWER[name]
    me = machine_name()
    if not _permitted(cmd):
        raise ControlError("%s is not enabled on %s: the sudoers rule is missing. Run "
                           "install step 19 on it (docs/power.md)." % (name, me), 503)
    with _lock:
        busy = _pending["name"]
        if busy and time.monotonic() - _pending["at"] < PENDING_TTL_S:
            raise ControlError("%s is already in progress on %s" % (busy, me), 409)
        _pending["name"], _pending["at"] = name, time.monotonic()
    timer = threading.Timer(POWER_DELAY_S, _run_power, args=(name,))
    timer.daemon = True
    timer.start()
    return {"message": "%s %s" % (verb, me), "machine": me,
            "delay_s": POWER_DELAY_S, "boot_id": boot_id()}


@control("reboot")
def reboot(request):
    return _power("reboot", request)


@control("poweroff")
def poweroff(request):
    return _power("poweroff", request)
