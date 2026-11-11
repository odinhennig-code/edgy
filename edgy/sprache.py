"""Edgy – das Herzstück: liest Edgy-Code und führt ihn aus."""

import html
import math
import random
import re
import time
from datetime import datetime


class EdgyFehler(Exception):
    """Ein Fehler in Edgy-Code, mit verständlicher Meldung."""

    def __init__(self, nachricht, zeile=None):
        self.nachricht = nachricht
        self.zeile = zeile
        super().__init__(self.text())

    def text(self):
        if self.zeile is not None:
            return f"Zeile {self.zeile}: {self.nachricht}"
        return self.nachricht


class Abbruch(Exception):
    """Wird geworfen, wenn das Programm von außen gestoppt wird."""


class _SchleifeVerlassen(Exception):
    """Intern: 'abbrechen' springt aus der Schleife."""


SCHLUESSELWOERTER = {
    "gib", "aus", "merk", "frag", "wenn", "dann", "sonst", "ende",
    "wiederhol", "mal", "und", "oder", "nicht", "wahr", "falsch", "ist",
    "solange", "zähl", "zaehl", "von", "bis", "warte", "abbrechen",
    "farbe", "leere", "seite", "überschrift", "ueberschrift", "absatz",
    "knopf", "bild", "link", "zu", "trennlinie", "hintergrund",
    "textfarbe", "zeig",
}

# Befehle, die einen Block öffnen (brauchen ein 'ende')
BLOCK_START = ("wenn", "wiederhol", "solange", "zähl", "zaehl")

FARBEN = {
    "schwarz": "#111111", "weiß": "#ffffff", "weiss": "#ffffff", "rot": "#ff3b3b",
    "gold": "#ffce00", "gelb": "#ffe14d", "blau": "#4d8dff", "grün": "#3ddc84",
    "gruen": "#3ddc84", "grau": "#8a8a8f", "lila": "#a66cff", "orange": "#ff8a3d",
    "pink": "#ff5fa2", "türkis": "#2ee6d6", "tuerkis": "#2ee6d6", "braun": "#a0663a",
    "normal": None,
}


def farbe_zu_hex(name, zeile=None):
    if isinstance(name, str):
        n = name.strip().lower()
        if n in FARBEN:
            return FARBEN[n]
        if re.fullmatch(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?", n):
            return n
    erlaubt = ", ".join(k for k in FARBEN if k not in ("weiss", "gruen", "tuerkis"))
    raise EdgyFehler(f"Die Farbe '{als_text(name)}' kenne ich nicht. Möglich: {erlaubt} oder #hex.", zeile)


# ---------------------------------------------------------------------------
# Eingebaute Funktionen, z. B.  zufall(1, 6)
# ---------------------------------------------------------------------------

def _f_zufall(zeile, a=1, b=None):
    if b is None:
        a, b = 1, a
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (a, b)):
        raise EdgyFehler("zufall braucht ganze Zahlen, z. B. zufall(1, 6).", zeile)
    if a > b:
        a, b = b, a
    return random.randint(a, b)


def _f_runde(zeile, x, stellen=0):
    _zahl_pruefen(x, "runde", zeile)
    ergebnis = round(x, int(stellen))
    return int(ergebnis) if stellen == 0 else ergebnis


def _f_wurzel(zeile, x):
    _zahl_pruefen(x, "wurzel", zeile)
    if x < 0:
        raise EdgyFehler("Aus einer Minus-Zahl kann man keine Wurzel ziehen.", zeile)
    w = math.sqrt(x)
    return int(w) if w == int(w) else w


def _f_zahl(zeile, x):
    w = zu_wert(als_text(x))
    if isinstance(w, str):
        raise EdgyFehler(f"'{x}' ist keine Zahl.", zeile)
    return w


def _zahl_pruefen(x, name, zeile):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise EdgyFehler(f"{name} braucht eine Zahl.", zeile)


