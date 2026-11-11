"""Tests für die Edgy-Sprache. Laufen bei jedem Upload auf GitHub."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from edgy.sprache import Edgy, EdgyFehler, vorschlag  # noqa: E402


def lauf(code, antworten=(), mit_farbe=False):
    aus = []
    it = iter(antworten)
    seiten = []

    def ausgabe(text, farbe=None):
        aus.append((text, farbe) if mit_farbe else text)

    Edgy(ausgabe=ausgabe, eingabe=lambda f: next(it),
         zeige_seite=lambda h, t: seiten.append((t, h))).starte(code)
    lauf.seiten = seiten
    return aus


def fehler(code):
    try:
        lauf(code)
    except EdgyFehler as f:
        return f.text()
    raise AssertionError(f"Kein Fehler bei: {code!r}")


# Grundbefehle
assert lauf('gib aus "Hallo"') == ["Hallo"]
assert lauf('merk x = 2\ngib aus x * 3 + 1') == ["7"]
assert lauf('gib aus 7 / 2') == ["3,5"]
assert lauf('gib aus 1.5 + 1') == ["2,5"]
assert lauf('frag n "?"\ngib aus "Hi " + n', ["Max"]) == ["Hi Max"]
assert lauf('frag a "?"\ngib aus a * 2', ["2,5"]) == ["5"]
assert lauf('frag a "?"\nwenn a > 12 dann\n gib aus "gross"\nsonst\n gib aus "klein"\nende', ["13"]) == ["gross"]
assert lauf('wiederhol 3 mal\n gib aus "x"\nende') == ["x", "x", "x"]
assert lauf('gib aus "a # b" # Kommentar') == ["a # b"]
assert lauf('wenn 1 ist nicht 2 und wahr dann\n gib aus "ok"\nende') == ["ok"]
assert lauf('gib aus "ha" * 3') == ["hahaha"]

# Neue Schleifen
assert lauf('zähl i von 1 bis 3\n gib aus i\nende') == ["1", "2", "3"]
assert lauf('zaehl i von 3 bis 1\n gib aus i\nende') == ["3", "2", "1"]
assert lauf('merk n = 0\nsolange n < 3\n merk n = n + 1\n gib aus n\nende') == ["1", "2", "3"]
assert lauf('zähl i von 1 bis 10\n wenn i == 3 dann\n  abbrechen\n ende\n gib aus i\nende') == ["1", "2"]
assert lauf('solange wahr\n abbrechen\nende\ngib aus "raus"') == ["raus"]
assert lauf('warte 0\ngib aus "ok"') == ["ok"]

# Funktionen
r = int(lauf('gib aus zufall(1, 6)')[0])
assert 1 <= r <= 6
assert lauf('gib aus länge("Edgy")') == ["4"]
assert lauf('gib aus groß("edgy") + klein("EDGY")') == ["EDGYedgy"]
assert lauf('gib aus runde(3.7)') == ["4"]
assert lauf('gib aus wurzel(16)') == ["4"]
assert lauf('gib aus zahl("5") + 1') == ["6"]
assert len(lauf('gib aus uhrzeit()')[0]) == 5

# Farbe
assert lauf('farbe "rot"\ngib aus "x"\nfarbe "normal"\ngib aus "y"', mit_farbe=True) == [("x", "#ff3b3b"), ("y", None)]

# Webseiten
lauf('seite "Test"\nhintergrund "schwarz"\ntextfarbe "weiß"\nüberschrift "Hallo <Welt>"\n'
     'absatz "Text"\nknopf "Los" zu "https://example.com"\nlink "Mehr" zu "https://example.com"\n'
     'bild "https://example.com/a.png"\ntrennlinie')
titel, h = lauf.seiten[0]
assert titel == "Test"
assert "<h1>Hallo &lt;Welt&gt;</h1>" in h and 'class="knopf" href="https://example.com"' in h
assert "--bg: #111111" in h and "<hr>" in h

# Fehler
assert "kenne ich nicht" in fehler("gib aus y")
assert "gibt es (noch) nicht" in fehler("tanz")
assert "ende" in fehler("wiederhol 2 mal\n gib aus 1")
assert "Durch 0" in fehler("gib aus 1 / 0")
assert "nur in einer Schleife" in fehler("abbrechen")
assert "Farbe" in fehler('farbe "regenbogen"')
assert "eingebaute Funktion" in fehler('merk zufall = 3')
assert "noch leer" in fehler('zeig seite')

# Vorschläge (Tab)
assert vorschlag("g") == "ib aus "
assert vorschlag("gib a") == "us "
assert vorschlag("w") == "enn "
assert vorschlag("wi") == "ederhol "
assert vorschlag("wenn x > 3 ") == "dann"
assert vorschlag("wiederhol 3 ") == "mal"
assert vorschlag("zähl i ") == "von "
assert vorschlag("zähl i von 1 ") == "bis "
assert vorschlag("gib aus pu", variablen=["punkte"]) == "nkte"
assert vorschlag("gib aus zu") == "fall("
assert vorschlag('gib aus "g') == ""
assert vorschlag('farbe "r') == 'ot"'
assert vorschlag("  gib aus 1") == ""
assert vorschlag("h", extra_befehle=["hilfe"]) == "ilfe"

print("Alle Edgy-Tests bestanden.")
