"""Das eigene Edgy-Fenster: Konsole + Editor."""

import os
import pathlib
import queue
import re
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, font as tkfont

from . import update
from .sprache import (
    BLOCK_START, FUNKTIONEN, SCHLUESSELWOERTER, Abbruch, Edgy, EdgyFehler,
    block_tiefe, braucht_mehr_zeilen, vorschlag,
)
from .version import VERSION

# ---------------------------------------------------------------- Farben
HINTERGRUND = "#0c0c0d"
LINIE = "#1f1f22"
TEXT = "#ececec"
GRAU = "#5f5f66"
HELLGRAU = "#8d8d94"
GEIST = "#4a4a50"
ROT = "#ff3b3b"
GOLD = "#ffce00"
DE_ROT = "#dd0000"
AUSWAHL = "#2a2a30"

SYNTAX = {
    "kw": "#ff5c5c",
    "fn": "#ff9f5a",
    "str": "#ffce00",
    "num": "#9ad0ff",
    "kom": "#55555c",
}

FENSTER_BEFEHLE = ["hilfe", "beispiel", "webseite", "editor", "öffne", "leeren", "version", "beenden"]

HILFE = """\
AUSGABE & EINGABE
  gib aus "Hallo"              Text anzeigen
  merk name = "Max"            etwas speichern
  frag alter "Wie alt?"        den Nutzer etwas fragen
  farbe "rot"                  Ausgabe einfärben ("normal" = zurück)
  leere                        Fenster leeren
  warte 2                      2 Sekunden warten

ENTSCHEIDUNGEN & SCHLEIFEN
  wenn alter > 12 dann ... sonst ... ende
  wiederhol 3 mal ... ende
  solange zahl < 10 ... ende
  zähl i von 1 bis 10 ... ende
  abbrechen                    Schleife sofort verlassen

FUNKTIONEN
  zufall(1, 6)   länge(text)   groß(text)   klein(text)
  runde(3.7)     wurzel(16)    zahl("5")    text(5)
  uhrzeit()      datum()

WEBSEITEN  (öffnen sich im Browser)
  seite "Meine Seite"          neue Seite mit Titel
  überschrift "Hallo"          große Überschrift
  absatz "Text"                normaler Text
  knopf "Los" zu "https://…"   Knopf (mit Link)
  link "Mehr" zu "https://…"   Link
  bild "https://…/bild.png"    Bild
  trennlinie                   Linie
  hintergrund "schwarz"        Hintergrundfarbe
  textfarbe "weiß"             Textfarbe
  zeig seite                   Seite jetzt öffnen (passiert sonst am Ende)

RECHNEN & VERGLEICHEN
  + - * / %   ( )      == != < > <= >= ist   und oder nicht wahr falsch
  # Kommentar

FENSTER
  Tab        Vorschlag übernehmen        Esc        Programm stoppen
  F5         Editor-Code starten         Strg+S     speichern
  Strg+O     öffnen                      Strg+N     neue Datei
  Befehle:   hilfe  beispiel  webseite  editor  öffne  leeren  version  beenden
"""

BEISPIEL = """\
# Ein kleines Beispiel
frag name "Wie heißt du?"
farbe "gold"
gib aus "Hi " + name + "!"
farbe "normal"

zähl i von 1 bis 3
  gib aus "Runde " + i
  warte 0.3
ende

merk wurf = zufall(1, 6)
wenn wurf == 6 dann
  gib aus "Eine 6! Glück gehabt."
sonst
  gib aus "Gewürfelt: " + wurf
ende
"""

BEISPIEL_SEITE = """\
seite "Meine erste Seite"
hintergrund "schwarz"
textfarbe "weiß"
überschrift "Hallo, Welt!"
absatz "Diese Seite wurde mit Edgy gebaut."
knopf "Zu Google" zu "https://google.de"
trennlinie
absatz "Heute ist der " + datum() + "."
"""


def ressource(name):
    basis = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(basis, "assets", name)


def dokumente_ordner():
    """Der Edgy-Ordner in 'Dokumente'."""
    pfad = None
    if os.name == "nt":
        try:
            import ctypes
            puffer = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, puffer) == 0:
                pfad = puffer.value
        except Exception:
            pfad = None
    if not pfad:
        pfad = os.path.join(os.path.expanduser("~"), "Documents")
    ordner = os.path.join(pfad, "Edgy")
    os.makedirs(ordner, exist_ok=True)
    return ordner


def _windows_feinschliff(root):
    """Dunkle Titelleiste unter Windows 10/11."""
    if os.name != "nt":
        return
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        wert = ctypes.c_int(1)
        for attribut in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribut, ctypes.byref(wert), 4) == 0:
                break
    except Exception:
        pass


# ---------------------------------------------------------------- Syntax-Farben
_MUSTER = re.compile(
    r'(?P<kom>#[^\n]*)|(?P<str>"[^"\n]*"?)|(?P<num>\b\d+(?:\.\d+)?\b)'
    r"|(?P<wort>[A-Za-zÄÖÜäöüß_][A-Za-zÄÖÜäöüß_0-9]*)"
)


