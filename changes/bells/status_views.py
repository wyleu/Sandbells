import json
import platform
import socket
import subprocess
import time
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse

from bells.app_settings import display_settings

SETTINGS_PATH = Path("/etc/sandbells/settings.json")


def _run(cmd, timeout=3):
    try:
        return subprocess.check_output(cmd, text=True, timeout=timeout).strip()
    except Exception:
        return ""


def _load_settings():
    try:
        if SETTINGS_PATH.is_file():
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _iface_operstate(iface: str) -> str:
    try:
        with open(f"/sys/class/net/{iface}/operstate") as f:
            return f.read().strip()
    except Exception:
        return "missing"


def _iface_ipv4(iface: str):
    """Return (ip, cidr) or ("", "")."""
    out = _run(["ip", "-4", "-o", "addr", "show", "dev", iface])
    for line in out.splitlines():
        parts = line.split()
        if "inet" in parts:
            i = parts.index("inet")
            if i + 1 < len(parts):
                cidr = parts[i + 1]  # e.g. 192.168.0.111/24
                ip = cidr.split("/")[0]
                return ip, cidr
    return "", ""


def _guess_ip_source(ip: str, cidr: str) -> str:
    if not ip:
        return "none"
    if ip.startswith("169.254."):
        return "link-local"
    # NM connection method if available
    out = _run(
        ["nmcli", "-t", "-f", "GENERAL.CONNECTION", "device", "show", "eth0"],
        timeout=2,
    )
    # Fallback: treat RFC1918 with /24 house ranges as dhcp-ish unknown
    return "assigned"


def _nm_method(iface: str) -> str:
    """dhcp | static | unknown | none"""
    try:
        out = _run(
            ["nmcli", "-t", "-f", "IP4.ADDRESS,GENERAL.STATE", "device", "show", iface],
            timeout=2,
        )
        if not out and not _iface_ipv4(iface)[0]:
            return "none"
    except Exception:
        pass
    # Connection method via active connection name is awkward; use addr presence
    ip, cidr = _iface_ipv4(iface)
    if not ip:
        return "none"
    if ip.startswith("169.254."):
        return "link-local"
    # Optional: nmcli -f ipv4.method connection show <name>
    try:
        conn = _run(
            ["nmcli", "-t", "-f", "GENERAL.CONNECTION", "device", "show", iface],
            timeout=2,
        )
        # format: GENERAL.CONNECTION:Wired connection 1
        name = conn.split(":")[-1].strip() if conn else ""
        if name and name != "--":
            method = _run(
                ["nmcli", "-t", "-f", "ipv4.method", "connection", "show", name],
                timeout=2,
            )
            # ipv4.method:auto / manual
            if "manual" in method:
                return "static"
            if "auto" in method:
                return "dhcp"
    except Exception:
        pass
    return "assigned"


