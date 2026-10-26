"""config.py -- where the Sandtest rig (the Pico 2 W test rig) is.

The page and the two proxy views never take a host from the browser: the
address comes only from here, so the proxy can only ever talk to the rig.

  host    env SANDTEST_HOST, else "sandtest": {"host": ...} in settings.json,
          else sandtest.local.  "host" or "host:port"; a leading http:// and
          a trailing / are tolerated.  The Pico's DHCP address (for example
          192.168.0.198) is fine and is what to use when .local does not
          resolve.
  token   env SANDTEST_TOKEN, else "sandtest": {"token": ...}; sent to the
          rig as the X-Sandtest-Token header (the firmware's http.token).
          Empty = no header.  The token is never sent to the browser.

The settings.json is the one every other Sandbells page reads
(/etc/sandbells/settings.json, or $SANDBELLS_SETTINGS).  It is read on every
call, so changing it needs no restart.
"""
import os
import re
from dataclasses import dataclass

DEFAULT_HOST = "sandtest.local"
TIMEOUT_S = 2.0              # the longest one proxied call may take, in total
DEFAULT_PORT = 80

_HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?(:[0-9]{1,5})?$")


@dataclass(frozen=True)
class Config:
    host: str            # "name" or "name:port"; as typed if error is set
    token: str
    source: str          # "env", "settings.json" or "default"
    error: str = ""      # non-empty: the host setting is unusable

    @property
    def hostname(self):
        return self.host.rsplit(":", 1)[0] if ":" in self.host else self.host

    @property
    def port(self):
        return int(self.host.rsplit(":", 1)[1]) if ":" in self.host else DEFAULT_PORT

    @property
    def token_set(self):
        return bool(self.token)


def clean_host(raw):
    """-> (host, error).  Only a plain host name or IPv4 address, optional port."""
    h = str(raw or "").strip()
    if h.lower().startswith("http://"):
        h = h[7:]
    h = h.rstrip("/")
    if not _HOST_RE.match(h):
        return "", "SANDTEST_HOST %r is not a host name or address (use name or name:port)" % h
    if ":" in h and not 1 <= int(h.rsplit(":", 1)[1]) <= 65535:
        return "", "SANDTEST_HOST %r has a bad port" % h
    return h, ""


def _file_section():
    try:
        from bells.app_settings import _load
        raw, _path = _load()
    except Exception:
        return {}
    sec = raw.get("sandtest") if isinstance(raw, dict) else None
    return sec if isinstance(sec, dict) else {}


def load():
    sec = _file_section()
    env_host = os.environ.get("SANDTEST_HOST", "").strip()
    if env_host:
        raw, source = env_host, "env"
    elif str(sec.get("host") or "").strip():
        raw, source = sec["host"], "settings.json"
    else:
        raw, source = DEFAULT_HOST, "default"
    host, err = clean_host(raw)
    if err:
        host = str(raw).strip()[:80]       # shown as typed, next to the error
    token = os.environ.get("SANDTEST_TOKEN", "").strip() or str(sec.get("token") or "").strip()
    return Config(host=host, token=token, source=source, error=err)
