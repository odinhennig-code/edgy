"""Das eigene schwarze Edgy-Fenster."""

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, font as tkfont

from . import update
from .sprache import Abbruch, Edgy, EdgyFehler, braucht_mehr_zeilen
from .version import VERSION

# Farben
HINTERGRUND = "#0c0c0d"
FELD = "#141416"
TEXT = "#ececec"
GRAU = "#6b6b70"
ROT = "#ff3b3b"
GOLD = "#ffce00"
SCHWARZ = "#1b1b1b"
DE_ROT = "#dd0000"

HILFE = """\
Befehle von Edgy
  gib aus "Hallo"            Text anzeigen
  merk name = "Max"          etwas speichern
  frag alter "Wie alt?"      den Nutzer etwas fragen
  wenn alter > 12 dann       Entscheidung
    ...
  sonst
    ...
  ende
  wiederhol 3 mal            Schleife
    ...
  ende

Rechnen:  + - * / %   Vergleichen:  == != < > <= >=  ist
Logik:    und  oder  nicht  wahr  falsch       Kommentar:  # ...

Fenster-Befehle
  öffne      eine .edgy-Datei auswählen und starten
  beispiel   ein Beispielprogramm laufen lassen
  leeren     Fenster leeren
  beenden    Edgy schließen
  Esc        laufendes Programm stoppen
"""

BEISPIEL = """\
gib aus "Willkommen bei Edgy!"
frag name "Wie heißt du?"
gib aus "Hi " + name + "!"
frag zahl "Gib eine Zahl ein:"
wenn zahl > 10 dann
  gib aus "Das ist eine große Zahl."
sonst
  gib aus "Das ist eine kleine Zahl."
ende
wiederhol 3 mal
  gib aus "Edgy ist scharf."
ende
"""


def ressource(name):
    basis = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(basis, "assets", name)


