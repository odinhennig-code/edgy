"""Edgy – das Herzstück: liest Edgy-Code und führt ihn aus."""

import re


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


SCHLUESSELWOERTER = {
    "gib", "aus", "merk", "frag", "wenn", "dann", "sonst", "ende",
    "wiederhol", "mal", "und", "oder", "nicht", "wahr", "falsch", "ist",
}

# ---------------------------------------------------------------------------
# Ausdrücke: Zerlegen (Tokens) und Ausrechnen
# ---------------------------------------------------------------------------

_TOKEN = re.compile(
    r"""\s*(?:
        (?P<zahl>\d+(?:[.,]\d+)?)
      | (?P<text>"[^"]*")
      | (?P<op>==|!=|<=|>=|[+\-*/%()<>=])
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
            wert = wert.replace(",", ".")
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

    def _sieh(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

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
            if wert in self.v:
                return self.v[wert]
            raise EdgyFehler(f"'{wert}' kenne ich nicht. Hast du es vorher mit merk gespeichert?", self.zeile)
        raise EdgyFehler(f"Unerwartet: '{wert}'.", self.zeile)

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
# Befehle: Code in Bausteine zerlegen
# ---------------------------------------------------------------------------

_NAME = re.compile(r"^[A-Za-zÄÖÜäöüß_][A-Za-zÄÖÜäöüß_0-9]*$")


def _pruefe_name(name, zeile):
    if not _NAME.match(name):
        raise EdgyFehler(f"'{name}' ist kein gültiger Name.", zeile)
    if name in SCHLUESSELWOERTER:
        raise EdgyFehler(f"'{name}' ist ein Edgy-Befehl und kann kein Name sein.", zeile)


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
    bausteine, pos, ende = _block(zeilen, 0, stop=())
    if ende is not None:
        raise EdgyFehler(f"'{ende}' ohne passendes wenn oder wiederhol.", zeilen[pos - 1][0])
    return bausteine


def _ausdruck(text, zeile):
    return Ausdruck(zerlege(text, zeile), zeile)


def _block(zeilen, pos, stop):
    bausteine = []
    while pos < len(zeilen):
        nr, text = zeilen[pos]
        erstes = text.split()[0]
        if erstes in ("sonst", "ende"):
            if text != erstes:
                raise EdgyFehler(f"Hinter '{erstes}' darf nichts mehr stehen.", nr)
            if erstes in stop:
                return bausteine, pos + 1, erstes
            return bausteine, pos + 1, erstes
        pos += 1

        if text.startswith("gib aus"):
            rest = text[len("gib aus"):].strip()
            if not rest:
                bausteine.append(("gib", nr, None))
            else:
                bausteine.append(("gib", nr, _ausdruck(rest, nr)))

        elif erstes == "gib":
            raise EdgyFehler("Meintest du 'gib aus'?", nr)

        elif erstes == "merk":
            rest = text[4:].strip()
            if "=" not in rest:
                raise EdgyFehler("So geht merk:  merk name = \"Max\"", nr)
            name, wert = rest.split("=", 1)
            name = name.strip()
            _pruefe_name(name, nr)
            bausteine.append(("merk", nr, name, _ausdruck(wert.strip(), nr)))

        elif erstes == "frag":
            teile = text[4:].strip().split(None, 1)
            if not teile:
                raise EdgyFehler("So geht frag:  frag name \"Wie heißt du?\"", nr)
            _pruefe_name(teile[0], nr)
            frage = _ausdruck(teile[1], nr) if len(teile) > 1 else None
            bausteine.append(("frag", nr, teile[0], frage))

        elif erstes == "wenn":
            if not text.endswith(" dann"):
                raise EdgyFehler("Hinter wenn ... gehört am Ende ein 'dann'.", nr)
            bedingung = _ausdruck(text[4:-5].strip(), nr)
            ja, pos, ende = _block(zeilen, pos, stop=("sonst", "ende"))
            nein = []
            if ende == "sonst":
                nein, pos, ende = _block(zeilen, pos, stop=("ende",))
                if ende == "sonst":
                    raise EdgyFehler("Ein wenn darf nur ein sonst haben.", nr)
            if ende != "ende":
                raise EdgyFehler("Dieses wenn wird nie mit 'ende' abgeschlossen.", nr)
            bausteine.append(("wenn", nr, bedingung, ja, nein))

        elif erstes == "wiederhol":
            if not text.endswith(" mal"):
                raise EdgyFehler("So geht wiederhol:  wiederhol 3 mal", nr)
            anzahl = _ausdruck(text[9:-4].strip(), nr)
            inhalt, pos, ende = _block(zeilen, pos, stop=("ende",))
            if ende != "ende":
                raise EdgyFehler("Dieses wiederhol wird nie mit 'ende' abgeschlossen.", nr)
            bausteine.append(("wiederhol", nr, anzahl, inhalt))

        else:
            raise EdgyFehler(f"Den Befehl '{erstes}' gibt es (noch) nicht. Tipp: hilfe", nr)

    return bausteine, pos, None


# ---------------------------------------------------------------------------
# Ausführen
# ---------------------------------------------------------------------------

class Edgy:
    """Führt Edgy-Programme aus.

    ausgabe(text)        – wird für jede Ausgabe aufgerufen
    eingabe(frage)->str  – wird aufgerufen, wenn das Programm etwas fragt
    """

    MAX_WIEDERHOLUNGEN = 1_000_000

    def __init__(self, ausgabe=print, eingabe=input):
        self.ausgabe = ausgabe
        self.eingabe = eingabe
        self.variablen = {}
        self.stopp = False

    def starte(self, code):
        self.stopp = False
        self._fuehre_aus(zerlege_programm(code))

    def _fuehre_aus(self, bausteine):
        for b in bausteine:
            if self.stopp:
                raise Abbruch()
            art = b[0]
            if art == "gib":
                self.ausgabe("" if b[2] is None else als_text(b[2].berechne(self.variablen)))
            elif art == "merk":
                self.variablen[b[2]] = b[3].berechne(self.variablen)
            elif art == "frag":
                frage = als_text(b[3].berechne(self.variablen)) if b[3] else ""
                self.variablen[b[2]] = zu_wert(self.eingabe(frage))
            elif art == "wenn":
                if wahrheit(b[2].berechne(self.variablen)):
                    self._fuehre_aus(b[3])
                else:
                    self._fuehre_aus(b[4])
            elif art == "wiederhol":
                anzahl = b[2].berechne(self.variablen)
                if isinstance(anzahl, bool) or not isinstance(anzahl, int):
                    raise EdgyFehler("wiederhol braucht eine ganze Zahl.", b[1])
                if anzahl > self.MAX_WIEDERHOLUNGEN:
                    raise EdgyFehler("So oft wiederholen ist zu viel (max. 1 Million).", b[1])
                for _ in range(max(anzahl, 0)):
                    self._fuehre_aus(b[3])


def braucht_mehr_zeilen(code):
    """True, wenn noch ein wenn/wiederhol offen ist (für die Eingabezeile)."""
    tiefe = 0
    for roh in code.splitlines():
        text = _ohne_kommentar(roh).strip()
        if not text:
            continue
        erstes = text.split()[0]
        if erstes in ("wenn", "wiederhol"):
            tiefe += 1
        elif erstes == "ende":
            tiefe -= 1
    return tiefe > 0
