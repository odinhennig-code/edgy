"""Edgy – die Entwicklungsumgebung: Explorer, Tabs, Editor, Konsole."""

import json
import os
import pathlib
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk, font as tkfont

from . import update
from .sprache import (
    FUNKTIONEN, SCHLUESSELWOERTER, Abbruch, Edgy, EdgyFehler,
    block_tiefe, braucht_mehr_zeilen, vorschlag,
)
from .version import VERSION

# ---------------------------------------------------------------- Farben
HINTERGRUND = "#0c0c0d"     # Editor
SEITE = "#0f0f11"           # Seitenleiste, inaktive Tabs
LEISTE = "#08080a"          # Aktivitätsleiste, Statusleiste
LINIE = "#1f1f22"
HOVER = "#18181c"
AUSWAHL_BAUM = "#1e1e24"
TEXT = "#ececec"
GRAU = "#5f5f66"
HELLGRAU = "#8d8d94"
GEIST = "#4a4a50"
ROT = "#ff3b3b"
GOLD = "#ffce00"
DE_ROT = "#dd0000"
AUSWAHL = "#2a2a30"

SYNTAX = {"kw": "#ff5c5c", "fn": "#ff9f5a", "str": "#ffce00", "num": "#9ad0ff", "kom": "#55555c"}

FENSTER_BEFEHLE = ["hilfe", "beispiel", "webseite", "editor", "öffne", "leeren", "version", "beenden"]
IGNORIEREN = {"__pycache__", "node_modules", ".git", "$RECYCLE.BIN", "desktop.ini"}
UMBAU_SCHLUESSEL = "umbau_animation_0_3"

HILFE = """\
AUSGABE & EINGABE
  gib aus "Hallo"              Text anzeigen
  merk name = "Max"            etwas speichern
  frag alter "Wie alt?"        den Nutzer etwas fragen
  farbe "rot"                  Ausgabe einfärben ("normal" = zurück)
  leere                        Konsole leeren
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

TASTEN
  Tab        Vorschlag übernehmen        F5         Datei starten
  Strg+N     neue Datei                  Strg+S     speichern
  Strg+O     Datei öffnen                Strg+W     Tab schließen
  Strg+B     Explorer ein/aus            Strg+J     Konsole ein/aus
  Strg+Tab   nächster Tab                Esc        Programm stoppen
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


# ---------------------------------------------------------------- Hilfsfunktionen
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


def einstellungen_pfad():
    eigener = os.environ.get("EDGY_EINSTELLUNGEN")
    if eigener:
        return eigener
    basis = os.environ.get("APPDATA") or os.path.expanduser("~")
    ordner = os.path.join(basis, "Edgy")
    os.makedirs(ordner, exist_ok=True)
    return os.path.join(ordner, "einstellungen.json")


def lade_einstellungen():
    try:
        with open(einstellungen_pfad(), encoding="utf-8") as f:
            daten = json.load(f)
            return daten if isinstance(daten, dict) else {}
    except (OSError, ValueError):
        return {}


def speichere_einstellungen(daten):
    try:
        with open(einstellungen_pfad(), "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def in_papierkorb(pfad):
    """Verschiebt eine Datei/einen Ordner in den Windows-Papierkorb."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        op = SHFILEOPSTRUCTW(None, 3, os.path.abspath(pfad) + "\0", None,
                             0x40 | 0x10 | 0x04 | 0x400, False, None, None)
        return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not os.path.exists(pfad)
    except Exception:
        return False


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


