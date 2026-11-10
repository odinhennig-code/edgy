"""Kleine Tests für die Edgy-Sprache. Laufen bei jedem Upload auf GitHub."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from edgy.sprache import Edgy, EdgyFehler  # noqa: E402


def lauf(code, antworten=()):
    aus = []
    it = iter(antworten)
    Edgy(ausgabe=aus.append, eingabe=lambda f: next(it)).starte(code)
    return aus


def fehler(code):
    try:
        lauf(code)
    except EdgyFehler as f:
        return f.text()
    raise AssertionError(f"Kein Fehler bei: {code!r}")


assert lauf('gib aus "Hallo"') == ["Hallo"]
assert lauf('merk x = 2\ngib aus x * 3 + 1') == ["7"]
assert lauf('gib aus 7 / 2') == ["3,5"]
assert lauf('frag n "?"\ngib aus "Hi " + n', ["Max"]) == ["Hi Max"]
assert lauf('frag a "?"\nwenn a > 12 dann\n gib aus "gross"\nsonst\n gib aus "klein"\nende', ["13"]) == ["gross"]
assert lauf('wiederhol 3 mal\n gib aus "x"\nende') == ["x", "x", "x"]
assert lauf('gib aus "a # b" # Kommentar') == ["a # b"]
assert lauf('wenn 1 ist nicht 2 und wahr dann\n gib aus "ok"\nende') == ["ok"]
assert "kenne ich nicht" in fehler("gib aus y")
assert "gibt es (noch) nicht" in fehler("tanz")
assert "ende" in fehler("wiederhol 2 mal\n gib aus 1")
assert "Durch 0" in fehler("gib aus 1 / 0")

print("Alle Edgy-Tests bestanden.")
