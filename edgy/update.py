"""Auto-Update: Edgy schaut beim Start auf GitHub nach einer neuen Version
und tauscht sich selbst aus – ohne Neuinstallieren."""

import json
import os
import subprocess
import sys
import tempfile
import urllib.request

from .version import GITHUB_REPO, VERSION


def _als_zahlen(version):
    teile = []
    for t in version.lstrip("vV").split("."):
        try:
            teile.append(int(t))
        except ValueError:
            teile.append(0)
    return tuple(teile)


def ist_exe():
    return getattr(sys, "frozen", False)


def suche_update():
    """Gibt (neue_version, download_url) zurück oder None."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    anfrage = urllib.request.Request(url, headers={"User-Agent": "Edgy"})
    with urllib.request.urlopen(anfrage, timeout=6) as antwort:
        daten = json.load(antwort)
    neu = daten.get("tag_name", "")
    if _als_zahlen(neu) <= _als_zahlen(VERSION):
        return None
    for datei in daten.get("assets", []):
        if datei.get("name", "").lower() == "edgy.exe":
            return neu, datei["browser_download_url"], datei.get("size") or 0
    return None


def installiere(download_url, groesse=0, fortschritt=None):
    """Lädt die neue Edgy.exe und tauscht sie nach dem Beenden aus.
    fortschritt(anteil) wird mit Werten von 0.0 bis 1.0 aufgerufen.
    Danach muss das Programm sich selbst beenden."""
    alte_exe = sys.executable
    ordner = os.path.dirname(alte_exe)
    neue_exe = os.path.join(ordner, "Edgy_neu.exe")

    anfrage = urllib.request.Request(download_url, headers={"User-Agent": "Edgy"})
    with urllib.request.urlopen(anfrage, timeout=60) as antwort, open(neue_exe, "wb") as f:
        gesamt = int(antwort.headers.get("Content-Length") or 0) or groesse or 12_000_000
        geladen = 0
        while True:
            block = antwort.read(65536)
            if not block:
                break
            f.write(block)
            geladen += len(block)
            if fortschritt:
                fortschritt(min(geladen / gesamt, 0.99))

    skript = os.path.join(tempfile.gettempdir(), "edgy_update.bat")
    with open(skript, "w", encoding="mbcs" if os.name == "nt" else "utf-8") as f:
        f.write(
            "@echo off\r\n"
            "set versuche=0\r\n"
            ":warte\r\n"
            "timeout /t 1 /nobreak >nul\r\n"
            f'move /y "{neue_exe}" "{alte_exe}" >nul 2>&1\r\n'
            "if errorlevel 1 (\r\n"
            "  set /a versuche+=1\r\n"
            "  if %versuche% lss 20 goto warte\r\n"
            ")\r\n"
            f'start "" "{alte_exe}"\r\n'
            'del "%~f0"\r\n'
        )
    # Das neue Edgy muss "frisch" starten und darf nichts vom alten erben,
    # sonst sucht es seine Dateien im (dann gelöschten) Temp-Ordner des alten.
    umgebung = {
        k: v for k, v in os.environ.items()
        if not k.upper().startswith(("_MEI", "_PYI"))
    }
    umgebung["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen(
        ["cmd", "/c", skript],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
        env=umgebung,
    )
