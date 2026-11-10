<p align="center"><img src="assets/edgy.png" width="96"></p>

<h1 align="center">Edgy</h1>

<p align="center">Eine eigene Programmiersprache – auf Deutsch.</p>

---

## Download

Die neueste **Edgy.exe** gibt's unter [Releases](../../releases/latest).

Einfach starten, unten in der Taskleiste Rechtsklick auf das Symbol → **An Taskleiste anheften**.

Updates kommen automatisch: Edgy schaut beim Start nach einer neuen Version und tauscht sich selbst aus.

---

## So sieht Edgy aus

```
gib aus "Hallo Welt!"

frag name "Wie heißt du?"
gib aus "Hi " + name

wenn name ist "Max" dann
  gib aus "Kenn ich!"
sonst
  gib aus "Neu hier?"
ende

wiederhol 3 mal
  gib aus "Edgy ist scharf."
ende
```

---

## Befehle

| Befehl | Was er macht |
|---|---|
| `gib aus "Text"` | Text anzeigen |
| `merk name = wert` | Etwas speichern |
| `frag name "Frage?"` | Den Nutzer etwas fragen |
| `wenn ... dann` / `sonst` / `ende` | Entscheidung |
| `wiederhol 3 mal` / `ende` | Schleife |
| `# ...` | Kommentar |

Rechnen: `+ - * / %` · Vergleichen: `== != < > <= >= ist` · Logik: `und oder nicht wahr falsch`

Im Fenster außerdem: `hilfe`, `beispiel`, `öffne`, `leeren`, `beenden` · **Esc** stoppt ein laufendes Programm.

---

## Neue Version rausbringen

1. Code ändern
2. In `edgy/version.py` die Nummer hochzählen (z. B. `0.1.0` → `0.2.0`)
3. Hochladen – GitHub baut die neue `Edgy.exe` automatisch