def faerbe(t):
    """Färbt Befehle, Texte, Zahlen und Kommentare in einem Text-Feld."""
    for tag in SYNTAX:
        t.tag_remove(tag, "1.0", "end")
    inhalt = t.get("1.0", "end-1c")
    if len(inhalt) > 200_000:
        return
    for m in _MUSTER.finditer(inhalt):
        art = m.lastgroup
        if art == "wort":
            w = m.group(art)
            if w in SCHLUESSELWOERTER:
                art = "kw"
            elif w in FUNKTIONEN and inhalt[m.end():m.end() + 1] == "(":
                art = "fn"
            else:
                continue
        t.tag_add(art, f"1.0+{m.start()}c", f"1.0+{m.end()}c")
    t.tag_raise("geist")
    t.tag_raise("sel")


# ---------------------------------------------------------------- Vorschläge
class Geist:
    """Grauer Vorschlag hinter dem Cursor – mit Tab übernehmen (wie in VS Code)."""

    def __init__(self, t, variablen_fn, extra_fn=lambda: (), bei_aenderung=None, tab_ohne=None):
        self.t = t
        self.variablen_fn = variablen_fn
        self.extra_fn = extra_fn
        self.bei_aenderung = bei_aenderung
        self.tab_ohne = tab_ohne
        self.text = ""
        t.tag_configure("geist", foreground=GEIST)
        t.bind("<KeyPress>", self._taste, add="+")
        t.bind("<KeyRelease>", self._losgelassen, add="+")
        t.bind("<Tab>", self._tab)
        t.bind("<Right>", self._rechts)
        t.bind("<End>", self._rechts)
        t.bind("<ButtonPress-1>", lambda e: self.weg(), add="+")
        t.bind("<FocusOut>", lambda e: self.weg(), add="+")

    def weg(self):
        bereich = self.t.tag_ranges("geist")
        if bereich:
            self.t.delete(bereich[0], bereich[1])
        self.text = ""
        if self.bei_aenderung:
            self.bei_aenderung(False)

    def _taste(self, e):
        if e.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
                        "Caps_Lock", "Tab", "Right", "End"):
            return None
        self.weg()
        return None

    def _losgelassen(self, e):
        if e.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
                        "Caps_Lock", "Tab", "Escape", "Up", "Down", "Return", "KP_Enter"):
            return
        if e.state & 0x4:  # Strg-Kürzel
            return
        self.zeige()

    def zeige(self):
        self.weg()
        t = self.t
        if t.tag_ranges("sel"):
            return
        if t.compare("insert", "!=", "insert lineend"):
            return
        vorher = t.get("insert linestart", "insert")
        nur_zeilenanfang = not vorher.strip() or " " not in vorher.strip()
        extra = self.extra_fn() if nur_zeilenanfang else ()
        v = vorschlag(vorher, self.variablen_fn(), extra)
        if v:
            t.insert("insert", v, "geist")
            t.mark_set("insert", f"insert-{len(v)}c")
            self.text = v
            if self.bei_aenderung:
                self.bei_aenderung(True)

    def annehmen(self):
        bereich = self.t.tag_ranges("geist")
        if not bereich:
            return False
        self.t.tag_remove("geist", bereich[0], bereich[1])
        self.t.mark_set("insert", bereich[1])
        self.text = ""
        if self.bei_aenderung:
            self.bei_aenderung(False)
        self.t.event_generate("<<Vorschlag>>")
        self.zeige()
        return True

    def _tab(self, _=None):
        if not self.annehmen() and self.tab_ohne:
            self.tab_ohne()
        return "break"

    def _rechts(self, _=None):
        if self.text and self.t.compare("insert", "==", self.t.tag_ranges("geist")[0]):
            self.annehmen()
            return "break"
        self.weg()
        return None


class DuenneLeiste(tk.Canvas):
    """Schmale, unauffällige Scrollleiste (die von Windows ist zu dick und weiß)."""

    def __init__(self, eltern, ziel):
        super().__init__(eltern, width=6, bg=HINTERGRUND, highlightthickness=0, bd=0, cursor="arrow")
        self.ziel = ziel
        self.anfang, self.ende = 0.0, 1.0
        self.ueber = False
        self.bind("<Configure>", lambda e: self._zeichne())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonPress-1>", self._klick)
        self.bind("<B1-Motion>", self._ziehen)
        self.bind("<MouseWheel>", lambda e: ziel.yview_scroll(int(-e.delta / 120) * 3, "units"))

    def set(self, anfang, ende):
        self.anfang, self.ende = float(anfang), float(ende)
        self._zeichne()

    def _hover(self, ja):
        self.ueber = ja
        self._zeichne()

    def _zeichne(self):
        self.delete("all")
        if self.ende - self.anfang >= 0.999:
            return
        h = self.winfo_height()
        y0 = max(int(self.anfang * h), 0)
        y1 = max(int(self.ende * h), y0 + 24)
        self.create_rectangle(1, y0, 5, y1, fill="#4a4a50" if self.ueber else "#2c2c31", width=0)

    def _klick(self, e):
        self._start_y = e.y
        self._start_anfang = self.anfang
        h = max(self.winfo_height(), 1)
        if not self.anfang * h <= e.y <= self.ende * h:
            self.ziel.yview_moveto(max(e.y / h - (self.ende - self.anfang) / 2, 0))
            self._start_anfang = float(self.ziel.yview()[0])

    def _ziehen(self, e):
        h = max(self.winfo_height(), 1)
        self.ziel.yview_moveto(self._start_anfang + (e.y - self._start_y) / h)