def mische(farbe1, farbe2, t):
    a = [int(farbe1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(farbe2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def weich(t):
    """Ease-out: schnell los, sanft ankommen."""
    return 1 - (1 - t) ** 3


def weich_rein_raus(t):
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


class Animator:
    """Kleine Animations-Maschine: bewegt Zahlen über die Zeit."""

    def __init__(self, root):
        self.root = root

    def los(self, dauer_ms, von, bis, setze, nach_ms=0, fertig=None, kurve=weich):
        zustand = {"start": None}

        def schritt():
            try:
                jetzt = time.perf_counter()
                if zustand["start"] is None:
                    zustand["start"] = jetzt
                t = min((jetzt - zustand["start"]) / max(dauer_ms / 1000, 0.001), 1.0)
                setze(von + (bis - von) * kurve(t))
                if t < 1:
                    self.root.after(10, schritt)
                elif fertig:
                    fertig()
            except tk.TclError:
                pass

        self.root.after(int(nach_ms), schritt)

    def spaeter(self, nach_ms, befehl):
        self.root.after(int(nach_ms), befehl)


class Icons:
    """Lädt die Icons8-Icons in der passenden Größe für den Bildschirm."""

    def __init__(self, skala):
        self.stufe = min((100, 125, 150, 200), key=lambda s: abs(s / 100 - skala))
        self.cache = {}

    def __call__(self, name):
        if name not in self.cache:
            try:
                self.cache[name] = tk.PhotoImage(file=ressource(os.path.join("icons", f"{name}@{self.stufe}.png")))
            except tk.TclError:
                self.cache[name] = ""
        return self.cache[name]


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

    MODIFIKATOREN = ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Caps_Lock")

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
        if e.keysym in self.MODIFIKATOREN + ("Tab", "Right", "End"):
            return None
        self.weg()
        return None

    def _losgelassen(self, e):
        if e.keysym in self.MODIFIKATOREN + ("Tab", "Escape", "Up", "Down", "Return", "KP_Enter"):
            return
        if e.state & 0x4:
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
    """Schmale, unauffällige Scrollleiste."""

    def __init__(self, eltern, ziel, bg=HINTERGRUND):
        super().__init__(eltern, width=7, bg=bg, highlightthickness=0, bd=0, cursor="arrow")
        self.ziel = ziel
        self.anfang, self.ende = 0.0, 1.0
        self.ueber = False
        self.bind("<Configure>", lambda e: self._zeichne())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonPress-1>", self._klick)
        self.bind("<B1-Motion>", self._ziehen)
        self.bind("<MouseWheel>", lambda e: self.ziel and self.ziel.yview_scroll(int(-e.delta / 120) * 3, "units"))

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
        self.create_rectangle(1, y0, 6, y1, fill="#4a4a50" if self.ueber else "#2c2c31", width=0)

    def _klick(self, e):
        self._start_y = e.y
        self._start_anfang = self.anfang
        h = max(self.winfo_height(), 1)
        if self.ziel is None:
            return
        if not self.anfang * h <= e.y <= self.ende * h:
            self.ziel.yview_moveto(max(e.y / h - (self.ende - self.anfang) / 2, 0))
            self._start_anfang = float(self.ziel.yview()[0])

    def _ziehen(self, e):
        h = max(self.winfo_height(), 1)
        if self.ziel is None:
            return
        self.ziel.yview_moveto(self._start_anfang + (e.y - self._start_y) / h)


# ---------------------------------------------------------------- Tabs
class Tab:
    def __init__(self, ide, pfad, inhalt):
        self.ide = ide
        self.pfad = pfad
        self.ist_edgy = pfad is None or pfad.lower().endswith(".edgy")
        t = self.text = ide._textfeld(ide.editor_innen, wrap="none")
        t.insert("1.0", inhalt)
        t.edit_reset()
        t.edit_modified(False)
        t.mark_set("insert", "1.0")
        t.configure(yscrollcommand=lambda *a: ide._editor_scroll(self, *a))
        t.bind("<Return>", lambda e: ide._editor_enter(self))
        t.bind("<KP_Enter>", lambda e: ide._editor_enter(self))
        t.bind("<KeyRelease>", lambda e: ide._editor_geaendert(self), add="+")
        t.bind("<ButtonRelease-1>", lambda e: ide._cursor_anzeigen(), add="+")
        t.bind("<<Paste>>", lambda e: ide.root.after(1, lambda: ide._editor_geaendert(self)), add="+")
        t.bind("<<Vorschlag>>", lambda e: ide._editor_geaendert(self), add="+")
        t.bind("<<Modified>>", lambda e: ide._tab_aktualisieren(self))
        if self.ist_edgy:
            self.geist = Geist(t, ide._bekannte_namen, tab_ohne=lambda: t.insert("insert", "  "))
            faerbe(t)
        else:
            self.geist = None
            t.bind("<Tab>", lambda e: (t.insert("insert", "  "), "break")[1])
        ide._tastenkuerzel_fuer(t)

        # Reiter in der Tab-Leiste
        self.reiter = tk.Frame(ide.tableiste, bg=SEITE, cursor="hand2")
        self.oben = tk.Frame(self.reiter, height=2, bg=SEITE)
        self.oben.pack(fill="x", side="top")
        innen = tk.Frame(self.reiter, bg=SEITE)
        innen.pack(fill="both", expand=True, padx=(ide.px(12), ide.px(6)))
        symbol = "baum_edgy" if self.ist_edgy else ("baum_web" if self._ist_web() else "baum_datei")
        self.symbol = tk.Label(innen, image=ide.icons(symbol), bg=SEITE, width=ide.px(18), anchor="e")
        self.symbol.pack(side="left")
        self.name_label = tk.Label(innen, text=self.name, font=ide.ui_schrift, fg=HELLGRAU, bg=SEITE)
        self.name_label.pack(side="left", padx=(ide.px(4), ide.px(8)))
        self.zu = tk.Label(innen, image=ide.icons("schliessen_klein"), bg=SEITE, cursor="hand2")
        self.zu.pack(side="left")
        for w in (self.reiter, innen, self.symbol, self.name_label):
            w.bind("<Button-1>", lambda e: ide.tab_aktivieren(self))
            w.bind("<Button-2>", lambda e: ide.tab_schliessen(self))
        self.zu.bind("<Button-1>", lambda e: ide.tab_schliessen(self))
        self.reiter.pack(side="left", fill="y")
        tk.Frame(ide.tableiste, width=1, bg=LINIE).pack(side="left", fill="y", in_=ide.tableiste, after=self.reiter)

    def _ist_web(self):
        return bool(self.pfad) and self.pfad.lower().endswith((".html", ".htm"))

    @property
    def name(self):
        return os.path.basename(self.pfad) if self.pfad else "Unbenannt.edgy"

    @property
    def geaendert(self):
        return bool(self.text.edit_modified())

    def inhalt(self):
        if self.geist:
            self.geist.weg()
        return self.text.get("1.0", "end-1c")

    def faerben(self, aktiv):
        bg = HINTERGRUND if aktiv else SEITE
        for w in (self.reiter, self.symbol, self.name_label, self.zu, self.name_label.master):
            w.configure(bg=bg)
        self.oben.configure(bg=DE_ROT if aktiv else bg)
        self.name_label.configure(fg=TEXT if aktiv else HELLGRAU, text=self.name)
        self.zu.configure(image=self.ide.icons("schliessen_weiss" if self.geaendert else "schliessen_klein"),
                          text="")
        if self.geaendert:
            self.zu.configure(image="", text="●", fg=TEXT if aktiv else HELLGRAU, font=self.ide.ui_schrift_klein)
        else:
            self.zu.configure(image=self.ide.icons("schliessen_klein"), text="")

    def entfernen(self):
        self.reiter.destroy()
        self.text.destroy()


# ---------------------------------------------------------------- Fenster
class EdgyFenster:
    def __init__(self, start_datei=None, umbau=None):
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Edgy.Programmiersprache")
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Edgy")
        self.root.configure(bg=HINTERGRUND)
        try:
            self.root.iconbitmap(default=ressource("edgy.ico"))
        except Exception:
            pass

        self.skala = max(self.root.winfo_fpixels("1i") / 96, 1.0)
        self.icons = Icons(self.skala)
        self.animator = Animator(self.root)
        self.einstellungen = lade_einstellungen()

        familien = set(tkfont.families())
        code_font = next((f for f in ("Cascadia Mono", "Consolas", "DejaVu Sans Mono") if f in familien), "Courier")
        ui_font = "Segoe UI" if "Segoe UI" in familien else "TkDefaultFont"
        self.schrift = tkfont.Font(family=code_font, size=12)
        self.schrift_fett = tkfont.Font(family=code_font, size=12, weight="bold")
        self.schrift_klein = tkfont.Font(family=code_font, size=10)
        self.ui_schrift = tkfont.Font(family=ui_font, size=10)
        self.ui_schrift_klein = tkfont.Font(family=ui_font, size=9)
        self.ui_schrift_fett = tkfont.Font(family=ui_font, size=9, weight="bold")

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
        self.tabs = []
        self.aktiv = None
        self.lauf_datei = None
        self._farb_tags = set()
        self.seitenleiste_an = True
        self.panel_an = True
        self.panel_hoehe = self.px(240)
        self.seiten_breite = self.px(250)

        self.arbeitsordner = self.einstellungen.get("arbeitsordner")
        if not self.arbeitsordner or not os.path.isdir(self.arbeitsordner):
            self.arbeitsordner = dokumente_ordner()
        self._beispiele_anlegen()

        self._stil()
        self._baue_alles()
        self._tastenkuerzel()

        if umbau is None:
            umbau = not self.einstellungen.get(UMBAU_SCHLUESSEL)
        self.root.protocol("WM_DELETE_WINDOW", self._schliessen)
        self.root.after(30, self._verarbeite_ausgaben)

        if umbau:
            self._umbau_vorbereiten()
        else:
            self._normal_starten()
            for pfad in self.einstellungen.get("offene_dateien", []):
                if os.path.isfile(pfad):
                    self.datei_oeffnen(pfad)

        if update.ist_exe():
            threading.Thread(target=self._pruefe_update, daemon=True).start()
        if start_datei:
            self.root.after(300, lambda: (self.datei_oeffnen(start_datei), self.starten()))

    def px(self, n):
        return int(round(n * self.skala))

    # ============================================================ Aufbau
    def _stil(self):
        stil = ttk.Style(self.root)
        try:
            stil.theme_use("clam")
        except tk.TclError:
            pass
        stil.configure("Edgy.Treeview", background=SEITE, fieldbackground=SEITE, foreground=HELLGRAU,
                       borderwidth=0, relief="flat", rowheight=self.px(24), font=self.ui_schrift,
                       indent=self.px(12))
        stil.map("Edgy.Treeview", background=[("selected", AUSWAHL_BAUM)], foreground=[("selected", TEXT)])
        stil.layout("Edgy.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        stil.layout("Edgy.Treeview.Item", [("Treeitem.padding", {"sticky": "nswe", "children": [
            ("Treeitem.image", {"side": "left", "sticky": ""}),
            ("Treeitem.text", {"side": "left", "sticky": ""}),
        ]})])

    def _baue_alles(self):
        # Ganz oben die Flagge
        streifen = tk.Frame(self.root, height=3, bg=HINTERGRUND)
        streifen.pack(fill="x", side="top")
        for farbe in ("#1b1b1b", DE_ROT, GOLD):
            tk.Frame(streifen, height=3, bg=farbe).pack(side="left", fill="both", expand=True)

        self._baue_kopf()

        # Statusleiste unten
        self.statusleiste = tk.Frame(self.root, bg=LEISTE, height=self.px(26))
        self.statusleiste.pack(fill="x", side="bottom")
        self.statusleiste.pack_propagate(False)
        tk.Frame(self.statusleiste, height=1, bg=LINIE).pack(fill="x", side="top")
        self.status_links = tk.Label(self.statusleiste, text="● bereit", font=self.ui_schrift_klein,
                                     fg=HELLGRAU, bg=LEISTE)
        self.status_links.pack(side="left", padx=self.px(12))
        self.status_rechts = tk.Label(self.statusleiste, text=f"Edgy v{VERSION}", font=self.ui_schrift_klein,
                                      fg=GRAU, bg=LEISTE)
        self.status_rechts.pack(side="right", padx=self.px(12))
        self.status_cursor = tk.Label(self.statusleiste, text="", font=self.ui_schrift_klein, fg=GRAU, bg=LEISTE)
        self.status_cursor.pack(side="right", padx=self.px(8))

        haupt = tk.Frame(self.root, bg=HINTERGRUND)
        haupt.pack(fill="both", expand=True)
        self._baue_aktivitaetsleiste(haupt)
        self._baue_seitenleiste(haupt)
        self._baue_spalte(haupt)

    def _baue_kopf(self):
        kopf = tk.Frame(self.root, bg=LEISTE, height=self.px(42))
        kopf.pack(fill="x", side="top")
        kopf.pack_propagate(False)
        tk.Frame(kopf, height=1, bg=LINIE).pack(fill="x", side="bottom")
        links = tk.Frame(kopf, bg=LEISTE)
        links.pack(side="left", padx=(self.px(12), 0))
        tk.Label(links, image=self.icons("logo"), bg=LEISTE).pack(side="left", padx=(0, self.px(9)))
        tk.Label(links, text="Edgy", font=(self.ui_schrift.actual("family"), 13, "bold"), fg=TEXT,
                 bg=LEISTE).pack(side="left")
        tk.Label(links, text=f"v{VERSION}", font=self.ui_schrift_klein, fg=GRAU,
                 bg=LEISTE).pack(side="left", padx=(self.px(7), 0), pady=(self.px(3), 0))
        self.kopf_titel = tk.Label(kopf, text="", font=self.ui_schrift, fg=HELLGRAU, bg=LEISTE)
        self.kopf_titel.place(relx=0.5, rely=0.5, anchor="center")

        self.start_knopf = tk.Frame(kopf, bg=LEISTE, cursor="hand2")
        self.start_knopf.pack(side="right", padx=self.px(12))
        a = tk.Label(self.start_knopf, image=self.icons("play_rot"), bg=LEISTE)
        a.pack(side="left", padx=(self.px(8), self.px(5)), pady=self.px(4))
        b = tk.Label(self.start_knopf, text="Starten", font=self.ui_schrift_fett, fg=DE_ROT, bg=LEISTE)
        b.pack(side="left", padx=(0, self.px(10)))
        for w in (self.start_knopf, a, b):
            w.bind("<Button-1>", lambda e: self.starten())
            w.bind("<Enter>", lambda e: [x.configure(bg=HOVER) for x in (self.start_knopf, a, b)])
            w.bind("<Leave>", lambda e: [x.configure(bg=LEISTE) for x in (self.start_knopf, a, b)])

    def _icon_knopf(self, eltern, icon, befehl, tipp, bg, hover_icon=None):
        l = tk.Label(eltern, image=self.icons(icon), bg=bg, cursor="hand2", padx=self.px(4), pady=self.px(3))
        l.bind("<Button-1>", lambda e: befehl())
        l.bind("<Enter>", lambda e: (l.configure(bg=HOVER, image=self.icons(hover_icon or icon)),
                                     self._status(tipp, temp=True)))
        l.bind("<Leave>", lambda e: (l.configure(bg=bg, image=self.icons(icon)), self._status()))
        return l

    def _baue_aktivitaetsleiste(self, eltern):
        self.aktivitaet = tk.Frame(eltern, bg=LEISTE, width=self.px(48))
        self.aktivitaet.pack(side="left", fill="y")
        self.aktivitaet.pack_propagate(False)
        tk.Frame(self.aktivitaet, width=1, bg=LINIE).place(relx=1, x=-1, y=0, relheight=1)
        self.aktiv_icons = []
        eintraege = [
            ("explorer", "Explorer (Strg+B)", self.seitenleiste_umschalten),
            ("konsole", "Konsole (Strg+J)", self.panel_umschalten),
            ("web", "Beispiel-Webseite", lambda: self._fensterbefehl("webseite")),
            ("hilfe", "Alle Befehle", lambda: self._fensterbefehl("hilfe")),
        ]
        for i, (icon, tipp, befehl) in enumerate(eintraege):
            rahmen = tk.Frame(self.aktivitaet, bg=LEISTE, width=self.px(47), height=self.px(46), cursor="hand2")
            rahmen.place(x=0, y=self.px(6) + i * self.px(48))
            marke = tk.Frame(rahmen, bg=LEISTE, width=self.px(2))
            marke.place(x=0, y=self.px(8), relheight=0.65)
            l = tk.Label(rahmen, image=self.icons(icon), bg=LEISTE)
            l.place(relx=0.5, rely=0.5, anchor="center")
            for w in (rahmen, l):
                w.bind("<Button-1>", lambda e, b=befehl: b())
                w.bind("<Enter>", lambda e, l=l, icon=icon, tipp=tipp: (l.configure(image=self.icons(icon + "_hell")),
                                                                          self._status(tipp, temp=True)))
                w.bind("<Leave>", lambda e, l=l, icon=icon: (self._aktiv_icons_faerben(), self._status()))
            self.aktiv_icons.append({"rahmen": rahmen, "label": l, "marke": marke, "icon": icon,
                                     "y": self.px(6) + i * self.px(48)})

    def _aktiv_icons_faerben(self):
        an = {"explorer": self.seitenleiste_an, "konsole": self.panel_an}
        for e in self.aktiv_icons:
            ist_an = an.get(e["icon"], False)
            e["label"].configure(image=self.icons(e["icon"] + ("_hell" if ist_an else "")))
            e["marke"].configure(bg=DE_ROT if ist_an else LEISTE)

    def _baue_seitenleiste(self, eltern):
        self.seitenleiste = tk.Frame(eltern, bg=SEITE, width=self.seiten_breite)
        self.seitenleiste.pack(side="left", fill="y")
        self.seitenleiste.pack_propagate(False)

        kopf = tk.Frame(self.seitenleiste, bg=SEITE, height=self.px(36))
        kopf.pack(fill="x")
        kopf.pack_propagate(False)
        tk.Label(kopf, text="EXPLORER", font=self.ui_schrift_fett, fg=GRAU, bg=SEITE).pack(side="left", padx=self.px(14))
        knoepfe = tk.Frame(kopf, bg=SEITE)
        knoepfe.pack(side="right", padx=self.px(6))
        for icon, tipp, befehl in (
            ("ordner_klein", "Ordner öffnen", self.ordner_waehlen),
            ("aktualisieren_klein", "Aktualisieren", self.baum_laden),
            ("neuer_ordner_klein", "Neuer Ordner", lambda: self.neuer_ordner_dialog()),
            ("neue_datei_klein", "Neue Datei", lambda: self.neue_datei_dialog()),
        ):
            self._icon_knopf(knoepfe, icon, befehl, tipp, SEITE, icon.replace("_klein", "_weiss")).pack(side="right")

        self.ordner_titel = tk.Label(self.seitenleiste, text="", font=self.ui_schrift_fett, fg=HELLGRAU,
                                     bg=SEITE, anchor="w", cursor="hand2")
        self.ordner_titel.pack(fill="x", padx=self.px(14), pady=(0, self.px(4)))
        self.ordner_titel.bind("<Button-3>", lambda e: self._kontextmenue(e, self.arbeitsordner))

        rahmen = tk.Frame(self.seitenleiste, bg=SEITE)
        rahmen.pack(fill="both", expand=True)
        self.baum = ttk.Treeview(rahmen, style="Edgy.Treeview", show="tree", selectmode="browse")
        leiste = DuenneLeiste(rahmen, self.baum, bg=SEITE)
        self.baum.configure(yscrollcommand=leiste.set)
        leiste.pack(side="right", fill="y")
        self.baum.pack(side="left", fill="both", expand=True, padx=(self.px(4), 0))
        self.baum.bind("<ButtonRelease-1>", self._baum_klick)
        self.baum.bind("<Button-3>", self._baum_rechtsklick)
        self.baum.bind("<Return>", self._baum_klick)
        self.baum.bind("<Double-Button-1>", lambda e: "break")
        self.baum.bind("<<TreeviewOpen>>", lambda e: self._ordner_icons())
        self.baum.bind("<<TreeviewClose>>", lambda e: self._ordner_icons())
        self.baum.tag_configure("versteckt", foreground=GRAU)

        self.seiten_trenner = tk.Frame(eltern, bg=LINIE, width=1, cursor="sb_h_double_arrow")
        self.seiten_trenner.pack(side="left", fill="y")
        self.seiten_trenner.bind("<B1-Motion>", self._seite_ziehen)

    def _baue_spalte(self, eltern):
        self.spalte = tk.Frame(eltern, bg=HINTERGRUND)
        self.spalte.pack(side="left", fill="both", expand=True)

        # Tab-Leiste
        self.tableiste_rahmen = tk.Frame(self.spalte, bg=SEITE, height=self.px(36))
        self.tableiste_rahmen.pack(fill="x", side="top")
        self.tableiste_rahmen.pack_propagate(False)
        self.tableiste = tk.Frame(self.tableiste_rahmen, bg=SEITE)
        self.tableiste.pack(fill="both", expand=True)

        # Konsole unten
        self.panel = tk.Frame(self.spalte, bg=HINTERGRUND, height=self.panel_hoehe)
        self.panel.pack(fill="x", side="bottom")
        self.panel.pack_propagate(False)
        self.panel_trenner = tk.Frame(self.spalte, bg=LINIE, height=1, cursor="sb_v_double_arrow")
        self.panel_trenner.pack(fill="x", side="bottom")
        self.panel_trenner.bind("<B1-Motion>", self._panel_ziehen)
        self._baue_konsole(self.panel)

        # Editor-Fläche
        self.editor_flaeche = tk.Frame(self.spalte, bg=HINTERGRUND)
        self.editor_flaeche.pack(fill="both", expand=True)
        self.editor_rahmen = tk.Frame(self.editor_flaeche, bg=HINTERGRUND)
        self.nummern = tk.Text(self.editor_rahmen, width=4, bg=HINTERGRUND, fg=GEIST, font=self.schrift, bd=0,
                               highlightthickness=0, padx=0, pady=self.px(6), spacing1=2, spacing3=2,
                               state="disabled", cursor="arrow", takefocus=0)
        self.nummern.tag_configure("rechts", justify="right")
        self.nummern.tag_configure("aktuell", foreground=HELLGRAU)
        self.nummern.bind("<MouseWheel>", lambda e: "break")
        self.nummern.pack(side="left", fill="y", padx=(self.px(10), self.px(16)))
        self.editor_leiste = DuenneLeiste(self.editor_rahmen, None)
        self.editor_leiste.pack(side="right", fill="y")
        self.editor_innen = tk.Frame(self.editor_rahmen, bg=HINTERGRUND)
        self.editor_innen.pack(side="left", fill="both", expand=True)
        self._baue_willkommen()

    def _baue_willkommen(self):
        w = self.willkommen = tk.Frame(self.editor_flaeche, bg=HINTERGRUND)
        mitte = tk.Frame(w, bg=HINTERGRUND)
        mitte.place(relx=0.5, rely=0.44, anchor="center")
        self.willkommen_teile = []
        logo = tk.Label(mitte, image=self.icons("logo_gross"), bg=HINTERGRUND)
        logo.pack(pady=(0, self.px(18)))
        titel = tk.Label(mitte, text="Edgy", font=(self.ui_schrift.actual("family"), 26, "bold"),
                         fg=TEXT, bg=HINTERGRUND)
        titel.pack()
        unter = tk.Label(mitte, text="Deine eigene Programmiersprache", font=self.ui_schrift,
                         fg=HELLGRAU, bg=HINTERGRUND)
        unter.pack(pady=(self.px(2), self.px(26)))
        self.willkommen_teile += [(titel, TEXT), (unter, HELLGRAU)]
        for icon, text, taste, befehl in (
            ("neue_datei_klein", "Neue Datei", "Strg+N", self.neue_datei),
            ("ordner_klein", "Datei öffnen", "Strg+O", self.datei_oeffnen_dialog),
            ("explorer_klein", "Ordner öffnen", "", self.ordner_waehlen),
            ("play_klein", "Beispiel ansehen", "", lambda: self._fensterbefehl("beispiel_datei")),
            ("web_klein", "Webseite bauen", "", lambda: self._fensterbefehl("webseite")),
            ("hilfe_klein", "Alle Befehle", "", lambda: self._fensterbefehl("hilfe")),
        ):
            zeile = tk.Frame(mitte, bg=HINTERGRUND, cursor="hand2")
            zeile.pack(fill="x", pady=self.px(3))
            i = tk.Label(zeile, image=self.icons(icon), bg=HINTERGRUND)
            i.pack(side="left", padx=(0, self.px(10)))
            t = tk.Label(zeile, text=text, font=self.ui_schrift, fg="#d24545", bg=HINTERGRUND)
            t.pack(side="left")
            k = tk.Label(zeile, text=taste, font=self.ui_schrift_klein, fg=GRAU, bg=HINTERGRUND)
            k.pack(side="right", padx=(self.px(40), 0))
            for x in (zeile, i, t, k):
                x.bind("<Button-1>", lambda e, b=befehl: b())
                x.bind("<Enter>", lambda e, t=t: t.configure(fg=ROT))
                x.bind("<Leave>", lambda e, t=t: t.configure(fg="#d24545"))
            self.willkommen_teile += [(t, "#d24545"), (k, GRAU)]

    def _baue_konsole(self, eltern):
        kopf = tk.Frame(eltern, bg=HINTERGRUND, height=self.px(32))
        kopf.pack(fill="x", side="top")
        kopf.pack_propagate(False)
        reiter = tk.Frame(kopf, bg=HINTERGRUND)
        reiter.pack(side="left", padx=(self.px(16), 0), fill="y")
        tk.Label(reiter, text="KONSOLE", font=self.ui_schrift_fett, fg=TEXT, bg=HINTERGRUND).pack(side="top", pady=(self.px(8), 0))
        tk.Frame(reiter, height=1, bg=DE_ROT).pack(side="bottom", fill="x")
        knoepfe = tk.Frame(kopf, bg=HINTERGRUND)
        knoepfe.pack(side="right", padx=self.px(10))
        self._icon_knopf(knoepfe, "schliessen_klein", self.panel_umschalten, "Konsole ausblenden",
                         HINTERGRUND, "schliessen_weiss").pack(side="right")
        self._icon_knopf(knoepfe, "aktualisieren_klein", self._leeren, "Konsole leeren",
                         HINTERGRUND, "aktualisieren_weiss").pack(side="right")

        unten = tk.Frame(eltern, bg=HINTERGRUND)
        unten.pack(fill="x", side="bottom", padx=self.px(16), pady=(0, self.px(10)))
        tk.Frame(unten, height=1, bg=LINIE).pack(fill="x", pady=(0, self.px(8)))
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

        rahmen = tk.Frame(eltern, bg=HINTERGRUND)
        rahmen.pack(fill="both", expand=True, padx=(self.px(16), self.px(8)), pady=(self.px(4), self.px(4)))
        self.anzeige = self._textfeld(rahmen, cursor="arrow")
        leiste = DuenneLeiste(rahmen, self.anzeige)
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

    def _textfeld(self, eltern, **extra):
        optionen = dict(
            height=1, width=1, bg=HINTERGRUND, fg=TEXT, font=self.schrift, bd=0,
            highlightthickness=0, wrap="word", insertbackground=GOLD, insertwidth=2,
            selectbackground=AUSWAHL, selectforeground=TEXT, padx=0, pady=self.px(6),
            spacing1=2, spacing3=2, undo=True, maxundo=-1,
        )
        optionen.update(extra)
        t = tk.Text(eltern, **optionen)
        for tag, farbe in SYNTAX.items():
            t.tag_configure(tag, foreground=farbe)
        t.tag_configure("geist", foreground=GEIST)
        return t

    # ============================================================ Tastenkürzel
    def _kuerzel(self):
        return {
            "<Control-s>": lambda: self.speichern(), "<Control-S>": lambda: self.speichern(unter=True),
            "<Control-o>": self.datei_oeffnen_dialog, "<Control-O>": self.datei_oeffnen_dialog,
            "<Control-n>": self.neue_datei, "<Control-N>": self.neue_datei,
            "<Control-w>": lambda: self.aktiv and self.tab_schliessen(self.aktiv),
            "<Control-b>": self.seitenleiste_umschalten, "<Control-j>": self.panel_umschalten,
            "<Control-Tab>": self.naechster_tab,
            "<F5>": self.starten,
            "<Control-l>": self._leeren,
        }

    def _tastenkuerzel_fuer(self, widget):
        for taste, befehl in self._kuerzel().items():
            widget.bind(taste, lambda e, b=befehl: (b(), "break")[1])

    def _tastenkuerzel(self):
        for w in (self.root, self.feld, self.anzeige):
            self._tastenkuerzel_fuer(w)
        self.root.bind("<Escape>", lambda e: self._stopp())

    # ============================================================ Start & Umbau-Animation
    def _zielgroesse(self):
        bw, bh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w = min(self.px(1320), int(bw * 0.88))
        h = min(self.px(820), int(bh * 0.85))
        return w, h, (bw - w) // 2, max((bh - h) // 2 - self.px(20), 0)

    def _normal_starten(self):
        w, h, x, y = self._zielgroesse()
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(self.px(720), self.px(460))
        self.baum_laden()
        self._editor_anzeigen()
        self._aktiv_icons_faerben()
        self.root.deiconify()
        _windows_feinschliff(self.root)
        self._begruessung()
        self._status()
        self.root.after(150, self._fokus_holen)

    def _umbau_vorbereiten(self):
        """Startzustand: sieht aus wie das alte kleine Edgy (nur Konsole)."""
        bw, bh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = self.px(1000), self.px(640)
        self.root.geometry(f"{w}x{h}+{(bw - w) // 2}+{max((bh - h) // 2 - self.px(20), 0)}")
        self.aktivitaet.configure(width=0)
        self.seitenleiste.configure(width=0)
        self.seiten_trenner.pack_forget()
        self.tableiste_rahmen.configure(height=0)
        self.statusleiste.configure(height=0)
        for e in self.aktiv_icons:
            e["rahmen"].place_configure(x=-self.px(50))
        for teil, _ in self.willkommen_teile:
            teil.configure(fg=HINTERGRUND)
        self._editor_anzeigen()
        self.root.deiconify()
        _windows_feinschliff(self.root)
        self.root.update_idletasks()
        self.panel.configure(height=max(self.spalte.winfo_height(), self.px(500)))
        self.root.update()
        self.root.after(250, self._umbau_abspielen)

    def _tippe(self, text, tag, nach_ms, tempo=14):
        """Schreibt Text Buchstabe für Buchstabe in die Konsole."""
        def start():
            self.anzeige.configure(state="normal")
            self.anzeige.insert("end", "", tag)
            self.anzeige.configure(state="disabled")
            for i, z in enumerate(text + "\n"):
                self.root.after(i * tempo, lambda z=z: self._zeichen_anhaengen(z, tag))
        self.root.after(int(nach_ms), start)

    def _zeichen_anhaengen(self, z, tag):
        self.anzeige.configure(state="normal")
        self.anzeige.insert("end", z, tag)
        self.anzeige.configure(state="disabled")
        self.anzeige.see("end")

    def _umbau_abspielen(self):
        a = self.animator
        self._tippe("› Update installiert.", "ein", 0)
        self._tippe("› Edgy wird zu einer richtigen Entwicklungsumgebung umgebaut …", "info", 450)

        # 1) Fenster wächst
        start_geo = (self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y())
        ziel = self._zielgroesse()

        def geo(t):
            w, h, x, y = (int(s + (z - s) * t) for s, z in zip(start_geo, ziel))
            self.root.geometry(f"{w}x{h}+{x}+{y}")
        a.los(750, 0, 1, geo, nach_ms=1500, kurve=weich_rein_raus)

        # 2) Aktivitätsleiste schiebt sich rein, Icons rutschen nacheinander
        a.los(380, 0, self.px(48), lambda v: self.aktivitaet.configure(width=int(v)), nach_ms=2150)
        for i, e in enumerate(self.aktiv_icons):
            a.los(420, -self.px(50), 0, lambda v, r=e["rahmen"]: r.place_configure(x=int(v)),
                  nach_ms=2400 + i * 110)
        a.spaeter(2400 + len(self.aktiv_icons) * 110 + 300, self._aktiv_icons_faerben)

        # 3) Explorer klappt auf, Dateien kommen nacheinander
        a.los(520, 0, self.seiten_breite, lambda v: self.seitenleiste.configure(width=int(v)), nach_ms=2700,
              fertig=lambda: self.seiten_trenner.pack(side="left", fill="y", after=self.seitenleiste))
        a.spaeter(2950, lambda: self.baum_laden(nacheinander=True))

        # 4) Konsole rutscht nach unten, Editor erscheint, Tab-Leiste kommt
        a.los(700, max(self.spalte.winfo_height(), self.px(500)), self.panel_hoehe,
              lambda v: self.panel.configure(height=int(v)), nach_ms=3300, kurve=weich_rein_raus)
        a.los(300, 0, self.px(36), lambda v: self.tableiste_rahmen.configure(height=int(v)), nach_ms=3800)
        for i, (teil, farbe) in enumerate(self.willkommen_teile):
            a.los(420, 0, 1, lambda t, w=teil, f=farbe: w.configure(fg=mische(HINTERGRUND, f, t)),
                  nach_ms=3900 + i * 70)

        # 5) Statusleiste
        a.los(260, 0, self.px(26), lambda v: self.statusleiste.configure(height=int(v)), nach_ms=4600)

        # 6) Fertig
        a.spaeter(5000, self._umbau_fertig)

    def _umbau_fertig(self):
        self._schreibe("")
        self._schreibe("✓ Willkommen in deiner neuen Entwicklungsumgebung.", "titel")
        self._schreibe("  Links deine Dateien, oben die Tabs, hier unten die Konsole. Viel Spaß!", "ein")
        self._schreibe("")
        self.root.minsize(self.px(720), self.px(460))
        self.einstellungen[UMBAU_SCHLUESSEL] = True
        speichere_einstellungen(self.einstellungen)
        self._status()
        self._fokus_holen()

    def _fokus_holen(self):
        try:
            self.root.lift()
            self.root.focus_force()
            (self.aktiv.text if self.aktiv else self.feld).focus_force()
        except tk.TclError:
            pass

    # ============================================================ Seitenleiste & Konsole ein/aus
    def seitenleiste_umschalten(self):
        self.seitenleiste_an = not self.seitenleiste_an
        if self.seitenleiste_an:
            self.seitenleiste.pack(side="left", fill="y", before=self.spalte)
            self.seiten_trenner.pack(side="left", fill="y", after=self.seitenleiste)
            self.animator.los(220, 0, self.seiten_breite, lambda v: self.seitenleiste.configure(width=int(v)))
        else:
            def weg():
                self.seitenleiste.pack_forget()
                self.seiten_trenner.pack_forget()
            self.animator.los(180, self.seitenleiste.winfo_width(), 0,
                              lambda v: self.seitenleiste.configure(width=int(v)), fertig=weg)
        self._aktiv_icons_faerben()

    def panel_umschalten(self):
        self.panel_an = not self.panel_an
        if self.panel_an:
            self.panel.pack(fill="x", side="bottom", before=self.editor_flaeche)
            self.panel_trenner.pack(fill="x", side="bottom", before=self.editor_flaeche)
            self.animator.los(220, 0, self.panel_hoehe, lambda v: self.panel.configure(height=int(v)))
            self.feld.focus_set()
        else:
            def weg():
                self.panel.pack_forget()
                self.panel_trenner.pack_forget()
            self.animator.los(180, self.panel.winfo_height(), 0,
                              lambda v: self.panel.configure(height=int(v)), fertig=weg)
        self._aktiv_icons_faerben()

    def _panel_zeigen(self):
        if not self.panel_an:
            self.panel_umschalten()

    def _seite_ziehen(self, e):
        neu = max(self.px(160), min(self.seitenleiste.winfo_width() + e.x, self.px(520)))
        self.seiten_breite = neu
        self.seitenleiste.configure(width=neu)

    def _panel_ziehen(self, e):
        neu = max(self.px(110), min(self.panel.winfo_height() - e.y, self.spalte.winfo_height() - self.px(120)))
        self.panel_hoehe = neu
        self.panel.configure(height=neu)

    # ============================================================ Status
    def _status(self, text=None, temp=False):
        if self.laeuft and not temp:
            self.status_links.configure(text="● läuft …   Esc = stoppen", fg=GOLD)
        elif text:
            self.status_links.configure(text=text, fg=HELLGRAU)
        else:
            self.status_links.configure(text="● bereit", fg=HELLGRAU)
        if self.aktiv:
            name = self.aktiv.name + (" ●" if self.aktiv.geaendert else "")
            ordner = os.path.basename(os.path.dirname(self.aktiv.pfad)) if self.aktiv.pfad else ""
            self.kopf_titel.configure(text=f"{ordner} / {name}" if ordner else name)
            self.root.title(f"{self.aktiv.name} – Edgy")
        else:
            self.kopf_titel.configure(text=os.path.basename(self.arbeitsordner))
            self.root.title("Edgy")
        self._cursor_anzeigen()

    def _cursor_anzeigen(self):
        if self.aktiv:
            zeile, spalte = self.aktiv.text.index("insert").split(".")
            self.status_cursor.configure(text=f"Zeile {zeile}, Spalte {int(spalte) + 1}")
            self._nummern_aktualisieren()
        else:
            self.status_cursor.configure(text="")

    # ============================================================ Explorer
    def _beispiele_anlegen(self):
        try:
            if any(not n.startswith(".") for n in os.listdir(self.arbeitsordner)):
                return
            with open(os.path.join(self.arbeitsordner, "willkommen.edgy"), "w", encoding="utf-8") as f:
                f.write(BEISPIEL)
            with open(os.path.join(self.arbeitsordner, "meine_seite.edgy"), "w", encoding="utf-8") as f:
                f.write(BEISPIEL_SEITE)
        except OSError:
            pass

    def _datei_icon(self, name):
        n = name.lower()
        if n.endswith(".edgy"):
            return self.icons("baum_edgy")
        if n.endswith((".html", ".htm")):
            return self.icons("baum_web")
        return self.icons("baum_datei")

    def baum_laden(self, nacheinander=False):
        offen = set()

        def sammle(eltern):
            for iid in self.baum.get_children(eltern):
                if self.baum.item(iid, "open"):
                    offen.add(iid)
                sammle(iid)
        sammle("")
        offen.update(self.einstellungen.get("offene_ordner", []))
        auswahl = self.baum.selection()
        self.baum.delete(*self.baum.get_children())
        self.ordner_titel.configure(text=os.path.basename(self.arbeitsordner).upper() or self.arbeitsordner)
        eintraege = self._eintraege(self.arbeitsordner)
        if nacheinander:
            for i, e in enumerate(eintraege):
                self.root.after(i * 55, lambda e=e: self._baum_eintrag("", e, offen, 0))
        else:
            for e in eintraege:
                self._baum_eintrag("", e, offen, 0)
            if auswahl and self.baum.exists(auswahl[0]):
                self.baum.selection_set(auswahl[0])
        self._status()

    def _eintraege(self, ordner):
        try:
            eintraege = [e for e in os.scandir(ordner)
                         if e.name not in IGNORIEREN and not e.name.startswith((".", "~$"))]
        except OSError:
            return []
        return sorted(eintraege, key=lambda e: (not e.is_dir(), e.name.lower()))

    def _baum_eintrag(self, eltern, e, offen, tiefe):
        try:
            if self.baum.exists(e.path):
                return
            if e.is_dir():
                ist_offen = e.path in offen
                iid = self.baum.insert(eltern, "end", iid=e.path, text=" " + e.name, open=ist_offen,
                                       image=self.icons("baum_auf" if ist_offen else "baum_zu"))
                if tiefe < 8:
                    for kind in self._eintraege(e.path):
                        self._baum_eintrag(iid, kind, offen, tiefe + 1)
            else:
                self.baum.insert(eltern, "end", iid=e.path, text=" " + e.name, image=self._datei_icon(e.name))
        except tk.TclError:
            pass

    def _ordner_icons(self):
        def setze(eltern):
            for iid in self.baum.get_children(eltern):
                if os.path.isdir(iid):
                    self.baum.item(iid, image=self.icons("baum_auf" if self.baum.item(iid, "open") else "baum_zu"))
                    setze(iid)
        self.root.after(1, lambda: setze(""))

    def _baum_klick(self, e=None):
        maus = e is not None and getattr(e, "type", None) == tk.EventType.ButtonRelease
        iid = self.baum.identify_row(e.y) if maus else self.baum.focus()
        if not iid:
            return
        if os.path.isdir(iid):
            # Klick auf Ordner klappt ihn auf/zu (wie in VS Code)
            self.baum.item(iid, open=not self.baum.item(iid, "open"))
            self._ordner_icons()
        elif os.path.isfile(iid):
            self.datei_oeffnen(iid)

    def _baum_rechtsklick(self, e):
        iid = self.baum.identify_row(e.y)
        if iid:
            self.baum.selection_set(iid)
            self.baum.focus(iid)
        self._kontextmenue(e, iid or self.arbeitsordner)

    def _kontextmenue(self, e, pfad):
        ordner = pfad if os.path.isdir(pfad) else os.path.dirname(pfad)
        m = tk.Menu(self.root, tearoff=0, bg="#16161a", fg=TEXT, activebackground="#2a1416",
                    activeforeground="#ffffff", bd=0, relief="flat", font=self.ui_schrift)
        m.add_command(label="  Neue Datei …", command=lambda: self.neue_datei_dialog(ordner))
        m.add_command(label="  Neuer Ordner …", command=lambda: self.neuer_ordner_dialog(ordner))
        if pfad != self.arbeitsordner:
            m.add_separator()
            if os.path.isfile(pfad):
                m.add_command(label="  Öffnen", command=lambda: self.datei_oeffnen(pfad))
                if pfad.lower().endswith(".edgy"):
                    m.add_command(label="  Starten", command=lambda: (self.datei_oeffnen(pfad), self.starten()))
            m.add_command(label="  Umbenennen …", command=lambda: self.umbenennen_dialog(pfad))
            m.add_command(label="  Löschen", command=lambda: self.loeschen(pfad))
        m.add_separator()
        m.add_command(label="  Im Windows-Explorer zeigen", command=lambda: self._im_explorer_zeigen(pfad))
        m.add_command(label="  Aktualisieren", command=self.baum_laden)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _im_explorer_zeigen(self, pfad):
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(pfad)])
            else:
                webbrowser.open(pathlib.Path(os.path.dirname(pfad)).as_uri())
        except OSError:
            pass

    def _ausgewaehlter_ordner(self):
        auswahl = self.baum.selection()
        if auswahl:
            p = auswahl[0]
            return p if os.path.isdir(p) else os.path.dirname(p)
        return self.arbeitsordner

    def frage_name(self, titel, vorgabe=""):
        """Kleines dunkles Fenster, das nach einem Namen fragt."""
        d = tk.Toplevel(self.root, bg=SEITE)
        d.title(titel)
        d.transient(self.root)
        d.resizable(False, False)
        try:
            d.iconbitmap(ressource("edgy.ico"))
        except Exception:
            pass
        tk.Label(d, text=titel, font=self.ui_schrift_fett, fg=TEXT, bg=SEITE).pack(anchor="w", padx=self.px(18), pady=(self.px(16), self.px(8)))
        rahmen = tk.Frame(d, bg=DE_ROT, padx=1, pady=1)
        rahmen.pack(fill="x", padx=self.px(18))
        feld = tk.Entry(rahmen, font=self.schrift, bg=HINTERGRUND, fg=TEXT, insertbackground=GOLD, bd=0,
                        highlightthickness=0, width=34)
        feld.pack(fill="x", ipady=self.px(6), ipadx=self.px(6))
        feld.insert(0, vorgabe)
        punkt = vorgabe.rfind(".")
        feld.selection_range(0, punkt if punkt > 0 else "end")
        feld.icursor(punkt if punkt > 0 else "end")
        tk.Label(d, text="Enter = OK     Esc = Abbrechen", font=self.ui_schrift_klein, fg=GRAU, bg=SEITE).pack(
            anchor="w", padx=self.px(18), pady=(self.px(8), self.px(14)))
        ergebnis = {"wert": None}

        def ok(_=None):
            ergebnis["wert"] = feld.get().strip()
            d.destroy()
        feld.bind("<Return>", ok)
        feld.bind("<Escape>", lambda e: d.destroy())
        d.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - d.winfo_width()) // 2
        y = self.root.winfo_rooty() + self.px(120)
        d.geometry(f"+{x}+{y}")
        _windows_feinschliff(d)
        feld.focus_force()
        d.grab_set()
        self.root.wait_window(d)
        return ergebnis["wert"] or None

    def _gueltiger_name(self, name):
        if not name or re.search(r'[\\/:*?"<>|]', name) or name in (".", ".."):
            messagebox.showerror("Edgy", "Dieser Name geht nicht.\nVerboten sind:  \\ / : * ? \" < > |")
            return False
        return True

    def datei_anlegen(self, ordner, name, inhalt=""):
        pfad = os.path.join(ordner, name)
        if os.path.exists(pfad):
            raise FileExistsError(name)
        with open(pfad, "w", encoding="utf-8", newline="\n") as f:
            f.write(inhalt)
        self.baum_laden()
        self._baum_zeigen(pfad)
        return pfad

    def ordner_anlegen(self, ordner, name):
        pfad = os.path.join(ordner, name)
        os.makedirs(pfad)
        self.baum_laden()
        self._baum_zeigen(pfad, aufklappen=True)
        return pfad

    def _baum_zeigen(self, pfad, aufklappen=False):
        if self.baum.exists(pfad):
            eltern = self.baum.parent(pfad)
            while eltern:
                self.baum.item(eltern, open=True)
                eltern = self.baum.parent(eltern)
            if aufklappen:
                self.baum.item(pfad, open=True)
            self.baum.selection_set(pfad)
            self.baum.focus(pfad)
            self.baum.see(pfad)
            self._ordner_icons()

    def neue_datei_dialog(self, ordner=None):
        ordner = ordner or self._ausgewaehlter_ordner()
        name = self.frage_name("Neue Datei", "neu.edgy")
        if not name or not self._gueltiger_name(name):
            return
        if "." not in name:
            name += ".edgy"
        try:
            pfad = self.datei_anlegen(ordner, name)
        except FileExistsError:
            messagebox.showerror("Edgy", f"'{name}' gibt es dort schon.")
            return
        except OSError as f:
            messagebox.showerror("Edgy", f"Ging nicht:\n{f}")
            return
        self.datei_oeffnen(pfad)

    def neuer_ordner_dialog(self, ordner=None):
        ordner = ordner or self._ausgewaehlter_ordner()
        name = self.frage_name("Neuer Ordner", "Neuer Ordner")
        if not name or not self._gueltiger_name(name):
            return
        try:
            self.ordner_anlegen(ordner, name)
        except FileExistsError:
            messagebox.showerror("Edgy", f"'{name}' gibt es dort schon.")
        except OSError as f:
            messagebox.showerror("Edgy", f"Ging nicht:\n{f}")

    def umbenennen_dialog(self, pfad):
        alt = os.path.basename(pfad)
        neu = self.frage_name("Umbenennen", alt)
        if not neu or neu == alt or not self._gueltiger_name(neu):
            return
        self.umbenennen(pfad, neu)

    def umbenennen(self, pfad, neuer_name):
        ziel = os.path.join(os.path.dirname(pfad), neuer_name)
        if os.path.exists(ziel):
            messagebox.showerror("Edgy", f"'{neuer_name}' gibt es dort schon.")
            return None
        try:
            os.rename(pfad, ziel)
        except OSError as f:
            messagebox.showerror("Edgy", f"Umbenennen ging nicht:\n{f}")
            return None
        for tab in self.tabs:
            if tab.pfad and (tab.pfad == pfad or tab.pfad.startswith(pfad + os.sep)):
                tab.pfad = ziel + tab.pfad[len(pfad):]
                tab.faerben(tab is self.aktiv)
        self.baum_laden()
        self._baum_zeigen(ziel)
        self._status()
        return ziel

    def loeschen(self, pfad, nachfragen=True):
        name = os.path.basename(pfad)
        art = "den Ordner" if os.path.isdir(pfad) else "die Datei"
        if nachfragen and not messagebox.askyesno("Löschen", f"Willst du {art} '{name}' löschen?\n\nSie kommt in den Papierkorb."):
            return False
        if not in_papierkorb(pfad):
            if nachfragen and not messagebox.askyesno(
                    "Endgültig löschen?", f"Der Papierkorb ging nicht.\n'{name}' endgültig löschen? Das kann man nicht rückgängig machen."):
                return False
            try:
                shutil.rmtree(pfad) if os.path.isdir(pfad) else os.remove(pfad)
            except OSError as f:
                messagebox.showerror("Edgy", f"Löschen ging nicht:\n{f}")
                return False
        for tab in list(self.tabs):
            if tab.pfad and (tab.pfad == pfad or tab.pfad.startswith(pfad + os.sep)):
                tab.text.edit_modified(False)
                self.tab_schliessen(tab)
        self.baum_laden()
        return True

    def ordner_waehlen(self):
        pfad = filedialog.askdirectory(title="Ordner öffnen", initialdir=self.arbeitsordner)
        if pfad:
            self.arbeitsordner = os.path.abspath(pfad)
            self.einstellungen["arbeitsordner"] = self.arbeitsordner
            self.einstellungen["offene_ordner"] = []
            speichere_einstellungen(self.einstellungen)
            self.baum_laden()
            if not self.seitenleiste_an:
                self.seitenleiste_umschalten()

    # ============================================================ Tabs
    def datei_oeffnen(self, pfad):
        pfad = os.path.abspath(pfad)
        for tab in self.tabs:
            if tab.pfad and os.path.normcase(tab.pfad) == os.path.normcase(pfad):
                self.tab_aktivieren(tab)
                return tab
        try:
            with open(pfad, encoding="utf-8-sig") as f:
                inhalt = f.read()
        except UnicodeDecodeError:
            messagebox.showinfo("Edgy", f"'{os.path.basename(pfad)}' ist keine Textdatei und kann hier nicht geöffnet werden.")
            return None
        except OSError as f:
            messagebox.showerror("Edgy", f"Öffnen ging nicht:\n{f}")
            return None
        tab = Tab(self, pfad, inhalt)
        self.tabs.append(tab)
        self.tab_aktivieren(tab)
        self._baum_zeigen(pfad)
        return tab

    def datei_oeffnen_dialog(self):
        pfad = filedialog.askopenfilename(
            title="Datei öffnen", initialdir=self.arbeitsordner,
            filetypes=[("Edgy-Programme", "*.edgy"), ("Alle Dateien", "*.*")],
        )
        if pfad:
            self.datei_oeffnen(pfad)

    def neue_datei(self, inhalt=""):
        tab = Tab(self, None, inhalt)
        self.tabs.append(tab)
        self.tab_aktivieren(tab)
        return tab

    def tab_aktivieren(self, tab):
        if self.aktiv and self.aktiv is not tab:
            if self.aktiv.geist:
                self.aktiv.geist.weg()
            self.aktiv.text.pack_forget()
        self.aktiv = tab
        tab.text.pack(fill="both", expand=True)
        for t in self.tabs:
            t.faerben(t is tab)
        self.editor_leiste.ziel = tab.text
        self._editor_anzeigen()
        self._nummern_aktualisieren()
        tab.text.focus_set()
        self._status()

    def tab_schliessen(self, tab):
        if tab.geaendert and tab.inhalt().strip():
            antwort = messagebox.askyesnocancel("Edgy", f"'{tab.name}' hat ungespeicherte Änderungen.\nVorher speichern?")
            if antwort is None:
                return False
            if antwort and not self.speichern(tab):
                return False
        index = self.tabs.index(tab)
        self.tabs.remove(tab)
        # Trennlinie hinter dem Reiter mit entfernen
        kinder = self.tableiste.pack_slaves()
        if tab.reiter in kinder:
            i = kinder.index(tab.reiter)
            if i + 1 < len(kinder):
                kinder[i + 1].destroy()
        tab.entfernen()
        if self.aktiv is tab:
            self.aktiv = None
            if self.tabs:
                self.tab_aktivieren(self.tabs[min(index, len(self.tabs) - 1)])
        self._editor_anzeigen()
        self._status()
        return True

    def naechster_tab(self):
        if len(self.tabs) > 1 and self.aktiv:
            self.tab_aktivieren(self.tabs[(self.tabs.index(self.aktiv) + 1) % len(self.tabs)])

    def _editor_anzeigen(self):
        if self.tabs:
            self.willkommen.pack_forget()
            if not self.editor_rahmen.winfo_ismapped():
                self.editor_rahmen.pack(fill="both", expand=True)
        else:
            self.editor_rahmen.pack_forget()
            self.willkommen.pack(fill="both", expand=True)

    def _tab_aktualisieren(self, tab):
        tab.faerben(tab is self.aktiv)
        self._status()

    def _editor_scroll(self, tab, *args):
        if tab is self.aktiv:
            self.editor_leiste.set(*args)
            self.nummern.yview_moveto(args[0])

    def _nummern_aktualisieren(self):
        if not self.aktiv:
            return
        t = self.aktiv.text
        anzahl = int(t.index("end-1c").split(".")[0])
        aktuell = int(t.index("insert").split(".")[0])
        self.nummern.configure(state="normal", width=max(len(str(anzahl)), 3))
        self.nummern.delete("1.0", "end")
        self.nummern.insert("1.0", "\n".join(str(i) for i in range(1, anzahl + 1)), "rechts")
        self.nummern.tag_add("aktuell", f"{aktuell}.0", f"{aktuell}.end")
        self.nummern.configure(state="disabled")
        self.nummern.yview_moveto(t.yview()[0])

    def _editor_enter(self, tab):
        if tab.geist:
            tab.geist.weg()
        t = tab.text
        zeile = t.get("insert linestart", "insert lineend")
        vorher = t.get("1.0", "insert linestart")
        if tab.ist_edgy:
            tiefe_davor = max(block_tiefe(vorher), 0)
            if zeile.strip() in ("ende", "sonst"):
                alt = len(zeile) - len(zeile.lstrip(" "))
                soll = max(tiefe_davor - 1, 0) * 2
                t.delete("insert linestart", f"insert linestart+{alt}c")
                t.insert("insert linestart", " " * soll)
            tiefe = max(block_tiefe(vorher + zeile), 0)
            einzug = tiefe * 2 if zeile.strip() else len(zeile) - len(zeile.lstrip(" "))
        else:
            einzug = len(zeile) - len(zeile.lstrip(" "))
        t.insert("insert", "\n" + " " * einzug)
        t.see("insert")
        self._editor_geaendert(tab)
        return "break"

    def _editor_geaendert(self, tab):
        if tab.ist_edgy:
            faerbe(tab.text)
        if tab is self.aktiv:
            self._cursor_anzeigen()

    def _bekannte_namen(self):
        namen = set(self.edgy.variablen)
        if self.aktiv and self.aktiv.ist_edgy:
            try:
                code = self.aktiv.text.get("1.0", "end-1c")
                namen.update(re.findall(r"^\s*(?:merk|frag|zähl|zaehl)\s+([A-Za-zÄÖÜäöüß_][\wÄÖÜäöüß]*)", code, re.M))
            except tk.TclError:
                pass
        return sorted(namen)

    def speichern(self, tab=None, unter=False):
        tab = tab or self.aktiv
        if not tab:
            return False
        inhalt = tab.inhalt()
        pfad = tab.pfad
        if unter or not pfad:
            pfad = filedialog.asksaveasfilename(
                title="Speichern unter", initialdir=self.arbeitsordner,
                initialfile=tab.name if tab.pfad else "programm.edgy", defaultextension=".edgy",
                filetypes=[("Edgy-Programme", "*.edgy"), ("Alle Dateien", "*.*")],
            )
            if not pfad:
                return False
        try:
            with open(pfad, "w", encoding="utf-8", newline="\n") as f:
                f.write(inhalt)
        except OSError as f:
            messagebox.showerror("Edgy", f"Speichern hat nicht geklappt:\n{f}")
            return False
        tab.pfad = os.path.abspath(pfad)
        tab.text.edit_modified(False)
        tab.faerben(tab is self.aktiv)
        self.baum_laden()
        self._status(f"✓ {tab.name} gespeichert", temp=True)
        self.root.after(1800, self._status)
        return True

    # ============================================================ Starten
    def starten(self):
        if self.laeuft:
            return
        tab = self.aktiv
        if not tab:
            tab = self.neue_datei(BEISPIEL)
            self._status("Hier ist ein Beispiel – drück F5 zum Starten.", temp=True)
            return
        if tab.pfad and tab.pfad.lower().endswith((".html", ".htm")):
            if tab.geaendert:
                self.speichern(tab)
            webbrowser.open(pathlib.Path(tab.pfad).as_uri())
            return
        if not tab.ist_edgy:
            self._panel_zeigen()
            self._schreibe(f"✕ {tab.name} ist keine Edgy-Datei.", "fehler")
            return
        code = tab.inhalt()
        if not code.strip():
            self._status("Die Datei ist leer.", temp=True)
            return
        if tab.pfad and tab.geaendert:
            self.speichern(tab)
        self.puffer = []
        self.lauf_datei = tab.pfad
        self._panel_zeigen()
        self._schreibe(f"▶ {tab.name}", "info")
        self._starte(code)

    def _starte(self, code):
        self.laeuft = True
        self._status()
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
        if self.lauf_datei:
            ordner = os.path.dirname(self.lauf_datei)
            name = os.path.splitext(os.path.basename(self.lauf_datei))[0]
        else:
            ordner = os.path.join(self.arbeitsordner, "Webseiten")
            name = re.sub(r"[^\wÄÖÜäöüß -]", "", titel).strip() or "seite"
        os.makedirs(ordner, exist_ok=True)
        pfad = os.path.join(ordner, name + ".html")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(html_code)
        webbrowser.open(pathlib.Path(pfad).as_uri())
        self.ausgaben.put(("info", f"🌐 Seite geöffnet: {pfad}"))
        self.ausgaben.put(("baum", None))

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

    # ============================================================ Konsole
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
        self._schreibe("Tipp hier Befehle ein oder öffne links eine Datei.  hilfe zeigt alle Befehle.", "ein")
        self._schreibe("")

    def _tab_hinweis(self, sichtbar):
        if sichtbar:
            if not self.tab_hinweis.winfo_ismapped():
                self.tab_hinweis.pack(side="right", before=self.feld)
        else:
            self.tab_hinweis.pack_forget()

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
            self.lauf_datei = None
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
            self._panel_zeigen()
            self._schreibe(HILFE, "hilfe")
        elif befehl == "leeren":
            self._leeren()
        elif befehl == "beenden":
            self._schliessen()
        elif befehl in ("öffne", "oeffne"):
            self.datei_oeffnen_dialog()
        elif befehl == "editor":
            if self.aktiv:
                self.aktiv.text.focus_set()
            else:
                self.neue_datei()
        elif befehl == "beispiel":
            self._panel_zeigen()
            self._schreibe(BEISPIEL.rstrip(), "ein")
            self._schreibe("")
            self.lauf_datei = None
            self._starte(BEISPIEL)
        elif befehl == "beispiel_datei":
            self.neue_datei(BEISPIEL)
        elif befehl == "webseite":
            self.neue_datei(BEISPIEL_SEITE)
            self._status("Beispiel-Webseite – drück F5, dann öffnet sie sich im Browser.", temp=True)
        elif befehl == "version":
            self._schreibe(f"Edgy v{VERSION}", "info")

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
                    self._status()
                elif art == "frage":
                    self._panel_zeigen()
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
                elif art == "baum":
                    self.baum_laden()
                elif art == "update_start":
                    self.update_bildschirm(inhalt)
                elif art == "update_fortschritt":
                    self.update_fortschritt(inhalt)
                elif art == "update_fertig":
                    self.update_fertig()
                elif art == "update_fehler":
                    self.update_fehler(inhalt)
                else:
                    self._schreibe(inhalt, None if art == "aus" else art)
        except queue.Empty:
            pass
        except tk.TclError:
            return
        self.root.after(30, self._verarbeite_ausgaben)

    def _schliessen(self):
        for tab in list(self.tabs):
            if tab.geaendert and tab.inhalt().strip():
                self.tab_aktivieren(tab)
                antwort = messagebox.askyesnocancel("Edgy", f"'{tab.name}' hat ungespeicherte Änderungen.\nVorher speichern?")
                if antwort is None:
                    return
                if antwort and not self.speichern(tab):
                    return
        offen = []

        def sammle(eltern):
            for iid in self.baum.get_children(eltern):
                if self.baum.item(iid, "open"):
                    offen.append(iid)
                sammle(iid)
        sammle("")
        self.einstellungen["offene_dateien"] = [t.pfad for t in self.tabs if t.pfad]
        self.einstellungen["offene_ordner"] = offen
        self.einstellungen["arbeitsordner"] = self.arbeitsordner
        speichere_einstellungen(self.einstellungen)
        self.edgy.stopp = True
        self.antworten.put("")
        self.root.destroy()

    # ============================================================ Update
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

    BALKEN_BREITE = 340

    def update_bildschirm(self, neu):
        self.geist_konsole.weg()
        o = tk.Frame(self.root, bg=HINTERGRUND)
        o.place(x=0, y=0, relwidth=1, relheight=1)
        o.lift()
        self._update_ebene = o
        mitte = tk.Frame(o, bg=HINTERGRUND)
        mitte.place(relx=0.5, rely=0.46, anchor="center")
        tk.Label(mitte, image=self.icons("logo_gross"), bg=HINTERGRUND).pack(pady=(0, self.px(26)))
        self._u_titel = tk.Label(mitte, text=f"Update auf {neu}", font=(self.ui_schrift.actual("family"), 17, "bold"),
                                 fg=TEXT, bg=HINTERGRUND)
        self._u_titel.pack()
        self._u_text = tk.Label(mitte, text="Die neue Version wird geladen …", font=self.ui_schrift,
                                fg=HELLGRAU, bg=HINTERGRUND)
        self._u_text.pack(pady=(self.px(6), self.px(26)))
        self._u_balken = tk.Canvas(mitte, width=self.px(self.BALKEN_BREITE), height=self.px(4), bg=LINIE,
                                   highlightthickness=0, bd=0)
        self._u_balken.pack()
        self._u_prozent = tk.Label(mitte, text="0 %", font=self.ui_schrift_klein, fg=GRAU, bg=HINTERGRUND)
        self._u_prozent.pack(pady=(self.px(10), 0))
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
        breite = int(self.px(self.BALKEN_BREITE) * self._u_wert)
        self._u_balken.delete("all")
        if breite > 0:
            self._u_balken.create_rectangle(0, 0, breite, self.px(4), fill=GOLD, width=0)
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
