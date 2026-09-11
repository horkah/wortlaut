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

    Gesucht war ein Wert, den man über Aufnahmen und Modelle hinweg vergleichen
    kann, ohne vier Kurven nebeneinander zu legen. Drei Entscheidungen stecken
    darin:

    **Die unbeschränkten Raten werden gebogen, nicht gekappt.** WER und CER
    können über 1 hinausgehen, wenn ein Modell mehr ausgibt, als gesprochen
    wurde - Whisper neigt bei Stille dazu, denselben Satz mehrfach zu
    wiederholen. Ein Deckel bei 1 wäre naheliegend und wäre falsch: Er machte
    „jedes Wort daneben" und „den Satz dreimal geliefert" ununterscheidbar,
    obwohl im zweiten Fall jedes Wort richtig erkannt wurde. Stattdessen
    `1/(1+x)`: bei 0 Fehlern 1, bei WER 1 genau ½, darüber fallend und nie
    ganz null. Monoton, glatt und ohne Sprungstelle - was für eine Kurve über
    hunderte Aufnahmen zählt.

    **Null bleibt der Boden, den MER und WIL setzen.** Die beiden sind von
    Haus aus auf [0, 1] beschränkt und erreichen die 1 genau dann, wenn kein
    einziges Wort getroffen wurde. Damit ist die Gesamtnote 0 gleichbedeutend
    mit „nichts davon war richtig" - und nicht mit „irgendeine Rate ist eben
    über den Deckel gerutscht".

    **Gemittelt wird geometrisch, nicht arithmetisch.** Das arithmetische
    Mittel lässt sich mit zwei guten Werten gegen einen katastrophalen
    aufrechnen: Ein Modell, das die Zeichen ungefähr trifft, aber kein einziges
    Wort, bekäme eine mittlere Note. Das geometrische Mittel kann das nicht -
    fällt ein Faktor auf null, fällt das Ergebnis mit. Genau das ist hier
    gewollt: Die vier Maße sind vier Blickwinkel auf dieselbe Frage, und wer
    aus einem davon durchfällt, hat nicht verstanden, was gesagt wurde.

    Alle vier zählen gleich. Eine Gewichtung wäre eine Behauptung darüber,
    welcher Fehler schwerer wiegt - die hängt am Zweck (Vorlesen, Diktat,
    Suche) und nicht am Modell. Solange dieser Zweck nicht feststeht, ist
    gleiches Gewicht die ehrlichere Vorgabe. Wer es anders braucht, sieht die
    Einzelmaße daneben; gespeichert werden sie alle.
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
