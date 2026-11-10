"""Startet Edgy. Optional mit einer .edgy-Datei:  Edgy.exe programm.edgy"""

import sys

from edgy.fenster import EdgyFenster


def main():
    datei = sys.argv[1] if len(sys.argv) > 1 else None
    EdgyFenster(start_datei=datei).start()


if __name__ == "__main__":
    main()