def _windows_feinschliff(root):
    """Dunkle Titelleiste + eigenes Taskleisten-Symbol unter Windows."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Edgy.Programmiersprache")
    except Exception:
        pass
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        wert = ctypes.c_int(1)
        for attribut in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribut, ctypes.byref(wert), 4) == 0:
                break
    except Exception:
        pass


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
        self.root.geometry("920x580")
        self.root.minsize(520, 320)
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

        self._baue_oberflaeche()

        self.ausgaben = queue.Queue()
        self.antworten = queue.Queue()
        self.edgy = Edgy(ausgabe=self._aus_thread, eingabe=self._frage_aus_thread)
        self.laeuft = False
        self.wartet_auf_antwort = False
        self.puffer = []
        self.verlauf = []
        self.verlauf_pos = 0

        self._begruessung()
        self.root.after(30, self._verarbeite_ausgaben)
        _windows_feinschliff(self.root)

        if update.ist_exe():
            threading.Thread(target=self._pruefe_update, daemon=True).start()

        if start_datei:
            self.root.after(200, lambda: self._starte_datei(start_datei))

    # ------------------------------------------------------------ Oberfläche
    def _baue_oberflaeche(self):
        streifen = tk.Frame(self.root, height=3, bg=HINTERGRUND)
        streifen.pack(fill="x", side="top")
        for farbe in (SCHWARZ, DE_ROT, GOLD):
            tk.Frame(streifen, height=3, bg=farbe).pack(side="left", fill="both", expand=True)

        kopf = tk.Frame(self.root, bg=HINTERGRUND)
        kopf.pack(fill="x", padx=22, pady=(14, 4))
        try:
            self._zeichen = tk.PhotoImage(file=ressource("zeichen.png"))
            tk.Label(kopf, image=self._zeichen, bg=HINTERGRUND).pack(side="left", padx=(0, 10))
        except Exception:
            pass
        tk.Label(kopf, text="Edgy", font=("Segoe UI Semibold", 16),
                 fg=TEXT, bg=HINTERGRUND).pack(side="left")
        tk.Label(kopf, text=f"v{VERSION}", font=self.schrift, fg=GRAU,
                 bg=HINTERGRUND).pack(side="left", padx=(10, 0), pady=(3, 0))
        self.status = tk.Label(kopf, text="bereit", font=self.schrift, fg=GRAU, bg=HINTERGRUND)
        self.status.pack(side="right")

        # Eingabezeile ZUERST unten festmachen, damit sie nie aus dem Fenster gedrückt wird
        unten = tk.Frame(self.root, bg=FELD, cursor="xterm")
        unten.pack(fill="x", side="bottom", padx=16, pady=16)
        self.prompt = tk.Label(unten, text="›", font=self.schrift_fett, fg=DE_ROT, bg=FELD)
        self.prompt.pack(side="left", padx=(14, 8), pady=10)
        self.feld = tk.Entry(unten, bg=FELD, fg=TEXT, font=self.schrift, bd=0,
                             highlightthickness=0, insertbackground=GOLD, insertwidth=2,
                             disabledbackground=FELD, readonlybackground=FELD)
        self.feld.pack(side="left", fill="x", expand=True, padx=(0, 14), pady=10)
        self.feld.bind("<Return>", self._enter)
        self.feld.bind("<KP_Enter>", self._enter)
        self.feld.bind("<Up>", lambda e: self._blaettern(-1))
        self.feld.bind("<Down>", lambda e: self._blaettern(1))
        unten.bind("<Button-1>", lambda e: self.feld.focus_set())
        self.prompt.bind("<Button-1>", lambda e: self.feld.focus_set())

        rahmen = tk.Frame(self.root, bg=HINTERGRUND)
        rahmen.pack(fill="both", expand=True, padx=22, pady=(6, 0))
        self.anzeige = tk.Text(
            rahmen, height=1, width=1,
            bg=HINTERGRUND, fg=TEXT, font=self.schrift, bd=0, highlightthickness=0,
            wrap="word", insertbackground=TEXT, selectbackground="#333338",
            padx=0, pady=4, spacing1=2, spacing3=2, cursor="arrow",
        )
        leiste = tk.Scrollbar(rahmen, command=self.anzeige.yview, bg=HINTERGRUND,
                              troughcolor=HINTERGRUND, bd=0, highlightthickness=0,
                              activebackground=GRAU, width=8)
        self.anzeige.configure(yscrollcommand=leiste.set)
        leiste.pack(side="right", fill="y")
        self.anzeige.pack(side="left", fill="both", expand=True)
        self.anzeige.tag_configure("aus", foreground=TEXT)
        self.anzeige.tag_configure("ein", foreground=GRAU)
        self.anzeige.tag_configure("fehler", foreground=ROT)
        self.anzeige.tag_configure("info", foreground=GOLD)
        self.anzeige.tag_configure("frage", foreground=GOLD)
        self.anzeige.tag_configure("titel", foreground=TEXT, font=self.schrift_fett)
        self.anzeige.configure(state="disabled")
        # Wer ins Fenster tippt, schreibt immer in die Eingabezeile
        self.anzeige.bind("<ButtonRelease-1>", self._fokus_wenn_nichts_markiert)
        self.anzeige.bind("<Key>", self._tippen_umleiten)

        self.root.bind("<Escape>", lambda e: self._stopp())
        self.root.bind("<Control-l>", lambda e: self._leeren())
        self.root.after(150, self._fokus_holen)

    def _fokus_holen(self):
        try:
            self.root.lift()
            self.root.focus_force()
            self.feld.focus_force()
            self.feld.icursor("end")
        except tk.TclError:
            pass

    def _fokus_wenn_nichts_markiert(self, _=None):
        if not self.anzeige.tag_ranges("sel"):
            self.feld.focus_set()

    def _tippen_umleiten(self, ereignis):
        if ereignis.state & 0x4:  # Strg gedrückt (z. B. Strg+C zum Kopieren)
            return None
        self.feld.focus_set()
        if ereignis.char and ereignis.char.isprintable():
            self.feld.insert("end", ereignis.char)
        elif ereignis.keysym in ("Return", "KP_Enter"):
            self._enter()
        return "break"

    def _schreibe(self, text, tag="aus"):
        self.anzeige.configure(state="normal")
        self.anzeige.insert("end", text + "\n", tag)
        self.anzeige.configure(state="disabled")
        self.anzeige.see("end")

    def _leeren(self):
        self.anzeige.configure(state="normal")
        self.anzeige.delete("1.0", "end")
        self.anzeige.configure(state="disabled")

    def _begruessung(self):
        self._schreibe("Willkommen bei Edgy.", "titel")
        self._schreibe("Schreib einen Befehl, z. B.  gib aus \"Hallo Welt\"  –  oder tippe  hilfe", "ein")
        self._schreibe("")

    # ------------------------------------------------------------ Eingabe
    def _enter(self, _=None):
        zeile = self.feld.get()
        self.feld.delete(0, "end")

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

        einrueck = "  " * self._tiefe()
        self._schreibe(("› " if not self.puffer else "… ") + einrueck + zeile, "ein")

        befehl = zeile.strip().lower()
        if not self.puffer and befehl in ("hilfe", "leeren", "beenden", "öffne", "oeffne", "beispiel", "version"):
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

    def _tiefe(self):
        tiefe = 0
        for z in self.puffer:
            w = z.strip().split()
            if w and w[0] in ("wenn", "wiederhol"):
                tiefe += 1
            elif w and w[0] == "ende":
                tiefe -= 1
        return max(tiefe, 0)

    def _blaettern(self, richtung):
        if not self.verlauf or self.wartet_auf_antwort:
            return "break"
        self.verlauf_pos = max(0, min(len(self.verlauf), self.verlauf_pos + richtung))
        self.feld.delete(0, "end")
        if self.verlauf_pos < len(self.verlauf):
            self.feld.insert(0, self.verlauf[self.verlauf_pos])
        return "break"

    def _fensterbefehl(self, befehl):
        if befehl == "hilfe":
            self._schreibe(HILFE, "info")
        elif befehl == "leeren":
            self._leeren()
        elif befehl == "beenden":
            self.root.destroy()
        elif befehl in ("öffne", "oeffne"):
            pfad = filedialog.askopenfilename(
                title="Edgy-Datei öffnen",
                filetypes=[("Edgy-Programme", "*.edgy"), ("Textdateien", "*.txt"), ("Alle Dateien", "*.*")],
            )
            if pfad:
                self._starte_datei(pfad)
        elif befehl == "beispiel":
            self._schreibe(BEISPIEL.rstrip(), "ein")
            self._schreibe("")
            self._starte(BEISPIEL)
        elif befehl == "version":
            self._schreibe(f"Edgy v{VERSION}", "info")

    # ------------------------------------------------------------ Ausführen
    def _starte_datei(self, pfad):
        try:
            with open(pfad, encoding="utf-8-sig") as f:
                code = f.read()
        except OSError as e:
            self._schreibe(f"Datei konnte nicht geöffnet werden: {e}", "fehler")
            return
        self._schreibe(f"▶ {os.path.basename(pfad)}", "info")
        self._starte(code)

    def _starte(self, code):
        self.laeuft = True
        self.status.configure(text="läuft …", fg=GOLD)
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

    def _aus_thread(self, text):
        self.ausgaben.put(("aus", text))

    def _frage_aus_thread(self, frage):
        self.ausgaben.put(("frage", frage))
        antwort = self.antworten.get()
        if self.edgy.stopp:
            raise Abbruch()
        return antwort

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

    def _verarbeite_ausgaben(self):
        try:
            for _ in range(500):
                art, text = self.ausgaben.get_nowait()
                if art == "fertig":
                    self.laeuft = False
                    self.status.configure(text="bereit", fg=GRAU)
                elif art == "frage":
                    if text:
                        self._schreibe(text, "frage")
                    self.wartet_auf_antwort = True
                    self.prompt.configure(text="?", fg=GOLD)
                    self.feld.focus_set()
                elif art == "update":
                    self._schreibe(text, "info")
                elif art == "schliessen":
                    self.root.destroy()
                    return
                else:
                    self._schreibe(text, art)
        except queue.Empty:
            pass
        self.root.after(30, self._verarbeite_ausgaben)

    # ------------------------------------------------------------ Update
    def _pruefe_update(self):
        try:
            gefunden = update.suche_update()
        except Exception:
            return  # kein Internet o. Ä. – einfach weitermachen
        if not gefunden:
            return
        neu, url = gefunden
        self.ausgaben.put(("update", f"⟳ Neue Version {neu} gefunden – wird geladen …"))
        try:
            update.installiere(url)
        except Exception as f:
            self.ausgaben.put(("fehler", f"✕ Update fehlgeschlagen: {f}"))
            return
        self.ausgaben.put(("update", "⟳ Fertig – Edgy startet neu."))
        self.ausgaben.put(("schliessen", None))

    def start(self):
        self.root.mainloop()
