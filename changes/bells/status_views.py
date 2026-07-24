import platform
import socket
import subprocess

from django.conf import settings
from django.http import JsonResponse


def system_status(request):
    hostname = socket.gethostname()
    hostname_local = f"{hostname}.local"

    try:
        ips = subprocess.check_output(["hostname", "-I"], text=True).strip().split()
        ip = ips[0] if ips else "No Net"
        ip_list = "  ".join(ips) if ips else "No Net"
    except Exception:
        ip = "No Net"
        ip_list = "No Net"

    wifi_state = "unknown"
    wifi_ssid = ""
    wired_state = "unknown"
    try:
        for iface, label in [("wlan0", "wifi"), ("eth0", "wired")]:
            try:
                with open(f"/sys/class/net/{iface}/operstate") as f:
                    state = f.read().strip()
                if label == "wifi":
                    wifi_state = state
                else:
                    wired_state = state
            except FileNotFoundError:
                pass
        try:
            ssid = subprocess.check_output(["iwgetid", "-r"], text=True, timeout=2).strip()
            if ssid:
                wifi_ssid = ssid
        except Exception:
            pass
    except Exception:
        pass

    try:
        git_branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=settings.BASE_DIR.parent, text=True
        ).strip()
        git_hash = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=settings.BASE_DIR.parent, text=True
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

    temp_c = "—"
    try:
        out = subprocess.check_output(["vcgencmd", "measure_temp"], text=True)
        temp_c = out.strip().replace("temp=", "").replace("'C", "") + "°C"
    except Exception:
        pass

    fan_pct = "—"
    for path in ["/run/sandbells-fan.pct", "/tmp/sandbells-fan.pct"]:
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

    return JsonResponse({
        "hostname": hostname,
        "hostname_local": hostname_local,
        "ip": ip,
        "ip_list": ip_list,
        "wifi_state": wifi_state,
        "wifi_ssid": wifi_ssid,
        "wired_state": wired_state,
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
    })