def _knopf(eltern, text, befehl, farbe=HELLGRAU, hover=TEXT, fett=False):
    l = tk.Label(eltern, text=text, fg=farbe, bg=HINTERGRUND, cursor="hand2",
                 font=("Segoe UI Semibold" if fett else "Segoe UI", 10), padx=8, pady=2)
    l.bind("<Button-1>", lambda e: befehl())
    l.bind("<Enter>", lambda e: l.configure(fg=hover))
    l.bind("<Leave>", lambda e: l.configure(fg=l._farbe))
    l._farbe = farbe
    return l


# ---------------------------------------------------------------- Fenster
class EdgyFenster:
    def __init__(self, start_datei=None):
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Edgy.Programmiersprache")
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        self.root = tk.Tk()
        self.root.title("Edgy")
        self.root.geometry("1000x640")
        self.root.minsize(600, 380)
        self.root.configure(bg=HINTERGRUND)
        try:
            self.root.iconbitmap(default=ressource("edgy.ico"))
        except Exception:
            try:
                self._icon = tk.PhotoImage(file=ressource("edgy.png"))
                self.root.iconphoto(True, self._icon)
            except Exception:
                pass

        familien = set(tkfont.families())
        name = next((f for f in ("Cascadia Mono", "Consolas", "DejaVu Sans Mono") if f in familien), "Courier")
        self.schrift = tkfont.Font(family=name, size=12)
        self.schrift_fett = tkfont.Font(family=name, size=12, weight="bold")
        self.schrift_klein = tkfont.Font(family=name, size=10)

        self.ausgaben = queue.Queue()
        self.antworten = queue.Queue()
        self.edgy = Edgy(ausgabe=self._aus_thread, eingabe=self._frage_aus_thread,
                         leeren=lambda: self.ausgaben.put(("leeren", None)),
                         zeige_seite=self._seite_aus_thread)
        self.laeuft = False
        self.wartet_auf_antwort = False
        self.puffer = []
        self.verlauf = []
        self.verlauf_pos = 0
        self.datei = None
        self.ansicht = None
        self._farb_tags = set()

        self._baue_kopf()
        self.koerper = tk.Frame(self.root, bg=HINTERGRUND)
        self.koerper.pack(fill="both", expand=True)
        self._baue_konsole()
        self._baue_editor()
        self._tastenkuerzel()

        self.zeige_ansicht("konsole")
        self._begruessung()
        self.root.after(30, self._verarbeite_ausgaben)
        self.root.protocol("WM_DELETE_WINDOW", self._schliessen)
        _windows_feinschliff(self.root)
        self.root.after(150, self._fokus_holen)

        if update.ist_exe():
            threading.Thread(target=self._pruefe_update, daemon=True).start()

        if start_datei:
            self.root.after(250, lambda: self._oeffne_pfad(start_datei, starten=True))

    # ------------------------------------------------------------ Aufbau
    def _baue_kopf(self):
        streifen = tk.Frame(self.root, height=3, bg=HINTERGRUND)
        streifen.pack(fill="x", side="top")
        for farbe in ("#1b1b1b", DE_ROT, GOLD):
            tk.Frame(streifen, height=3, bg=farbe).pack(side="left", fill="both", expand=True)

        kopf = tk.Frame(self.root, bg=HINTERGRUND)
        kopf.pack(fill="x", padx=20, pady=(12, 0))
        try:
            self._zeichen = tk.PhotoImage(file=ressource("zeichen.png"))
            tk.Label(kopf, image=self._zeichen, bg=HINTERGRUND).pack(side="left", padx=(0, 10))
        except Exception:
            pass
        tk.Label(kopf, text="Edgy", font=("Segoe UI Semibold", 15), fg=TEXT,
                 bg=HINTERGRUND).pack(side="left")
        tk.Label(kopf, text=f"v{VERSION}", font=("Segoe UI", 9), fg=GRAU,
                 bg=HINTERGRUND).pack(side="left", padx=(8, 0), pady=(4, 0))

        reiter = tk.Frame(kopf, bg=HINTERGRUND)
        reiter.pack(side="left", padx=(36, 0))
        self.reiter = {}
        for schluessel, beschriftung in (("konsole", "Konsole"), ("editor", "Editor")):
            l = _knopf(reiter, beschriftung, lambda s=schluessel: self.zeige_ansicht(s))
            l.pack(side="left")
            self.reiter[schluessel] = l

        rechts = tk.Frame(kopf, bg=HINTERGRUND)
        rechts.pack(side="right")
        _knopf(rechts, "▶  Start", self.starte_editor, farbe=DE_ROT, hover=ROT, fett=True).pack(side="right", padx=(10, 0))
        tk.Frame(rechts, width=1, height=16, bg=LINIE).pack(side="right", padx=6)
        _knopf(rechts, "Speichern", self.speichern).pack(side="right")
        _knopf(rechts, "Öffnen", self.oeffnen).pack(side="right")
        _knopf(rechts, "Neu", self.neu).pack(side="right")

        self.status = tk.Label(self.root, text="", font=("Segoe UI", 9), fg=GRAU, bg=HINTERGRUND, anchor="w")
        self.status.pack(fill="x", padx=28, pady=(2, 0))

    def _textfeld(self, eltern, **extra):
        optionen = dict(
            height=1, width=1, bg=HINTERGRUND, fg=TEXT, font=self.schrift, bd=0,
            highlightthickness=0, wrap="word", insertbackground=GOLD, insertwidth=2,
            selectbackground=AUSWAHL, selectforeground=TEXT, padx=0, pady=4,
            spacing1=2, spacing3=2, undo=True,
        )
        optionen.update(extra)
        t = tk.Text(eltern, **optionen)
        for tag, farbe in SYNTAX.items():
            t.tag_configure(tag, foreground=farbe)
        t.tag_configure("geist", foreground=GEIST)
        return t

    def _leiste(self, eltern, ziel):
        return DuenneLeiste(eltern, ziel)

    def _baue_konsole(self):
        self.konsole = tk.Frame(self.koerper, bg=HINTERGRUND)

        # Eingabe zuerst unten festmachen (wird nie rausgedrückt)
        unten = tk.Frame(self.konsole, bg=HINTERGRUND)
        unten.pack(fill="x", side="bottom", padx=28, pady=(0, 18))
        tk.Frame(unten, height=1, bg=LINIE).pack(fill="x", pady=(0, 10))
        zeile = tk.Frame(unten, bg=HINTERGRUND)
        zeile.pack(fill="x")
        self.prompt = tk.Label(zeile, text="›", font=self.schrift_fett, fg=DE_ROT, bg=HINTERGRUND, width=2, anchor="w")
        self.prompt.pack(side="left")
        self.tab_hinweis = tk.Label(zeile, text="Tab ↹", font=self.schrift_klein, fg=GRAU, bg=HINTERGRUND)
        self.feld = self._textfeld(zeile, wrap="none")
        self.feld.configure(height=1, pady=0, spacing1=0, spacing3=0)
        self.feld.pack(side="left", fill="x", expand=True)
        self.feld.bind("<Return>", self._enter)
        self.feld.bind("<KP_Enter>", self._enter)
        self.feld.bind("<Up>", lambda e: self._blaettern(-1))
        self.feld.bind("<Down>", lambda e: self._blaettern(1))
        self.feld.bind("<<Paste>>", self._einfuegen)
        self.feld.bind("<KeyRelease>", lambda e: faerbe(self.feld), add="+")
        self.geist_konsole = Geist(
            self.feld, self._bekannte_namen,
            extra_fn=lambda: FENSTER_BEFEHLE if not self.puffer and not self.wartet_auf_antwort else (),
            bei_aenderung=self._tab_hinweis,
        )
        for w in (unten, zeile, self.prompt):
            w.bind("<Button-1>", lambda e: self.feld.focus_set())

        rahmen = tk.Frame(self.konsole, bg=HINTERGRUND)
        rahmen.pack(fill="both", expand=True, padx=28, pady=(10, 8))
        self.anzeige = self._textfeld(rahmen, cursor="arrow")
        leiste = self._leiste(rahmen, self.anzeige)
        self.anzeige.configure(yscrollcommand=leiste.set)
        leiste.pack(side="right", fill="y")
        self.anzeige.pack(side="left", fill="both", expand=True)
        self.anzeige.tag_configure("ein", foreground=GRAU)
        self.anzeige.tag_configure("fehler", foreground=ROT)
        self.anzeige.tag_configure("info", foreground=GOLD)
        self.anzeige.tag_configure("frage", foreground=GOLD)
        self.anzeige.tag_configure("hilfe", foreground=HELLGRAU)
        self.anzeige.tag_configure("titel", foreground=TEXT, font=self.schrift_fett)
        self.anzeige.configure(state="disabled")
        self.anzeige.bind("<ButtonRelease-1>", self._fokus_wenn_nichts_markiert)
        self.anzeige.bind("<Key>", self._tippen_umleiten)

    def _baue_editor(self):
        self.editor_rahmen = tk.Frame(self.koerper, bg=HINTERGRUND)

        fuss = tk.Label(self.editor_rahmen, text="Tab  Vorschlag übernehmen     F5  Starten     Strg+S  Speichern",
                        font=("Segoe UI", 9), fg=GRAU, bg=HINTERGRUND, anchor="w")
        fuss.pack(side="bottom", fill="x", padx=28, pady=(4, 14))

        innen = tk.Frame(self.editor_rahmen, bg=HINTERGRUND)
        innen.pack(fill="both", expand=True, padx=(16, 28), pady=(10, 0))
        self.nummern = tk.Text(innen, width=4, bg=HINTERGRUND, fg=GEIST, font=self.schrift, bd=0,
                               highlightthickness=0, padx=0, pady=4, spacing1=2, spacing3=2,
                               state="disabled", cursor="arrow", takefocus=0)
        self.nummern.tag_configure("rechts", justify="right")
        self.nummern.bind("<MouseWheel>", lambda e: "break")
        self.nummern.pack(side="left", fill="y", padx=(0, 14))
        self.editor = self._textfeld(innen, wrap="none")
        leiste = self._leiste(innen, self.editor)

        def scrollen(*args):
            leiste.set(*args)
            self.nummern.yview_moveto(args[0])

        self.editor.configure(yscrollcommand=scrollen)
        leiste.pack(side="right", fill="y")
        self.editor.pack(side="left", fill="both", expand=True)
        self.editor.bind("<Return>", self._editor_enter)
        self.editor.bind("<KP_Enter>", self._editor_enter)
        self.editor.bind("<KeyRelease>", lambda e: self._editor_geaendert(), add="+")
        self.editor.bind("<<Paste>>", lambda e: self.root.after(1, self._editor_geaendert), add="+")
        self.editor.bind("<<Vorschlag>>", lambda e: self._editor_geaendert(), add="+")
        self.editor.bind("<<Modified>>", self._modifiziert)
        self.editor.bind("<MouseWheel>", lambda e: self.root.after(1, lambda: self.nummern.yview_moveto(self.editor.yview()[0])), add="+")
        self.geist_editor = Geist(self.editor, self._bekannte_namen,
                                  tab_ohne=lambda: self.editor.insert("insert", "  "))
        self._nummern_aktualisieren()

    def _tastenkuerzel(self):
        kuerzel = {
            "<Control-s>": self.speichern, "<Control-S>": self.speichern,
            "<Control-o>": self.oeffnen, "<Control-O>": self.oeffnen,
            "<Control-n>": self.neu, "<Control-N>": self.neu,
            "<F5>": self.starte_editor,
            "<Control-l>": self._leeren,
        }
        for taste, befehl in kuerzel.items():
            for w in (self.root, self.feld, self.editor, self.anzeige):
                w.bind(taste, lambda e, b=befehl: (b(), "break")[1])
        self.root.bind("<Escape>", lambda e: self._stopp())

    # ------------------------------------------------------------ Ansichten
    def zeige_ansicht(self, welche):
        if welche == self.ansicht:
            return
        self.ansicht = welche
        self.konsole.pack_forget()
        self.editor_rahmen.pack_forget()
        if welche == "konsole":
            self.konsole.pack(fill="both", expand=True)
            self.feld.focus_set()
        else:
            self.editor_rahmen.pack(fill="both", expand=True)
            self.editor.focus_set()
        for s, l in self.reiter.items():
            l._farbe = TEXT if s == welche else GRAU
            l.configure(fg=l._farbe, font=("Segoe UI Semibold" if s == welche else "Segoe UI", 10))
        self._status()

    def _status(self, text=None):
        if text is None:
            name = os.path.basename(self.datei) if self.datei else "Unbenannt.edgy"
            geaendert = " •" if self.editor.edit_modified() else ""
            text = f"{name}{geaendert}" if self.ansicht == "editor" else ""
        self.status.configure(text=text)
        titel = "Edgy"
        if self.datei:
            titel = f"{os.path.basename(self.datei)} – Edgy"
        self.root.title(titel)

    def _fokus_holen(self):
        try:
            self.root.lift()
            self.root.focus_force()
            (self.feld if self.ansicht == "konsole" else self.editor).focus_force()
        except tk.TclError:
            pass

    def _tab_hinweis(self, sichtbar):
        if sichtbar:
            if not self.tab_hinweis.winfo_ismapped():
                self.tab_hinweis.pack(side="right", before=self.feld)
        else:
            self.tab_hinweis.pack_forget()

    def _bekannte_namen(self):
        namen = set(self.edgy.variablen)
        try:
            code = self.editor.get("1.0", "end-1c")
            namen.update(re.findall(r"^\s*(?:merk|frag|zähl|zaehl)\s+([A-Za-zÄÖÜäöüß_][\wÄÖÜäöüß]*)", code, re.M))
        except tk.TclError:
            pass
        return sorted(namen)

    # ------------------------------------------------------------ Konsole
    def _schreibe(self, text, tag=None):
        self.anzeige.configure(state="normal")
        self.anzeige.insert("end", text + "\n", tag or ())
        self.anzeige.configure(state="disabled")
        self.anzeige.see("end")

    def _leeren(self):
        self.anzeige.configure(state="normal")
        self.anzeige.delete("1.0", "end")
        self.anzeige.configure(state="disabled")

    def _begruessung(self):
        self._schreibe("Willkommen bei Edgy.", "titel")
        self._schreibe("Tipp einfach los – Vorschläge übernimmst du mit Tab.  hilfe zeigt alle Befehle.", "ein")
        self._schreibe("")

    def _fokus_wenn_nichts_markiert(self, _=None):
        if not self.anzeige.tag_ranges("sel"):
            self.feld.focus_set()

    def _tippen_umleiten(self, e):
        if e.state & 0x4:
            return None
        self.feld.focus_set()
        if e.char and e.char.isprintable():
            self.feld.insert("end", e.char)
            faerbe(self.feld)
            self.geist_konsole.zeige()
        elif e.keysym in ("Return", "KP_Enter"):
            self._enter()
        return "break"

    def _feld_text(self):
        self.geist_konsole.weg()
        return self.feld.get("1.0", "end-1c")

    def _feld_setzen(self, text):
        self.geist_konsole.weg()
        self.feld.delete("1.0", "end")
        self.feld.insert("1.0", text)
        faerbe(self.feld)

    def _einfuegen(self, _=None):
        try:
            inhalt = self.root.clipboard_get()
        except tk.TclError:
            return "break"
        self.geist_konsole.weg()
        zeilen = inhalt.replace("\r\n", "\n").split("\n")
        if len(zeilen) == 1:
            self.feld.insert("insert", inhalt)
            faerbe(self.feld)
            return "break"
        zeilen[0] = self._feld_text() + zeilen[0]
        self._feld_setzen("")
        for z in zeilen:
            if z.strip():
                self._verarbeite_zeile(z)
        return "break"

    def _enter(self, _=None):
        zeile = self._feld_text()
        self._feld_setzen("")
        self._verarbeite_zeile(zeile)
        return "break"

    def _verarbeite_zeile(self, zeile):
        if self.wartet_auf_antwort:
            self._schreibe(zeile, "ein")
            self.wartet_auf_antwort = False
            self.prompt.configure(text="›", fg=DE_ROT)
            self.antworten.put(zeile)
            return

        if self.laeuft:
            return

        if zeile.strip():
            self.verlauf.append(zeile)
        self.verlauf_pos = len(self.verlauf)

        einrueck = "  " * max(block_tiefe("\n".join(self.puffer)), 0)
        self._schreibe(("› " if not self.puffer else "  ") + einrueck + zeile.strip(), "ein")

        befehl = zeile.strip().lower()
        if not self.puffer and befehl in FENSTER_BEFEHLE + ["oeffne"]:
            self._fensterbefehl(befehl)
            return

        self.puffer.append(zeile)
        code = "\n".join(self.puffer)
        if braucht_mehr_zeilen(code):
            self.prompt.configure(text="…", fg=GOLD)
            return
        self.puffer = []
        self.prompt.configure(text="›", fg=DE_ROT)
        if code.strip():
            self._starte(code)

    def _blaettern(self, richtung):
        if not self.verlauf or self.wartet_auf_antwort:
            return "break"
        self.verlauf_pos = max(0, min(len(self.verlauf), self.verlauf_pos + richtung))
        self._feld_setzen(self.verlauf[self.verlauf_pos] if self.verlauf_pos < len(self.verlauf) else "")
        self.feld.mark_set("insert", "end")
        return "break"

    def _fensterbefehl(self, befehl):
        if befehl == "hilfe":
            self._schreibe(HILFE, "hilfe")
        elif befehl == "leeren":
            self._leeren()
        elif befehl == "beenden":
            self._schliessen()
        elif befehl in ("öffne", "oeffne"):
            self.oeffnen()
        elif befehl == "editor":
            self.zeige_ansicht("editor")
        elif befehl == "beispiel":
            self._schreibe(BEISPIEL.rstrip(), "ein")
            self._schreibe("")
            self._starte(BEISPIEL)
        elif befehl == "webseite":
            if self._darf_verwerfen():
                self.datei = None
                self._editor_setzen(BEISPIEL_SEITE)
                self.zeige_ansicht("editor")
                self.status.configure(text="Beispiel-Webseite – drück F5, dann öffnet sie sich im Browser.")
        elif befehl == "version":
            self._schreibe(f"Edgy v{VERSION}", "info")

    # ------------------------------------------------------------ Editor
    def _editor_enter(self, _=None):
        self.geist_editor.weg()
        t = self.editor
        zeile = t.get("insert linestart", "insert lineend")
        vorher = t.get("1.0", "insert linestart")
        tiefe_davor = max(block_tiefe(vorher), 0)
        erstes = zeile.strip().split()[0] if zeile.strip() else ""
        if zeile.strip() in ("ende", "sonst"):
            # ende/sonst automatisch passend einrücken
            alt = len(zeile) - len(zeile.lstrip(" "))
            soll = max(tiefe_davor - 1, 0) * 2
            t.delete("insert linestart", f"insert linestart+{alt}c")
            t.insert("insert linestart", " " * soll)
        tiefe = max(block_tiefe(vorher + zeile), 0)
        einzug = tiefe * 2 if zeile.strip() else len(zeile) - len(zeile.lstrip(" "))
        t.insert("insert", "\n" + " " * einzug)
        t.see("insert")
        self._editor_geaendert()
        return "break"

    def _editor_geaendert(self):
        faerbe(self.editor)
        self._nummern_aktualisieren()

    def _nummern_aktualisieren(self):
        anzahl = int(self.editor.index("end-1c").split(".")[0])
        self.nummern.configure(state="normal")
        self.nummern.delete("1.0", "end")
        self.nummern.insert("1.0", "\n".join(str(i) for i in range(1, anzahl + 1)), "rechts")
        self.nummern.configure(state="disabled")
        self.nummern.yview_moveto(self.editor.yview()[0])

    def _modifiziert(self, _=None):
        self._status()

    def _editor_code(self):
        self.geist_editor.weg()
        return self.editor.get("1.0", "end-1c")

    def _editor_setzen(self, code):
        self.geist_editor.weg()
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", code)
        self.editor.edit_reset()
        self.editor.edit_modified(False)
        self.editor.mark_set("insert", "1.0")
        self._editor_geaendert()
        self._status()

    def _darf_verwerfen(self):
        if not self.editor.edit_modified() or not self._editor_code().strip():
            return True
        antwort = messagebox.askyesnocancel("Edgy", "Die Datei hat ungespeicherte Änderungen.\nVorher speichern?")
        if antwort is None:
            return False
        if antwort:
            return self.speichern()
        return True

    def neu(self):
        if not self._darf_verwerfen():
            return
        self.datei = None
        self._editor_setzen("")
        self.zeige_ansicht("editor")
        self._status()

    def oeffnen(self):
        if not self._darf_verwerfen():
            return
        pfad = filedialog.askopenfilename(
            title="Edgy-Datei öffnen", initialdir=dokumente_ordner(),
            filetypes=[("Edgy-Programme", "*.edgy"), ("Textdateien", "*.txt"), ("Alle Dateien", "*.*")],
        )
        if pfad:
            self._oeffne_pfad(pfad)

    def _oeffne_pfad(self, pfad, starten=False):
        try:
            with open(pfad, encoding="utf-8-sig") as f:
                code = f.read()
        except OSError as e:
            self.zeige_ansicht("konsole")
            self._schreibe(f"✕ Datei konnte nicht geöffnet werden: {e}", "fehler")
            return
        self.datei = os.path.abspath(pfad)
        self._editor_setzen(code)
        self.zeige_ansicht("editor")
        if starten:
            self.starte_editor()

    def speichern(self, unter=False):
        code = self._editor_code()
        pfad = self.datei
        if unter or not pfad:
            pfad = filedialog.asksaveasfilename(
                title="Edgy-Datei speichern", initialdir=dokumente_ordner(),
                initialfile="programm.edgy", defaultextension=".edgy",
                filetypes=[("Edgy-Programme", "*.edgy"), ("Alle Dateien", "*.*")],
            )
            if not pfad:
                return False
        try:
            with open(pfad, "w", encoding="utf-8", newline="\n") as f:
                f.write(code)
        except OSError as e:
            messagebox.showerror("Edgy", f"Speichern hat nicht geklappt:\n{e}")
            return False
        self.datei = os.path.abspath(pfad)
        self.editor.edit_modified(False)
        self._status()
        self.status.configure(text=f"{os.path.basename(pfad)}  ✓ gespeichert")
        self.root.after(2000, self._status)
        return True

    def starte_editor(self):
        if self.laeuft:
            return
        code = self._editor_code()
        if not code.strip():
            self.zeige_ansicht("editor")
            self._editor_setzen(BEISPIEL)
            self.status.configure(text="Der Editor war leer – hier ist ein Beispiel. Drück F5 zum Starten.")
            return
        self.puffer = []
        self.zeige_ansicht("konsole")
        name = os.path.basename(self.datei) if self.datei else "Unbenannt.edgy"
        self._schreibe(f"▶ {name}", "info")
        self._starte(code)

    # ------------------------------------------------------------ Ausführen
    def _starte(self, code):
        self.laeuft = True
        self.status.configure(text="läuft …   Esc = stoppen", fg=GOLD)
        threading.Thread(target=self._lauf, args=(code,), daemon=True).start()

    def _lauf(self, code):
        try:
            self.edgy.starte(code)
        except EdgyFehler as f:
            self.ausgaben.put(("fehler", "✕ " + f.text()))
        except Abbruch:
            self.ausgaben.put(("info", "■ gestoppt"))
        except RecursionError:
            self.ausgaben.put(("fehler", "✕ Das Programm ist zu tief verschachtelt."))
        except Exception as f:  # sollte nie passieren
            self.ausgaben.put(("fehler", f"✕ Interner Fehler: {f}"))
        self.ausgaben.put(("fertig", None))

    def _aus_thread(self, text, farbe=None):
        self.ausgaben.put(("farbig", (text, farbe)) if farbe else ("aus", text))

    def _frage_aus_thread(self, frage):
        self.ausgaben.put(("frage", frage))
        antwort = self.antworten.get()
        if self.edgy.stopp:
            raise Abbruch()
        return antwort

    def _seite_aus_thread(self, html_code, titel):
        if self.datei:
            ordner = os.path.dirname(self.datei)
            name = os.path.splitext(os.path.basename(self.datei))[0]
        else:
            ordner = os.path.join(dokumente_ordner(), "Webseiten")
            name = re.sub(r"[^\wÄÖÜäöüß -]", "", titel).strip() or "seite"
        os.makedirs(ordner, exist_ok=True)
        pfad = os.path.join(ordner, name + ".html")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(html_code)
        webbrowser.open(pathlib.Path(pfad).as_uri())
        self.ausgaben.put(("info", f"🌐 Seite geöffnet: {pfad}"))

    def _stopp(self):
        if self.laeuft:
            self.edgy.stopp = True
            if self.wartet_auf_antwort:
                self.wartet_auf_antwort = False
                self.prompt.configure(text="›", fg=DE_ROT)
                self.antworten.put("")
        elif self.puffer:
            self.puffer = []
            self.prompt.configure(text="›", fg=DE_ROT)
            self._schreibe("■ Eingabe verworfen", "info")

    def _farb_tag(self, farbe):
        tag = "f_" + farbe.lstrip("#")
        if tag not in self._farb_tags:
            self.anzeige.tag_configure(tag, foreground=farbe)
            self._farb_tags.add(tag)
        return tag

    def _verarbeite_ausgaben(self):
        try:
            for _ in range(400):
                art, inhalt = self.ausgaben.get_nowait()
                if art == "fertig":
                    self.laeuft = False
                    self.status.configure(fg=GRAU)
                    self._status()
                elif art == "frage":
                    if self.ansicht != "konsole":
                        self.zeige_ansicht("konsole")
                    if inhalt:
                        self._schreibe(inhalt, "frage")
                    self.wartet_auf_antwort = True
                    self.prompt.configure(text="?", fg=GOLD)
                    self.feld.focus_set()
                elif art == "farbig":
                    text, farbe = inhalt
                    self._schreibe(text, self._farb_tag(farbe))
                elif art == "leeren":
                    self._leeren()
                elif art == "update_start":
                    self.update_bildschirm(inhalt)
                elif art == "update_fortschritt":
                    self.update_fortschritt(inhalt)
                elif art == "update_fertig":
                    self.update_fertig()
                elif art == "update_fehler":
                    self.update_fehler(inhalt)
                elif art == "schliessen":
                    self.root.destroy()
                    return
                else:
                    self._schreibe(inhalt, None if art == "aus" else art)
        except queue.Empty:
            pass
        self.root.after(30, self._verarbeite_ausgaben)

    def _schliessen(self):
        if self._darf_verwerfen():
            self.edgy.stopp = True
            self.antworten.put("")
            self.root.destroy()

    # ------------------------------------------------------------ Update
    def _pruefe_update(self):
        try:
            gefunden = update.suche_update()
        except Exception:
            return
        if not gefunden:
            return
        neu, url, groesse = gefunden
        self.ausgaben.put(("update_start", neu))
        try:
            update.installiere(url, groesse, lambda a: self.ausgaben.put(("update_fortschritt", a)))
        except Exception as f:
            self.ausgaben.put(("update_fehler", str(f)))
            return
        self.ausgaben.put(("update_fertig", None))

    # Update-Bildschirm mit Ladebalken
    BALKEN_BREITE = 340

    def update_bildschirm(self, neu):
        self.geist_konsole.weg()
        o = tk.Frame(self.root, bg=HINTERGRUND)
        o.place(x=0, y=0, relwidth=1, relheight=1)
        o.lift()
        self._update_ebene = o
        mitte = tk.Frame(o, bg=HINTERGRUND)
        mitte.place(relx=0.5, rely=0.46, anchor="center")
        try:
            self._update_logo = tk.PhotoImage(file=ressource("update_logo.png"))
            tk.Label(mitte, image=self._update_logo, bg=HINTERGRUND).pack(pady=(0, 26))
        except Exception:
            pass
        self._u_titel = tk.Label(mitte, text=f"Update auf {neu}", font=("Segoe UI Semibold", 17),
                                 fg=TEXT, bg=HINTERGRUND)
        self._u_titel.pack()
        self._u_text = tk.Label(mitte, text="Die neue Version wird geladen …", font=("Segoe UI", 10),
                                fg=HELLGRAU, bg=HINTERGRUND)
        self._u_text.pack(pady=(6, 26))
        self._u_balken = tk.Canvas(mitte, width=self.BALKEN_BREITE, height=4, bg=LINIE,
                                   highlightthickness=0, bd=0)
        self._u_balken.pack()
        self._u_prozent = tk.Label(mitte, text="0 %", font=("Segoe UI", 9), fg=GRAU, bg=HINTERGRUND)
        self._u_prozent.pack(pady=(10, 0))
        self._u_ziel = 0.0
        self._u_wert = 0.0
        self._u_fertig = False
        self._update_animation()

    def update_fortschritt(self, anteil):
        self._u_ziel = max(self._u_ziel, min(float(anteil), 1.0))

    def update_fertig(self):
        self._u_ziel = 1.0
        self._u_fertig = True

    def _update_animation(self):
        if not getattr(self, "_update_ebene", None):
            return
        self._u_wert += (self._u_ziel - self._u_wert) * 0.18
        if self._u_ziel - self._u_wert < 0.002:
            self._u_wert = self._u_ziel
        breite = int(self.BALKEN_BREITE * self._u_wert)
        self._u_balken.delete("all")
        if breite > 0:
            self._u_balken.create_rectangle(0, 0, breite, 4, fill=GOLD, width=0)
        self._u_prozent.configure(text=f"{int(self._u_wert * 100)} %")
        if self._u_fertig and self._u_wert >= 1.0:
            self._u_titel.configure(text="Programm wird neu gestartet …")
            self._u_text.configure(text="Gleich geht's weiter.")
            self._u_fertig = False
            if not getattr(self, "_nur_test", False):
                self.root.after(1400, self.root.destroy)
            return
        self.root.after(16, self._update_animation)

    def update_fehler(self, meldung):
        if not getattr(self, "_update_ebene", None):
            return
        self._u_titel.configure(text="Update hat nicht geklappt", fg=ROT)
        self._u_text.configure(text=meldung[:120])
        self.root.after(3500, self.update_weg)

    def update_weg(self):
        ebene = getattr(self, "_update_ebene", None)
        if ebene:
            ebene.destroy()
            self._update_ebene = None

    def start(self):
        self.root.mainloop()
