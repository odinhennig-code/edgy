"""Fenster-Test auf echtem Windows (läuft auf GitHub): tippt, prüft, macht Screenshots."""

import os
import sys
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import ImageGrab  # noqa: E402

from edgy import fenster  # noqa: E402

ORDNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "screenshots")
os.makedirs(ORDNER, exist_ok=True)
geoeffnet = []
webbrowser.open = lambda url, *a, **k: geoeffnet.append(url)

f = fenster.EdgyFenster()
r = f.root
r.geometry("1000x640+30+30")


def pumpe(sekunden=0.4):
    ende = time.time() + sekunden
    while time.time() < ende:
        r.update()
        time.sleep(0.01)


def warte_auf(bedingung, sekunden=8):
    ende = time.time() + sekunden
    while time.time() < ende:
        r.update()
        if bedingung():
            return True
        time.sleep(0.02)
    return False


def foto(name):
    pumpe(0.3)
    x, y = r.winfo_rootx(), r.winfo_rooty()
    w, h = r.winfo_width(), r.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(os.path.join(ORDNER, name + ".png"))


def konsole():
    return f.anzeige.get("1.0", "end-1c")


def feld():
    return f.feld.get("1.0", "end-1c")


pumpe(0.8)
foto("1_start")

# --- Vorschlag: "g" -> grau "ib aus ", Tab übernimmt
f.feld.focus_force()
f.feld.insert("end", "g")
f.geist_konsole.zeige()
pumpe()
assert feld() == "gib aus ", repr(feld())
assert f.geist_konsole.text == "ib aus "
assert f.tab_hinweis.winfo_ismapped()
foto("2_vorschlag")
assert f.geist_konsole.annehmen()
f.geist_konsole.weg()
assert feld() == "gib aus ", repr(feld())
f.feld.insert("end", '"Hallo Edgy"')
fenster.faerbe(f.feld)
pumpe()
foto("3_eingabe")
f._enter()
assert warte_auf(lambda: "Hallo Edgy\n" in konsole() and not f.laeuft), konsole()

# --- frag mit Antwort
f._verarbeite_zeile('frag name "Wie heißt du?"')
assert warte_auf(lambda: f.wartet_auf_antwort)
f._verarbeite_zeile("Max")
assert warte_auf(lambda: not f.laeuft)
f._verarbeite_zeile('gib aus "Hi " + name')
assert warte_auf(lambda: "Hi Max" in konsole())

# --- mehrzeilig in der Konsole
for z in ["zähl i von 1 bis 3", "  gib aus i * 10", "ende"]:
    f._verarbeite_zeile(z)
assert warte_auf(lambda: "30\n" in konsole() and not f.laeuft), konsole()

# --- Farbe
f._starte('farbe "gold"\ngib aus "Goldene Zeile"\nfarbe "normal"\ngib aus zufall(1, 6)')
assert warte_auf(lambda: "Goldene Zeile" in konsole() and not f.laeuft)

# --- Fehler werden rot angezeigt
f._verarbeite_zeile("tanz")
assert warte_auf(lambda: "gibt es (noch) nicht" in konsole())
foto("4_konsole")

# --- hilfe
f._verarbeite_zeile("hilfe")
pumpe()
assert "WEBSEITEN" in konsole()
f._leeren()

# --- Editor mit automatischem Einrücken
f.zeige_ansicht("editor")
f._editor_setzen("")
f.editor.insert("end", "wenn 1 dann")
f._editor_enter()
assert f.editor.get("2.0", "2.end") == "  ", repr(f.editor.get("2.0", "2.end"))
f.editor.insert("end", 'gib aus "drin"')
f._editor_enter()
f.editor.insert("end", "ende")
f._editor_enter()
zeilen = f.editor.get("1.0", "end-1c").split("\n")
assert zeilen[2] == "ende", zeilen
assert zeilen[3] == "", zeilen

# Vorschlag im Editor
f.editor.insert("end", "wi")
f.geist_editor.zeige()
pumpe()
assert f.geist_editor.text == "ederhol "
f.geist_editor.annehmen()
f.geist_editor.weg()

f._editor_setzen(fenster.BEISPIEL)
f.editor.mark_set("insert", "end")
pumpe()
foto("5_editor")

# --- Webseite
f._editor_setzen(fenster.BEISPIEL_SEITE)
f.starte_editor()
assert warte_auf(lambda: geoeffnet and not f.laeuft), konsole()
pfad = geoeffnet[0]
assert pfad.startswith("file:") and pfad.endswith(".html"), pfad
assert "Seite geöffnet" in konsole()
foto("6_webseite")

# --- Update-Bildschirm
f._nur_test = True
f.update_bildschirm("v9.9.9")
f.update_fortschritt(0.6)
pumpe(1.0)
foto("7_update_laedt")
f.update_fertig()
assert warte_auf(lambda: "neu gestartet" in f._u_titel.cget("text"))
pumpe(0.3)
foto("8_update_neustart")
f.update_weg()

f.editor.edit_modified(False)
r.destroy()
print("Fenster-Test bestanden.")
