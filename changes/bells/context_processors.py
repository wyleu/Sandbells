import subprocess
from django.conf import settings

def git_hash(request):
    try:
        h = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=settings.BASE_DIR.parent,
            text=True,
        ).strip()
    except Exception:
        h = "dev"
    return {"git_hash": h}