def system_status(request):
    hostname = socket.gethostname()
    hostname_local = f"{hostname}.local"

    cfg = _load_settings()
    eth_cfg = cfg.get("ethernet") or {}
    fallback_ip = eth_cfg.get("fallback_ip") or "192.168.99.2"
    fallback_prefix = int(eth_cfg.get("fallback_prefix") or 24)
    status_cfg = cfg.get("status") or {}
    poll_hint_sec = int(status_cfg.get("poll_hint_sec") or 5)


    try:
        ips = _run(["hostname", "-I"]).split()
        ip_list = "  ".join(ips) if ips else "No Net"
    except Exception:
        ips = []
        ip_list = "No Net"

    wifi_state = _iface_operstate("wlan0")
    wired_state = _iface_operstate("eth0")
    wifi_ip, wifi_cidr = _iface_ipv4("wlan0")
    wired_ip, wired_cidr = _iface_ipv4("eth0")

    wifi_ssid = ""
    try:
        ssid = _run(["iwgetid", "-r"], timeout=2)
        if ssid:
            wifi_ssid = ssid
    except Exception:
        pass

    wired_method = _nm_method("eth0")
    wifi_method = _nm_method("wlan0")

    using_fallback = bool(wired_ip and wired_ip == fallback_ip)

    # Primary display IP: prefer wired, then wifi, then hostname -I
    ip = wired_ip or wifi_ip or (ips[0] if ips else "No Net")

    try:
        git_branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=settings.BASE_DIR.parent,
            text=True,
        ).strip()
        git_hash = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=settings.BASE_DIR.parent,
            text=True,
        ).strip()
    except Exception:
        git_branch = "unknown"
        git_hash = "unknown"

    try:
        with open("/sys/firmware/devicetree/base/model", "r") as f:
            pi_model = f.read().replace("\x00", "").strip()
    except Exception:
        pi_model = platform.machine()

    try:
        mem = subprocess.check_output(["free", "-h"], text=True)
        mem_line = [l for l in mem.splitlines() if l.startswith("Mem:")][0].split()
        memory = f"{mem_line[2]} / {mem_line[1]}"
    except Exception:
        memory = "unknown"

    # CPU % and 1-minute load
    cpu_pct = "—"
    load1 = "—"
    try:
        # 1-second sample via /proc/stat
        def _cpu_times():
            with open("/proc/stat") as f:
                fields = f.readline().split()[1:]
            return list(map(int, fields))

        t1 = _cpu_times()
        time.sleep(0.15)          # short sample, keeps the API snappy
        t2 = _cpu_times()
        idle1, idle2 = t1[3], t2[3]
        total1, total2 = sum(t1), sum(t2)
        idle_delta = idle2 - idle1
        total_delta = total2 - total1
        if total_delta > 0:
            cpu_pct = f"{100.0 * (1.0 - idle_delta / total_delta):.0f}%"
    except Exception:
        pass

    try:
        with open("/proc/loadavg") as f:
            load1 = f.read().split()[0]
    except Exception:
        pass

    throttled = "No"
    try:
        out = subprocess.check_output(["vcgencmd", "get_throttled"], text=True).strip()
        # "throttled=0x0" → No, anything else → Yes
        if not out.endswith("=0x0"):
            throttled = "Yes"
    except Exception:
        throttled = "—"


    temp_c = "—"
    try:
        out = subprocess.check_output(["vcgencmd", "measure_temp"], text=True)
        temp_c = out.strip().replace("temp=", "").replace("'C", "") + "°C"
    except Exception:
        pass

    fan_pct = "—"
    for path in ("/run/sandbells-fan.pct", "/tmp/sandbells-fan.pct"):
        try:
            with open(path) as f:
                fan_pct = f.read().strip() + "%"
                break
        except Exception:
            continue

    def svc(name):
        try:
            return subprocess.check_output(
                ["systemctl", "is-active", name], text=True
            ).strip()
        except Exception:
            return "unknown"

    time_source = "none"
    time_locked = False
    try:
        out = subprocess.check_output(["chronyc", "sources"], text=True, timeout=5)
        for line in out.splitlines():
            s = line.strip()
            if not s or s.startswith("MS") or s.startswith("="):
                continue
            if len(s) >= 2 and s[1] == "*":
                parts = s.split()
                time_source = parts[1] if len(parts) > 1 else "synced"
                time_locked = True
                break
        if not time_locked:
            for line in out.splitlines():
                if "sandgps" in line.lower():
                    time_source = "unreachable"
                    break
    except Exception:
        time_source = "unknown"
        time_locked = False

    time_label = time_source if time_locked else "NO LOCK"

    d = display_settings()

    return JsonResponse(
        {
            "hostname": hostname,
            "hostname_local": hostname_local,
            "ip": ip,
            "ip_list": ip_list,
            "wifi_state": wifi_state,
            "wifi_ssid": wifi_ssid,
            "wifi_ip": wifi_ip,
            "wifi_cidr": wifi_cidr,
            "wifi_method": wifi_method,
            "wired_state": wired_state,
            "wired_ip": wired_ip,
            "wired_cidr": wired_cidr,
            "wired_method": wired_method,
            "fallback_ip": fallback_ip,
            "fallback_prefix": fallback_prefix,
            "using_fallback": using_fallback,
            "git_branch": git_branch,
            "git_hash": git_hash,
            "arch": platform.machine(),
            "pi_model": pi_model,
            "memory": memory,
            "temp": temp_c,
            "fan": fan_pct,
            "debug": settings.DEBUG,
            "nginx": svc("nginx"),
            "gunicorn": svc("gunicorn"),
            "kiosk": svc("sandbells-kiosk"),
            "time_source": time_source,
            "time_locked": time_locked,
            "time_label": time_label,
            "status_tick": int(time.time()),
            "poll_hint_sec": poll_hint_sec,
            "cpu": cpu_pct,
            "load1": load1,
            "throttled": throttled,
            "random_bells": d["random_bells"],
            "random_windows": d["random_windows"],
            "pattern_mode": d["pattern_position_mode"],
            "settings_path": d.get("_settings_path", ""),
        }
    )