FUNKTIONEN = {
    "zufall": (_f_zufall, 1, 2),
    "länge": (lambda z, x: len(als_text(x)), 1, 1),
    "laenge": (lambda z, x: len(als_text(x)), 1, 1),
    "groß": (lambda z, x: als_text(x).upper(), 1, 1),
    "gross": (lambda z, x: als_text(x).upper(), 1, 1),
    "klein": (lambda z, x: als_text(x).lower(), 1, 1),
    "runde": (_f_runde, 1, 2),
    "wurzel": (_f_wurzel, 1, 1),
    "zahl": (_f_zahl, 1, 1),
    "text": (lambda z, x: als_text(x), 1, 1),
    "uhrzeit": (lambda z: datetime.now().strftime("%H:%M"), 0, 0),
    "datum": (lambda z: datetime.now().strftime("%d.%m.%Y"), 0, 0),
}

# ---------------------------------------------------------------------------
# Ausdrücke: Zerlegen (Tokens) und Ausrechnen
# ---------------------------------------------------------------------------

_TOKEN = re.compile(
    r"""\s*(?:
        (?P<zahl>\d+(?:\.\d+)?)
      | (?P<text>"[^"]*")
      | (?P<op>==|!=|<=|>=|[+\-*/%()<>=,])
      | (?P<wort>[A-Za-zÄÖÜäöüß_][A-Za-zÄÖÜäöüß_0-9]*)
    )""",
    re.VERBOSE,
)


def zerlege(code, zeile):
    tokens = []
    pos = 0
    code = code.rstrip()
    while pos < len(code):
        m = _TOKEN.match(code, pos)
        if not m or m.end() == pos:
            rest = code[pos:].strip()
            if rest.startswith('"'):
                raise EdgyFehler("Da fehlt ein schließendes Anführungszeichen \".", zeile)
            raise EdgyFehler(f"Mit '{rest[:1]}' kann ich nichts anfangen.", zeile)
        pos = m.end()
        art = m.lastgroup
        wert = m.group(art)
        if art == "zahl":
            wert = float(wert) if "." in wert else int(wert)
        elif art == "text":
            wert = wert[1:-1]
        tokens.append((art, wert))
    return tokens


