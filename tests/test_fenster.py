"""Fenster-Test auf echtem Windows (läuft auf GitHub): klickt, tippt, prüft, macht Screenshots."""

import json
import os
import sys
import tempfile
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import ImageGrab  # noqa: E402

ORDNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "screenshots")
os.makedirs(ORDNER, exist_ok=True)

# Eigener Test-Arbeitsordner + eigene Einstellungen
arbeit = tempfile.mkdtemp(prefix="edgy_test_")
os.makedirs(os.path.join(arbeit, "Projekt"))
with open(os.path.join(arbeit, "hallo.edgy"), "w", encoding="utf-8") as f:
    f.write('gib aus "Hallo aus der Datei"\nzähl i von 1 bis 2\n  gib aus i\nende\n')
with open(os.path.join(arbeit, "Projekt", "spiel.edgy"), "w", encoding="utf-8") as f:
    f.write('merk punkte = 0\n')
with open(os.path.join(arbeit, "Projekt", "notizen.txt"), "w", encoding="utf-8") as f:
    f.write("Nur Text\n")
einstellungen = os.path.join(arbeit, "_einstellungen.json")
with open(einstellungen, "w", encoding="utf-8") as f:
    json.dump({"arbeitsordner": arbeit}, f)
os.environ["EDGY_EINSTELLUNGEN"] = einstellungen

geoeffnet = []
webbrowser.open = lambda url, *a, **k: geoeffnet.append(url)

from edgy import fenster  # noqa: E402

nr = [0]


def pumpe(f, sekunden=0.4):
    ende = time.time() + sekunden
    while time.time() < ende:
        f.root.update()
        time.sleep(0.008)


def warte_auf(f, bedingung, sekunden=8):
    ende = time.time() + sekunden
    while time.time() < ende:
        f.root.update()
        if bedingung():
            return True
        time.sleep(0.02)
    return False


def foto(f, name):
    f.root.update()
    r = f.root
    x, y, w, h = r.winfo_rootx(), r.winfo_rooty(), r.winfo_width(), r.winfo_height()
    nr[0] += 1
    ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(
        os.path.join(ORDNER, f"{nr[0]:02d}_{name}.png"))


# =============================================================== 1) Umbau-Film
f = fenster.EdgyFenster(umbau=True)
start = time.time()
U, S = fenster.EdgyFenster.FILM_UMBAU / 1000, fenster.EdgyFenster.FILM_SPRUCH / 1000
for zeit, name in [(0.75, "film_kachel"), (2.3, "film_intro"), (3.0, "film_wisch"), (4.9, "film_altes_edgy"),
                   (7.2, "film_frage"), (12.6, "film_antwort"), (16.2, "film_umbauen_knopf"),
                   (U + 0.6, "film_fenster_waechst"), (U + 1.6, "film_icons_explorer"),
                   (U + 2.5, "film_konsole_rutscht"), (U + 3.8, "film_editor"),
                   (S + 1.0, "film_spruch_halb"), (S + 2.6, "film_spruch"), (S + 3.6, "film_wisch_weg"),
                   (fenster.EdgyFenster.FILM_ENDE / 1000 + 0.8, "film_fertig")]:
    while time.time() - start < zeit:
        f.root.update()
        time.sleep(0.004)
    foto(f, name)
with open(einstellungen, encoding="utf-8") as fh:
    assert json.load(fh).get(fenster.UMBAU_SCHLUESSEL) is True, "Umbau-Film wurde nicht gemerkt"
assert f.baum.exists(os.path.join(arbeit, "hallo.edgy"))
assert f.aktivitaet.winfo_width() > 10 and f.seitenleiste.winfo_width() > 100
f.root.destroy()

# =============================================================== 1b) Überspringen
with open(einstellungen, "w", encoding="utf-8") as fh:
    json.dump({"arbeitsordner": arbeit}, fh)
f = fenster.EdgyFenster()  # Film nicht gesehen -> startet
pumpe(f, 6.0)
f._umbau_ueberspringen()
pumpe(f, 1.0)
assert f._umbau_erledigt and f.seitenleiste.winfo_width() > 100 and f.statusleiste.winfo_height() > 10
assert not f.chat.winfo_exists()
foto(f, "uebersprungen")
with open(einstellungen, encoding="utf-8") as fh:
    assert json.load(fh).get(fenster.UMBAU_SCHLUESSEL) is True
f.root.destroy()

# =============================================================== 2) Normaler Start (ohne Animation)
f = fenster.EdgyFenster()
pumpe(f, 0.6)
assert f.aktivitaet.winfo_width() > 10, "Aktivitätsleiste fehlt"
assert f.baum.exists(os.path.join(arbeit, "Projekt"))
assert f.baum.exists(os.path.join(arbeit, "Projekt", "spiel.edgy"))
foto(f, "normal_start")

