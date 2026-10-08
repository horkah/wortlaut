"""Wie gut hat ein Modell gehört? Fehlerraten und eine Zahl darüber.

Gemessen wird immer dasselbe Paar: der Text, den jemand vorgelesen hat
(**Referenz**, die Vorlage aus „hören"), und der Text, den ein Modell daraus
gemacht hat (**Hypothese**). Beides sind Zeichenketten; diese Datei rechnet und
weiß nichts von Datenbanken, Modellen oder Dateien.

Vier Fehlerraten, weil keine allein genügt:

* **WER** zählt Wörter. Die vertraute Zahl, aber grob: Ein Umlaut daneben
  kostet dasselbe wie ein völlig falsches Wort, und bei kurzen Vorlagen springt
  sie in großen Stufen.
* **CER** zählt Zeichen. Fein genug für „Häuser" gegen „Heuser", aber blind
  dafür, ob ein Satz noch als derselbe Satz erkennbar ist.
* **MER** setzt die Fehler ins Verhältnis zu allem, was passiert ist, statt nur
  zur Referenz. Anders als WER kann sie nicht über 1 steigen, wenn ein Modell
  ins Fabulieren gerät und mehr ausgibt, als gesprochen wurde.
* **WIL** misst, wie viel von der Wortinformation verloren ging - sie bestraft
  Auslassen und Dazudichten gleichermaßen und ist von Haus aus auf [0, 1]
  beschränkt.

Alle vier sind Fehlermaße: kleiner ist besser. `genauigkeit()` dreht das um und
fasst sie zu einer Zahl zusammen (siehe dort).

Verglichen wird auf **normalisiertem** Text (`normalisiere`): Groß- und
Kleinschreibung, Satzzeichen und doppelte Leerzeichen sind nicht das, was hier
zur Debatte steht. Ob ein Modell einen Punkt setzt, hängt an seiner
Nachbearbeitung und nicht daran, ob es den Sprecher verstanden hat. Der
Rohtext bleibt davon unberührt - er wird gespeichert und angezeigt, damit der
Mensch die echten Unterschiede sieht.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass

# Was vor dem Vergleich vereinheitlicht wird. Typografie zuerst, damit „"
# und " nicht als verschiedene Zeichen gezählt werden.
_TYPOGRAFIE = str.maketrans(
    {
        "„": '"',
        "“": '"',
        "”": '"',
        "‟": '"',
        "‚": "'",
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
        "…": "...",
        " ": " ",
    }
)

# Satzzeichen fallen weg, Ziffern und Buchstaben bleiben. `\w` schließt in
# Python Umlaute und ß ein - genau richtig, die gehören zum Wort.
_KEIN_WORT = re.compile(r"[^\w\s]", re.UNICODE)
_MEHRFACHER_RAUM = re.compile(r"\s+")


def normalisiere(text: str) -> str:
    """Kleinschreibung, ohne Satzzeichen, einfache Leerzeichen.

    NFC zuerst: Ein „ä" kann als ein Zeichen oder als „a" plus Trema
    ankommen, je nachdem, woher der Text stammt. Ohne Angleichung zählte der
    Zeichenvergleich denselben Buchstaben einmal als eins und einmal als zwei -
    und ein Modell sähe schlechter aus, als es ist.
    """
    angeglichen = unicodedata.normalize("NFC", text).translate(_TYPOGRAFIE)
    ohne_zeichen = _KEIN_WORT.sub(" ", angeglichen.lower())
    return _MEHRFACHER_RAUM.sub(" ", ohne_zeichen).strip()


@dataclass(frozen=True)
class Schritte:
    """Die vier Zahlen, aus denen sich jede Fehlerrate ergibt."""

    treffer: int
    ersetzt: int
    geloescht: int
    eingefuegt: int

    @property
    def fehler(self) -> int:
        return self.ersetzt + self.geloescht + self.eingefuegt

    @property
    def referenzlaenge(self) -> int:
        return self.treffer + self.ersetzt + self.geloescht

    @property
    def hypothesenlaenge(self) -> int:
        return self.treffer + self.ersetzt + self.eingefuegt


def schritte(referenz: list[str], hypothese: list[str]) -> Schritte:
    """Levenshtein, aber mit Buchführung darüber, welcher Art die Fehler waren.

    Die übliche Distanz liefert nur eine Zahl. MER und WIL brauchen mehr: Sie
    unterscheiden, ob etwas fehlt, zu viel ist oder vertauscht wurde. Darum
    trägt jede Zelle nicht nur die Kosten, sondern gleich die vier Zähler des
    günstigsten Weges dorthin.

    Zwei Zeilen genügen: Rückwärts gelaufen wird nie, die Zähler wandern
    vorwärts mit.
    """
    # Erste Zeile: die Hypothese aus dem Nichts aufbauen, alles eingefügt.
    zeile: list[tuple[int, Schritte]] = [
        (j, Schritte(0, 0, 0, j)) for j in range(len(hypothese) + 1)
    ]

    for i, ref_zeichen in enumerate(referenz, start=1):
        # Erste Spalte: die Referenz vollständig gelöscht.
        neu: list[tuple[int, Schritte]] = [(i, Schritte(0, 0, i, 0))]
        for j, hyp_zeichen in enumerate(hypothese, start=1):
            diagonal_kosten, diagonal = zeile[j - 1]
            oben_kosten, oben = zeile[j]
            links_kosten, links = neu[j - 1]

            if ref_zeichen == hyp_zeichen:
                neu.append(
                    (
                        diagonal_kosten,
                        Schritte(
                            diagonal.treffer + 1,
                            diagonal.ersetzt,
                            diagonal.geloescht,
                            diagonal.eingefuegt,
                        ),
                    )
                )
                continue

            # Bei Gleichstand gewinnt das Ersetzen: Ein vertauschtes Wort ist
            # als ein Fehler verständlicher denn als Löschung plus Einfügung.
            bester = min(
                (diagonal_kosten + 1, 0),
                (links_kosten + 1, 1),
                (oben_kosten + 1, 2),
            )
            kosten, art = bester
            if art == 0:
                gezaehlt = Schritte(
                    diagonal.treffer,
                    diagonal.ersetzt + 1,
                    diagonal.geloescht,
                    diagonal.eingefuegt,
                )
            elif art == 1:
                gezaehlt = Schritte(
                    links.treffer, links.ersetzt, links.geloescht, links.eingefuegt + 1
                )
            else:
                gezaehlt = Schritte(
                    oben.treffer, oben.ersetzt, oben.geloescht + 1, oben.eingefuegt
                )
            neu.append((kosten, gezaehlt))
        zeile = neu

    return zeile[-1][1]


def _rate(zaehler: int, nenner: int) -> float:
    """Eine leere Referenz hat keine Fehlerrate; 0 ist die ehrlichere Antwort."""
    return zaehler / nenner if nenner else 0.0


@dataclass(frozen=True)
class Guete:
    """Alle Maße zu einem Paar aus Vorlage und erkanntem Text."""

    wer: float
    cer: float
    mer: float
    wil: float
    genauigkeit: float

    def als_dict(self) -> dict[str, float]:
        return asdict(self)


def genauigkeit(wer: float, cer: float, mer: float, wil: float) -> float:
    """Eine Zahl von 0 bis 100 aus den vier Fehlerraten - das geometrische Mittel.

    * **WER und CER werden gebogen, nicht gekappt** (`1/(1+x)`): Sie können
      über 1 steigen, wenn Whisper bei Stille denselben Satz wiederholt, und
      „jedes Wort falsch" soll von „dreimal richtig geliefert" unterscheidbar
      bleiben. Monoton, glatt, nie ganz null.
    * **Null ist der Boden von MER und WIL**: Beide erreichen 1 genau dann,
      wenn kein Wort getroffen wurde - Genauigkeit 0 heißt „nichts richtig".
    * **Geometrisch**, damit ein durchgefallenes Maß nicht von zwei guten
      aufgerechnet wird.

    Alle vier zählen gleich; eine Gewichtung hinge am Zweck, nicht am Modell.
    """
    faktoren = (
        1.0 / (1.0 + max(wer, 0.0)),
        1.0 / (1.0 + max(cer, 0.0)),
        1.0 - min(max(mer, 0.0), 1.0),
        1.0 - min(max(wil, 0.0), 1.0),
    )
    produkt = 1.0
    for faktor in faktoren:
        produkt *= faktor
    return 100.0 * produkt ** (1.0 / len(faktoren))


def bewerte(referenz: str, hypothese: str) -> Guete:
    """Vorlage gegen erkannten Text: vier Fehlerraten und die Zahl darüber."""
    ref_text = normalisiere(referenz)
    hyp_text = normalisiere(hypothese)

    woerter = schritte(ref_text.split(), hyp_text.split())
    # Zeichen **mit** Leerzeichen: Wo ein Modell zwei Wörter zusammenzieht, ist
    # das ein Fehler und soll auch als einer zählen.
    zeichen = schritte(list(ref_text), list(hyp_text))

    wer = _rate(woerter.fehler, woerter.referenzlaenge)
    cer = _rate(zeichen.fehler, zeichen.referenzlaenge)
    mer = _rate(woerter.fehler, woerter.treffer + woerter.fehler)
    # WIP: der Anteil der Wortinformation, der erhalten blieb. Das Produkt der
    # beiden Trefferquoten - gegen die Referenz und gegen die Hypothese -
    # bestraft Auslassen und Dazudichten in einem Maß.
    wip = (
        woerter.treffer**2 / (woerter.referenzlaenge * woerter.hypothesenlaenge)
        if woerter.referenzlaenge and woerter.hypothesenlaenge
        else 0.0
    )
    wil = 1.0 - wip

    return Guete(
        wer=wer, cer=cer, mer=mer, wil=wil, genauigkeit=genauigkeit(wer, cer, mer, wil)
    )


# ── Die Maße, wie sie heißen ────────────────────────────────────────────────
#
# Name, Erklärung und Richtung jedes Maßes - einmal, für Auswertung und
# Modelltafel. Wie eine Ansicht ein Maß darstellt (Einheit, Stellen, Achse),
# steht bei ihr.


@dataclass(frozen=True)
class Mass:
    schluessel: str
    name: str
    kurz: str
    erklaerung: str
    hoch_ist_gut: bool = False


# Was `bewerte` liefert, in der Reihenfolge der Anzeige - die Felder von `Guete`.
GUETE = (
    Mass(
        "genauigkeit",
        "Genauigkeit",
        "Genauigkeit",
        "Die vier Fehlermaße zu einer Zahl zusammengefasst, 0 bis 100.",
        hoch_ist_gut=True,
    ),
    Mass("wer", "Wortfehlerrate (WER)", "WER", "Anteil falscher, fehlender und zusätzlicher Wörter."),
    Mass("cer", "Zeichenfehlerrate (CER)", "CER", "Dasselbe auf Zeichen - feiner, aber blind für den Sinn."),
    Mass("mer", "Trefferfehlerrate (MER)", "MER", "Fehler im Verhältnis zu allem Gesagten; nie über 1."),
    Mass("wil", "Wortinformationsverlust (WIL)", "WIL", "Wie viel Wortinformation verloren ging; nie über 1."),
)
RECHENZEIT = Mass(
    "rechenzeit_s",
    "Rechenzeit",
    "Zeit",
    "Sekunden je Aufnahme. Sie hängt an der Maschine: Zwischen Karte und Prozessor "
    "liegt das Zehn- bis Zwanzigfache - vergleichbar nur auf demselben Rechenwerk.",
)
# Jedes Maß einer Erkennung, die Rechenzeit zuletzt.
MASSE = (*GUETE, RECHENZEIT)
GUETEFELDER = tuple(mass.schluessel for mass in GUETE)
MESSFELDER = tuple(mass.schluessel for mass in MASSE)
# Bei diesen Maßen ist größer besser; bei allen übrigen kleiner.
HOCH_IST_GUT = frozenset(mass.schluessel for mass in MASSE if mass.hoch_ist_gut)