class Ausdruck:
    """Rechnet einen Ausdruck aus, z. B.  alter + 1  oder  name == "Max"."""

    def __init__(self, tokens, zeile):
        self.t = tokens
        self.i = 0
        self.zeile = zeile

    def _sieh(self, weiter=0):
        j = self.i + weiter
        return self.t[j] if j < len(self.t) else (None, None)

    def _ist(self, *werte):
        art, wert = self._sieh()
        return art in ("op", "wort") and wert in werte

    def _nimm(self):
        tok = self._sieh()
        self.i += 1
        return tok

    def berechne(self, variablen):
        self.v = variablen
        self.i = 0
        if not self.t:
            raise EdgyFehler("Hier fehlt ein Wert.", self.zeile)
        ergebnis = self._oder()
        if self.i < len(self.t):
            raise EdgyFehler(f"Unerwartet: '{self.t[self.i][1]}'.", self.zeile)
        return ergebnis

    def _oder(self):
        links = self._und()
        while self._ist("oder"):
            self._nimm()
            rechts = self._und()
            links = wahrheit(links) or wahrheit(rechts)
        return links

    def _und(self):
        links = self._nicht()
        while self._ist("und"):
            self._nimm()
            rechts = self._nicht()
            links = wahrheit(links) and wahrheit(rechts)
        return links

    def _nicht(self):
        if self._ist("nicht"):
            self._nimm()
            return not wahrheit(self._nicht())
        return self._vergleich()

    def _vergleich(self):
        links = self._summe()
        if self._ist("==", "=", "ist", "!=", "<", ">", "<=", ">="):
            _, op = self._nimm()
            if op == "ist" and self._ist("nicht"):
                self._nimm()
                op = "!="
            rechts = self._summe()
            try:
                if op in ("==", "=", "ist"):
                    return links == rechts
                if op == "!=":
                    return links != rechts
                if op == "<":
                    return links < rechts
                if op == ">":
                    return links > rechts
                if op == "<=":
                    return links <= rechts
                if op == ">=":
                    return links >= rechts
            except TypeError:
                raise EdgyFehler("Text und Zahl kann ich nicht mit < oder > vergleichen.", self.zeile)
        return links

    def _summe(self):
        links = self._produkt()
        while self._ist("+", "-"):
            _, op = self._nimm()
            rechts = self._produkt()
            if op == "+":
                if isinstance(links, str) or isinstance(rechts, str):
                    links = als_text(links) + als_text(rechts)
                else:
                    links = links + rechts
            else:
                links = self._zahl(links) - self._zahl(rechts)
        return links

    def _produkt(self):
        links = self._einzeln()
        while self._ist("*", "/", "%"):
            _, op = self._nimm()
            rechts = self._einzeln()
            if op == "*" and isinstance(links, str) and isinstance(rechts, int) and not isinstance(rechts, bool):
                links = links * max(rechts, 0)  # "ha" * 3 = "hahaha"
                continue
            a, b = self._zahl(links), self._zahl(rechts)
            if op == "*":
                links = a * b
            elif b == 0:
                raise EdgyFehler("Durch 0 teilen geht nicht.", self.zeile)
            elif op == "/":
                links = a / b
                if links == int(links):
                    links = int(links)
            else:
                links = a % b
        return links

    def _einzeln(self):
        art, wert = self._nimm()
        if art is None:
            raise EdgyFehler("Der Ausdruck hört zu früh auf.", self.zeile)
        if art in ("zahl", "text"):
            return wert
        if art == "op" and wert == "-":
            return -self._zahl(self._einzeln())
        if art == "op" and wert == "(":
            ergebnis = self._oder()
            if not self._ist(")"):
                raise EdgyFehler("Da fehlt eine schließende Klammer ).", self.zeile)
            self._nimm()
            return ergebnis
        if art == "wort":
            if wert == "wahr":
                return True
            if wert == "falsch":
                return False
            if self._sieh() == ("op", "("):
                return self._funktion(wert)
            if wert in self.v:
                return self.v[wert]
            if wert in FUNKTIONEN:
                raise EdgyFehler(f"{wert} ist eine Funktion – schreib {wert}(...).", self.zeile)
            raise EdgyFehler(f"'{wert}' kenne ich nicht. Hast du es vorher mit merk gespeichert?", self.zeile)
        raise EdgyFehler(f"Unerwartet: '{wert}'.", self.zeile)

    def _funktion(self, name):
        if name not in FUNKTIONEN:
            raise EdgyFehler(f"Die Funktion '{name}' gibt es (noch) nicht.", self.zeile)
        self._nimm()  # (
        argumente = []
        if not self._ist(")"):
            argumente.append(self._oder())
            while self._ist(","):
                self._nimm()
                argumente.append(self._oder())
        if not self._ist(")"):
            raise EdgyFehler("Da fehlt eine schließende Klammer ).", self.zeile)
        self._nimm()
        funktion, minimum, maximum = FUNKTIONEN[name]
        if not minimum <= len(argumente) <= maximum:
            if minimum == maximum:
                raise EdgyFehler(f"{name} braucht genau {minimum} Wert(e).", self.zeile)
            raise EdgyFehler(f"{name} braucht {minimum} bis {maximum} Werte.", self.zeile)
        return funktion(self.zeile, *argumente)

    def _zahl(self, wert):
        if isinstance(wert, bool) or not isinstance(wert, (int, float)):
            raise EdgyFehler(f"Mit '{als_text(wert)}' kann ich nicht rechnen, das ist keine Zahl.", self.zeile)
        return wert


def wahrheit(wert):
    if isinstance(wert, str):
        return wert != ""
    return bool(wert)


def als_text(wert):
    if wert is True:
        return "wahr"
    if wert is False:
        return "falsch"
    if isinstance(wert, float):
        return f"{wert:.10g}".replace(".", ",")
    return str(wert)


def zu_wert(eingabe):
    """Macht aus einer Eingabe eine Zahl, wenn es eine ist."""
    e = eingabe.strip()
    if re.fullmatch(r"-?\d+", e):
        return int(e)
    if re.fullmatch(r"-?\d+[.,]\d+", e):
        return float(e.replace(",", "."))
    return eingabe


# ---------------------------------------------------------------------------
# Webseiten
# ---------------------------------------------------------------------------