# Datei öffnen -> Tab
hallo = os.path.join(arbeit, "hallo.edgy")
tab = f.datei_oeffnen(hallo)
pumpe(f)
assert f.aktiv is tab and len(f.tabs) == 1
assert "Hallo aus der Datei" in tab.text.get("1.0", "end")

# Zweite Datei, Ordner aufgeklappt
spiel = os.path.join(arbeit, "Projekt", "spiel.edgy")
tab2 = f.datei_oeffnen(spiel)
pumpe(f)
assert len(f.tabs) == 2 and f.baum.item(os.path.join(arbeit, "Projekt"), "open")

# Im Editor tippen: Vorschlag + Einrücken
t = tab2.text
t.mark_set("insert", "end-1c")
t.insert("insert", "wi")
tab2.geist.zeige()
pumpe(f, 0.2)
assert tab2.geist.text == "ederhol ", tab2.geist.text
foto(f, "editor_vorschlag")
tab2.geist.annehmen()
tab2.geist.weg()
t.insert("insert", "3 mal")
f._editor_enter(tab2)
assert t.get("insert linestart", "insert") == "  ", repr(t.get("insert linestart", "insert"))
t.insert("insert", "merk punkte = punkte + zufall(1, 6)")
f._editor_enter(tab2)
t.insert("insert", "ende")
f._editor_enter(tab2)
t.insert("insert", 'gib aus "Punkte: " + punkte')
f._editor_geaendert(tab2)
pumpe(f)
assert tab2.geaendert
foto(f, "editor_geaendert")

# Speichern (Datei hat schon einen Pfad -> kein Dialog)
assert f.speichern(tab2)
with open(spiel, encoding="utf-8") as fh:
    gespeichert = fh.read()
assert "wiederhol 3 mal\n  merk punkte" in gespeichert and "\nende\n" in gespeichert, gespeichert
assert not tab2.geaendert

# Starten
f.starten()
assert warte_auf(f, lambda: "Punkte: " in f.anzeige.get("1.0", "end") and not f.laeuft), f.anzeige.get("1.0", "end")
foto(f, "gestartet")

# Neue Datei + neuer Ordner + Umbenennen + Löschen über den Explorer
neu = f.datei_anlegen(arbeit, "neu.edgy", 'gib aus "neu"\n')
assert os.path.isfile(neu) and f.baum.exists(neu)
ordner = f.ordner_anlegen(arbeit, "Webseiten-Test")
assert os.path.isdir(ordner) and f.baum.exists(ordner)
umbenannt = f.umbenennen(neu, "umbenannt.edgy")
assert umbenannt and os.path.isfile(umbenannt) and not os.path.exists(neu)
assert f.baum.exists(umbenannt)
assert f.loeschen(umbenannt, nachfragen=False)
assert not os.path.exists(umbenannt) and not f.baum.exists(umbenannt)

# Webseite aus einer Datei -> HTML daneben
seite_edgy = f.datei_anlegen(ordner, "seite.edgy", fenster.BEISPIEL_SEITE)
f.datei_oeffnen(seite_edgy)
f.starten()
assert warte_auf(f, lambda: geoeffnet and not f.laeuft), f.anzeige.get("1.0", "end")
assert os.path.isfile(os.path.join(ordner, "seite.html"))
pumpe(f, 0.3)
assert f.baum.exists(os.path.join(ordner, "seite.html"))
foto(f, "webseite")

# Konsole: Vorschlag mit Tab
f.feld.focus_force()
f.feld.insert("end", "g")
f.geist_konsole.zeige()
pumpe(f, 0.2)
assert f.feld.get("1.0", "end-1c") == "gib aus "
foto(f, "konsole_vorschlag")
f.geist_konsole.weg()
f._feld_setzen("")

# Tab schließen
anzahl = len(f.tabs)
f.tab_schliessen(f.tabs[0])
assert len(f.tabs) == anzahl - 1

# Explorer & Konsole ein-/ausblenden
f.seitenleiste_umschalten()
f.panel_umschalten()
pumpe(f, 0.6)
assert not f.seitenleiste.winfo_ismapped() and not f.panel.winfo_ismapped()
foto(f, "nur_editor")
f.seitenleiste_umschalten()
f.panel_umschalten()
pumpe(f, 0.6)
assert f.seitenleiste.winfo_ismapped() and f.panel.winfo_ismapped()

# Alle Tabs zu -> Willkommen
for tb in list(f.tabs):
    tb.text.edit_modified(False)
    f.tab_schliessen(tb)
pumpe(f, 0.3)
assert f.willkommen.winfo_ismapped()
foto(f, "willkommen")

# Update-Bildschirm
f._nur_test = True
f.update_bildschirm("v9.9.9")
f.update_fortschritt(0.6)
pumpe(f, 1.0)
foto(f, "update_laedt")
f.update_fertig()
assert warte_auf(f, lambda: "neu gestartet" in f._u_titel.cget("text"))
f.update_weg()

f.root.destroy()
print("Fenster-Test bestanden.")