class Webseite:
    def __init__(self, titel="Meine Seite"):
        self.titel = titel
        self.teile = []
        self.hintergrund = "#ffffff"
        self.textfarbe = "#111111"

    def html(self):
        e = html.escape
        inhalt = "\n".join(self.teile)
        return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="Edgy">
<title>{e(self.titel)}</title>
<style>
  :root {{ --bg: {self.hintergrund}; --fg: {self.textfarbe}; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--fg);
         font-family: "Segoe UI", system-ui, -apple-system, sans-serif; line-height: 1.6; }}
  main {{ max-width: 760px; margin: 0 auto; padding: 72px 24px; }}
  h1 {{ font-size: 2.6rem; line-height: 1.15; margin: 0 0 24px; letter-spacing: -0.02em; }}
  p {{ font-size: 1.1rem; margin: 0 0 18px; opacity: .85; }}
  a {{ color: inherit; }}
  .knopf {{ display: inline-block; margin: 8px 8px 18px 0; padding: 12px 22px; border-radius: 10px;
           background: var(--fg); color: var(--bg); text-decoration: none; font-weight: 600; border: 0;
           font: inherit; font-weight: 600; cursor: pointer; }}
  .knopf:hover {{ opacity: .85; }}
  img {{ max-width: 100%; border-radius: 12px; margin: 8px 0 18px; display: block; }}
  hr {{ border: 0; border-top: 1px solid currentColor; opacity: .15; margin: 32px 0; }}
  .streifen {{ position: fixed; top: 0; left: 0; right: 0; height: 4px;
              background: linear-gradient(90deg, #111 33.3%, #dd0000 33.3% 66.6%, #ffce00 66.6%); }}
  footer {{ margin-top: 56px; font-size: .8rem; opacity: .45; }}
</style>
</head>
<body>
<div class="streifen"></div>
<main>
{inhalt}
<footer>Gemacht mit Edgy</footer>
</main>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Befehle: Code in Bausteine zerlegen
# ---------------------------------------------------------------------------

_NAME = re.compile(r"^[A-Za-zÄÖÜäöüß_][A-Za-zÄÖÜäöüß_0-9]*$")


def _pruefe_name(name, zeile):
    if not _NAME.match(name):
        raise EdgyFehler(f"'{name}' ist kein gültiger Name.", zeile)
    if name in SCHLUESSELWOERTER:
        raise EdgyFehler(f"'{name}' ist ein Edgy-Befehl und kann kein Name sein.", zeile)
    if name in FUNKTIONEN:
        raise EdgyFehler(f"'{name}' ist eine eingebaute Funktion und kann kein Name sein.", zeile)


def _ohne_kommentar(text):
    """Entfernt # Kommentare, aber nicht innerhalb von Text."""
    in_text = False
    for i, z in enumerate(text):
        if z == '"':
            in_text = not in_text
        elif z == "#" and not in_text:
            return text[:i]
    return text


def zerlege_programm(code):
    zeilen = []
    for nr, roh in enumerate(code.splitlines(), start=1):
        text = _ohne_kommentar(roh).strip()
        if text:
            zeilen.append((nr, text))
    bausteine, pos, ende = _block(zeilen, 0)
    if ende is not None:
        raise EdgyFehler(f"'{ende}' ohne passendes wenn, wiederhol, solange oder zähl.", zeilen[pos - 1][0])
    return bausteine


def _ausdruck(text, zeile):
    return Ausdruck(zerlege(text, zeile), zeile)


def _teile_bei(text, wort, zeile):
    """Teilt einen Ausdruck beim Wort (z. B. 'zu'), außerhalb von Text und Klammern."""
    tokens = zerlege(text, zeile)
    tiefe = 0
    for i, (art, wert) in enumerate(tokens):
        if art == "op" and wert == "(":
            tiefe += 1
        elif art == "op" and wert == ")":
            tiefe -= 1
        elif art == "wort" and wert == wort and tiefe == 0:
            return Ausdruck(tokens[:i], zeile), Ausdruck(tokens[i + 1:], zeile)
    return Ausdruck(tokens, zeile), None


def _rest(text, befehl):
    return text[len(befehl):].strip()


def _block(zeilen, pos):
    bausteine = []
    while pos < len(zeilen):
        nr, text = zeilen[pos]
        erstes = text.split()[0]
        if erstes in ("sonst", "ende"):
            if text != erstes:
                raise EdgyFehler(f"Hinter '{erstes}' darf nichts mehr stehen.", nr)
            return bausteine, pos + 1, erstes
        pos += 1

        if text.startswith("gib aus"):
            rest = _rest(text, "gib aus")
            bausteine.append(("gib", nr, _ausdruck(rest, nr) if rest else None))

        elif erstes == "gib":
            raise EdgyFehler("Meintest du 'gib aus'?", nr)

        elif erstes == "merk":
            rest = _rest(text, "merk")
            if "=" not in rest:
                raise EdgyFehler("So geht merk:  merk name = \"Max\"", nr)
            name, wert = rest.split("=", 1)
            name = name.strip()
            _pruefe_name(name, nr)
            bausteine.append(("merk", nr, name, _ausdruck(wert.strip(), nr)))

        elif erstes == "frag":
            teile = _rest(text, "frag").split(None, 1)
            if not teile:
                raise EdgyFehler("So geht frag:  frag name \"Wie heißt du?\"", nr)
            _pruefe_name(teile[0], nr)
            frage = _ausdruck(teile[1], nr) if len(teile) > 1 else None
            bausteine.append(("frag", nr, teile[0], frage))

        elif erstes == "wenn":
            if not text.endswith(" dann"):
                raise EdgyFehler("Hinter wenn ... gehört am Ende ein 'dann'.", nr)
            bedingung = _ausdruck(text[4:-5].strip(), nr)
            ja, pos, ende = _block(zeilen, pos)
            nein = []
            if ende == "sonst":
                nein, pos, ende = _block(zeilen, pos)
                if ende == "sonst":
                    raise EdgyFehler("Ein wenn darf nur ein sonst haben.", nr)
            if ende != "ende":
                raise EdgyFehler("Dieses wenn wird nie mit 'ende' abgeschlossen.", nr)
            bausteine.append(("wenn", nr, bedingung, ja, nein))

        elif erstes == "wiederhol":
            if not text.endswith(" mal"):
                raise EdgyFehler("So geht wiederhol:  wiederhol 3 mal", nr)
            anzahl = _ausdruck(text[9:-4].strip(), nr)
            inhalt, pos = _schleifen_inhalt(zeilen, pos, "wiederhol", nr)
            bausteine.append(("wiederhol", nr, anzahl, inhalt))

        elif erstes == "solange":
            rest = _rest(text, "solange")
            if rest.endswith(" dann"):
                rest = rest[:-5]
            if not rest:
                raise EdgyFehler("So geht solange:  solange zahl < 10", nr)
            inhalt, pos = _schleifen_inhalt(zeilen, pos, "solange", nr)
            bausteine.append(("solange", nr, _ausdruck(rest, nr), inhalt))

        elif erstes in ("zähl", "zaehl"):
            m = re.fullmatch(r"\S+\s+(\S+)\s+von\s+(.+?)\s+bis\s+(.+)", text)
            if not m:
                raise EdgyFehler("So geht zähl:  zähl i von 1 bis 10", nr)
            _pruefe_name(m.group(1), nr)
            inhalt, pos = _schleifen_inhalt(zeilen, pos, "zähl", nr)
            bausteine.append(("zähl", nr, m.group(1), _ausdruck(m.group(2), nr),
                              _ausdruck(m.group(3), nr), inhalt))

        elif erstes == "abbrechen":
            bausteine.append(("abbrechen", nr))

        elif erstes == "warte":
            rest = _rest(text, "warte")
            if rest.endswith(" sekunden"):
                rest = rest[:-9]
            elif rest.endswith(" sekunde"):
                rest = rest[:-8]
            bausteine.append(("warte", nr, _ausdruck(rest, nr)))

        elif erstes == "farbe":
            bausteine.append(("farbe", nr, _ausdruck(_rest(text, "farbe"), nr)))

        elif erstes == "leere":
            bausteine.append(("leere", nr))

        # ---- Webseiten ----
        elif erstes == "seite":
            rest = _rest(text, "seite")
            bausteine.append(("seite", nr, _ausdruck(rest, nr) if rest else None))

        elif erstes in ("überschrift", "ueberschrift", "absatz", "bild", "hintergrund", "textfarbe"):
            rest = _rest(text, erstes)
            if not rest:
                raise EdgyFehler(f"Hinter {erstes} fehlt ein Wert, z. B. {erstes} \"...\"", nr)
            bausteine.append(("web_" + erstes.replace("ue", "ü"), nr, _ausdruck(rest, nr)))

        elif erstes in ("knopf", "link"):
            beschriftung, ziel = _teile_bei(_rest(text, erstes), "zu", nr)
            if erstes == "link" and ziel is None:
                raise EdgyFehler("So geht link:  link \"Google\" zu \"https://google.de\"", nr)
            bausteine.append(("web_" + erstes, nr, beschriftung, ziel))

        elif erstes == "trennlinie":
            bausteine.append(("web_trennlinie", nr))

        elif text == "zeig seite":
            bausteine.append(("zeig_seite", nr))

        else:
            raise EdgyFehler(f"Den Befehl '{erstes}' gibt es (noch) nicht. Tipp: hilfe", nr)

    return bausteine, pos, None


def _schleifen_inhalt(zeilen, pos, name, nr):
    inhalt, pos, ende = _block(zeilen, pos)
    if ende != "ende":
        raise EdgyFehler(f"Dieses {name} wird nie mit 'ende' abgeschlossen.", nr)
    return inhalt, pos


# ---------------------------------------------------------------------------
# Ausführen
# ---------------------------------------------------------------------------

class Edgy:
    """Führt Edgy-Programme aus.

    ausgabe(text[, farbe])  – für jede Ausgabe (farbe = Hex-Farbe, falls gesetzt)
    eingabe(frage) -> str   – wenn das Programm etwas fragt
    leeren()                – wenn das Programm 'leere' aufruft
    zeige_seite(html, titel)– wenn eine Webseite fertig ist
    """

    MAX_WIEDERHOLUNGEN = 1_000_000

    def __init__(self, ausgabe=print, eingabe=input, leeren=None, zeige_seite=None):
        self.ausgabe = ausgabe
        self.eingabe = eingabe
        self.leeren = leeren
        self.zeige_seite = zeige_seite
        self.variablen = {}
        self.stopp = False
        self.farbe = None
        self.seite = None
        self.letzte_seite_html = None

    def starte(self, code):
        self.stopp = False
        self.seite = None
        self.farbe = None
        try:
            self._fuehre_aus(zerlege_programm(code))
        except _SchleifeVerlassen:
            raise EdgyFehler("'abbrechen' geht nur in einer Schleife.")
        if self.seite is not None and self.seite.teile:
            self._seite_zeigen()

    def _sag(self, text):
        if self.farbe:
            self.ausgabe(text, self.farbe)
        else:
            self.ausgabe(text)

    def _web(self):
        if self.seite is None:
            self.seite = Webseite()
        return self.seite

    def _seite_zeigen(self):
        seite = self.seite
        self.letzte_seite_html = seite.html()
        self.seite = None
        if self.zeige_seite:
            self.zeige_seite(self.letzte_seite_html, seite.titel)

    def _fuehre_aus(self, bausteine):
        v = self.variablen
        for b in bausteine:
            if self.stopp:
                raise Abbruch()
            art = b[0]
            if art == "gib":
                self._sag("" if b[2] is None else als_text(b[2].berechne(v)))
            elif art == "merk":
                v[b[2]] = b[3].berechne(v)
            elif art == "frag":
                frage = als_text(b[3].berechne(v)) if b[3] else ""
                v[b[2]] = zu_wert(self.eingabe(frage))
            elif art == "wenn":
                if wahrheit(b[2].berechne(v)):
                    self._fuehre_aus(b[3])
                else:
                    self._fuehre_aus(b[4])
            elif art == "wiederhol":
                anzahl = b[2].berechne(v)
                if isinstance(anzahl, bool) or not isinstance(anzahl, int):
                    raise EdgyFehler("wiederhol braucht eine ganze Zahl.", b[1])
                if anzahl > self.MAX_WIEDERHOLUNGEN:
                    raise EdgyFehler("So oft wiederholen ist zu viel (max. 1 Million).", b[1])
                try:
                    for _ in range(max(anzahl, 0)):
                        self._pruefe_stopp()
                        self._fuehre_aus(b[3])
                except _SchleifeVerlassen:
                    pass
            elif art == "solange":
                try:
                    while wahrheit(b[2].berechne(v)):
                        self._pruefe_stopp()
                        self._fuehre_aus(b[3])
                except _SchleifeVerlassen:
                    pass
            elif art == "zähl":
                start, ende = b[3].berechne(v), b[4].berechne(v)
                for x in (start, ende):
                    if isinstance(x, bool) or not isinstance(x, int):
                        raise EdgyFehler("zähl braucht ganze Zahlen, z. B. zähl i von 1 bis 10.", b[1])
                schritt = 1 if ende >= start else -1
                try:
                    for i in range(start, ende + schritt, schritt):
                        self._pruefe_stopp()
                        v[b[2]] = i
                        self._fuehre_aus(b[5])
                except _SchleifeVerlassen:
                    pass
            elif art == "abbrechen":
                raise _SchleifeVerlassen()
            elif art == "warte":
                sekunden = b[2].berechne(v)
                if isinstance(sekunden, bool) or not isinstance(sekunden, (int, float)) or sekunden < 0:
                    raise EdgyFehler("warte braucht eine Zahl in Sekunden, z. B. warte 2", b[1])
                ende_zeit = time.monotonic() + min(sekunden, 3600)
                while time.monotonic() < ende_zeit:
                    self._pruefe_stopp()
                    time.sleep(min(0.05, max(0, ende_zeit - time.monotonic())))
            elif art == "farbe":
                self.farbe = farbe_zu_hex(b[2].berechne(v), b[1])
            elif art == "leere":
                if self.leeren:
                    self.leeren()
            elif art == "seite":
                self.seite = Webseite(als_text(b[2].berechne(v)) if b[2] else "Meine Seite")
            elif art == "web_überschrift":
                self._web().teile.append(f"<h1>{html.escape(als_text(b[2].berechne(v)))}</h1>")
            elif art == "web_absatz":
                self._web().teile.append(f"<p>{html.escape(als_text(b[2].berechne(v)))}</p>")
            elif art == "web_bild":
                quelle = html.escape(als_text(b[2].berechne(v)), quote=True)
                self._web().teile.append(f'<img src="{quelle}" alt="">')
            elif art == "web_hintergrund":
                self._web().hintergrund = farbe_zu_hex(b[2].berechne(v), b[1]) or "#ffffff"
            elif art == "web_textfarbe":
                self._web().textfarbe = farbe_zu_hex(b[2].berechne(v), b[1]) or "#111111"
            elif art == "web_knopf":
                text = html.escape(als_text(b[2].berechne(v)))
                if b[3] is None:
                    self._web().teile.append(f'<button class="knopf">{text}</button>')
                else:
                    ziel = html.escape(als_text(b[3].berechne(v)), quote=True)
                    self._web().teile.append(f'<a class="knopf" href="{ziel}">{text}</a>')
            elif art == "web_link":
                text = html.escape(als_text(b[2].berechne(v)))
                ziel = html.escape(als_text(b[3].berechne(v)), quote=True)
                self._web().teile.append(f'<p><a href="{ziel}">{text}</a></p>')
            elif art == "web_trennlinie":
                self._web().teile.append("<hr>")
            elif art == "zeig_seite":
                if self.seite is None or not self.seite.teile:
                    raise EdgyFehler("Die Seite ist noch leer. Füg erst z. B. überschrift \"Hallo\" hinzu.", b[1])
                self._seite_zeigen()

    def _pruefe_stopp(self):
        if self.stopp:
            raise Abbruch()


def braucht_mehr_zeilen(code):
    """True, wenn noch ein Block offen ist (für die Eingabezeile)."""
    return block_tiefe(code) > 0


def block_tiefe(code):
    tiefe = 0
    for roh in code.splitlines():
        text = _ohne_kommentar(roh).strip()
        if not text:
            continue
        erstes = text.split()[0]
        if erstes in BLOCK_START:
            tiefe += 1
        elif erstes == "ende":
            tiefe -= 1
    return tiefe


# ---------------------------------------------------------------------------
# Vorschläge (Autovervollständigung mit Tab)
# ---------------------------------------------------------------------------

# Was am Zeilenanfang vorgeschlagen wird
BEFEHLS_VORSCHLAEGE = [
    "gib aus ", "merk ", "frag ", "wenn ", "sonst", "ende", "wiederhol ",
    "solange ", "zähl ", "warte ", "abbrechen", "farbe ", "leere",
    "seite ", "überschrift ", "absatz ", "knopf ", "link ", "bild ",
    "trennlinie", "hintergrund ", "textfarbe ", "zeig seite",
]

WORT_VORSCHLAEGE = ["dann", "mal", "und", "oder", "nicht", "wahr", "falsch", "ist", "von", "bis", "zu"]

FUNKTIONS_VORSCHLAEGE = ["zufall(", "länge(", "groß(", "klein(", "runde(", "wurzel(",
                         "zahl(", "text(", "uhrzeit()", "datum()"]

FARB_VORSCHLAEGE = ["schwarz", "weiß", "rot", "gold", "gelb", "blau", "grün", "grau",
                    "lila", "orange", "pink", "türkis", "braun", "normal"]


def vorschlag(zeile_vorher, variablen=(), extra_befehle=()):
    """Gibt zurück, was hinter dem Cursor grau ergänzt werden soll ('' = nichts)."""
    if zeile_vorher.count('"') % 2 == 1:
        # Innerhalb von Text: nur Farben nach farbe/hintergrund/textfarbe
        m = re.match(r'\s*(farbe|hintergrund|textfarbe)\s+"([^"]*)$', zeile_vorher)
        if m and m.group(2):
            for f in FARB_VORSCHLAEGE:
                if f.startswith(m.group(2).lower()) and f != m.group(2).lower():
                    return f[len(m.group(2)):] + '"'
        return ""

    links = zeile_vorher.lstrip()
    if not links:
        return ""

    # Ganze Zeile ist erst ein Befehlsanfang (z. B. "g" -> "gib aus ")
    if re.fullmatch(r"[A-Za-zÄÖÜäöüß ]+", links) and " " not in links.rstrip():
        for b in list(extra_befehle) + BEFEHLS_VORSCHLAEGE:
            if b.startswith(links) and b != links:
                return b[len(links):]
    if links in ("gib", "gib ", "gib a", "gib au"):
        return "gib aus "[len(links):]
    if links == "zeig" or links in ("zeig ", "zeig s", "zeig se", "zeig sei", "zeig seit"):
        return "zeig seite"[len(links):]

    erstes = links.split()[0]

    # Passende Endungen, wenn die Zeile mit Leerzeichen endet
    if zeile_vorher.endswith(" "):
        teile = links.split()
        if erstes == "wenn" and len(teile) >= 2 and teile[-1] != "dann":
            return "dann"
        if erstes == "wiederhol" and len(teile) == 2:
            return "mal"
        if erstes in ("zähl", "zaehl"):
            if len(teile) == 2:
                return "von "
            if len(teile) == 4 and teile[2] == "von":
                return "bis "
        if erstes in ("knopf", "link") and len(teile) >= 2 and "zu" not in teile:
            return 'zu "https://'
        if erstes in ("farbe", "hintergrund", "textfarbe") and len(teile) == 1:
            return '"'
        return ""

    # Aktuelles Wort ergänzen
    m = re.search(r"([A-Za-zÄÖÜäöüß_][A-Za-zÄÖÜäöüß_0-9]*)$", zeile_vorher)
    if not m or len(links.split()) < 2:
        return ""
    wort = m.group(1)
    kandidaten = sorted(variablen) + FUNKTIONS_VORSCHLAEGE + WORT_VORSCHLAEGE
    for k in kandidaten:
        if k.startswith(wort) and k != wort:
            return k[len(wort):]
    return ""
